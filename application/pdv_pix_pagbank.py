"""Captura Pix PagBank para o caixa Web, usando o ledger financeiro canônico.

O PDV registra a obrigação no checkout; só o provedor confirma a liquidação.
Todas as mutações e finalização do pedido/estoque pertencem à Application/UoW.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from application.pagbank import criar_pix_pagbank_em_transacao
from application.pagbank_reconciliacao import reconciliar_order_pagbank_em_transacao
from core.pagamentos.modelos import MetodoPagamento, TipoTransacao
from core.pagamentos.pagbank import ClientePagBank
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Permissao
from core.seguranca.segredos import SecretStore
from infra.pagamentos.pagbank_runtime import PagBankAdapterFactory
from infra.transacoes.uow import UnitOfWorkV1


class PixPdvInvalido(ValueError):
    """O pagamento consultado não permite a operação solicitada."""


@dataclass(frozen=True)
class PixPdvCobranca:
    pagamento_id: str
    order_id: str
    status_provedor: str
    status_pagamento: str
    pix_copia_cola: str | None
    qr_code_url: str | None
    idempotente: bool


def _exigir_caixa(contexto: ContextoExecucao, *, confirmar: bool = False) -> None:
    exigidas = {Permissao.PDV_OPERAR, Permissao.PAGAMENTO_REGISTRAR}
    if confirmar:
        exigidas.add(Permissao.PAGAMENTO_CONFIRMAR)
    if not exigidas.issubset(contexto.permissoes):
        raise PermissionError("seguranca.pdv_pagamento_permissao_exigida")


def _pagamento_pix(uow: UnitOfWorkV1, contexto: ContextoExecucao, pagamento_id: str):
    pagamento = uow.pagamentos.buscar_pagamento(
        contexto.tenant_id,
        contexto.unidade_id,
        pagamento_id,
    )
    if pagamento is None:
        raise LookupError("pagamento_nao_encontrado")
    if pagamento.metodo is not MetodoPagamento.PIX:
        raise PixPdvInvalido("pagamento_nao_e_pix")
    return pagamento


def _order_vinculada(uow: UnitOfWorkV1, contexto: ContextoExecucao, pagamento_id: str) -> str:
    ordens = [
        item.id_externo
        for item in uow.pagamentos.listar_transacoes(
            contexto.tenant_id,
            contexto.unidade_id,
            pagamento_id,
        )
        if item.provedor == "pagbank"
        and item.tipo is TipoTransacao.INICIACAO
        and item.id_externo
    ]
    if len(set(ordens)) != 1:
        raise PixPdvInvalido("pix_pagbank_sem_order_unica")
    return ordens[0]


def iniciar_pix_pagbank_pdv(
    *,
    contexto: ContextoExecucao,
    pagamento_id: str,
    cliente: ClientePagBank,
    session_factory: Callable[[], Session],
    secret_store: SecretStore | None = None,
    adapter_factory: Any | None = None,
) -> PixPdvCobranca:
    _exigir_caixa(contexto)
    pagamento_id = pagamento_id.strip()
    if not pagamento_id:
        raise PixPdvInvalido("pagamento_id_invalido")
    cliente.para_payload()  # valida sem persistir CPF/CNPJ no banco local
    with UnitOfWorkV1(session_factory) as uow:
        pagamento = _pagamento_pix(uow, contexto, pagamento_id)
        if pagamento.saldo.valor <= 0:
            raise PixPdvInvalido("pagamento_ja_liquidado")
        assert uow.session is not None
        fabrica = adapter_factory or PagBankAdapterFactory(secret_store=secret_store)
        adapter = fabrica.construir(
            session=uow.session,
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
        )
        criado = criar_pix_pagbank_em_transacao(
            contexto=contexto,
            recursos=uow.recursos,
            adapter=adapter,
            pagamento_id=pagamento_id,
            cliente=cliente,
            # Identidade estável entre timeouts/retries, sem duplicar ordem externa.
            idempotency_key=f"pdv-pix-{pagamento_id}"[:128],
            timestamp=datetime.now(timezone.utc),
        )
        exibicao = dict(criado.payload_exibicao)
        status_provedor = criado.status
        if criado.idempotente:
            consulta = adapter.consultar_transacao(criado.order_id)
            if consulta is None:
                raise PixPdvInvalido("pix_pagbank_order_indisponivel")
            exibicao = dict(consulta.payload_exibicao)
            status_provedor = consulta.status
        else:
            uow.commit()
        return PixPdvCobranca(
            pagamento_id=pagamento_id,
            order_id=criado.order_id,
            status_provedor=status_provedor,
            status_pagamento=pagamento.status.value,
            pix_copia_cola=exibicao.get("pix_copia_cola"),
            qr_code_url=exibicao.get("qr_code_png_url"),
            idempotente=criado.idempotente,
        )


def verificar_pix_pagbank_pdv(
    *,
    contexto: ContextoExecucao,
    pagamento_id: str,
    session_factory: Callable[[], Session],
    secret_store: SecretStore | None = None,
    adapter_factory: Any | None = None,
) -> dict[str, str]:
    """Consulta a fonte financeira externa; nunca aceita confirmação do browser."""
    _exigir_caixa(contexto, confirmar=True)
    pagamento_id = pagamento_id.strip()
    with UnitOfWorkV1(session_factory) as uow:
        _pagamento_pix(uow, contexto, pagamento_id)
        order_id = _order_vinculada(uow, contexto, pagamento_id)
        assert uow.session is not None
        fabrica = adapter_factory or PagBankAdapterFactory(secret_store=secret_store)
        adapter = fabrica.construir(
            session=uow.session,
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
        )
        resultado = reconciliar_order_pagbank_em_transacao(
            recursos=uow.recursos,
            adapter=adapter,
            order_id=order_id,
            timestamp=datetime.now(timezone.utc),
        )
        if resultado is not None:
            uow.commit()
        atualizado = _pagamento_pix(uow, contexto, pagamento_id)
        return {
            "pagamento_id": pagamento_id,
            "order_id": order_id,
            "status_pagamento": atualizado.status.value,
        }
