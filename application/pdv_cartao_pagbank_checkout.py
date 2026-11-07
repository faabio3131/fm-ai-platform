"""Checkout de cartão hospedado no PagBank sem manipular PAN/CVV no Kordena."""
from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.orm import Session

from application.finalizacao_pagamento import finalizar_pagamento_liquidado_em_transacao
from core.dominio.dinheiro import Dinheiro
from core.pagamentos.adapters import CobrancaProvedor
from core.pagamentos.fontes_financeiras import confirmar_cartao_por_consulta_provedor
from core.pagamentos.modelos import (
    MetodoPagamento,
    StatusTransacao,
    TipoTransacao,
    TransacaoPagamento,
)
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Permissao
from core.seguranca.segredos import SecretStore
from infra.pagamentos.pagbank_runtime import PagBankAdapterFactory
from infra.transacoes.uow import UnitOfWorkV1


class CheckoutCartaoInvalido(ValueError):
    """O checkout não corresponde a uma obrigação cartão deste estabelecimento."""


@dataclass(frozen=True)
class ResultadoCheckoutCartao:
    pagamento_id: str
    checkout_id: str
    pagamento_url: str
    status_provedor: str
    status_pagamento: str
    idempotente: bool


def _permissao(contexto: ContextoExecucao, *, confirmar: bool) -> None:
    exigidas = {Permissao.PDV_OPERAR, Permissao.PAGAMENTO_REGISTRAR}
    if confirmar:
        exigidas.add(Permissao.PAGAMENTO_CONFIRMAR)
    if not exigidas.issubset(contexto.permissoes):
        raise PermissionError("seguranca.cartao_checkout_permissao_exigida")


def _pagamento(uow, contexto: ContextoExecucao, pagamento_id: str):
    pagamento = uow.pagamentos.buscar_pagamento(
        contexto.tenant_id, contexto.unidade_id, pagamento_id
    )
    if pagamento is None:
        raise LookupError("pagamento_nao_encontrado")
    if pagamento.metodo not in {
        MetodoPagamento.CARTAO_CREDITO, MetodoPagamento.CARTAO_DEBITO
    }:
        raise CheckoutCartaoInvalido("pagamento_nao_e_cartao")
    return pagamento


def _vinculo(uow, contexto: ContextoExecucao, pagamento_id: str):
    encontrados = [
        t for t in uow.pagamentos.listar_transacoes(
            contexto.tenant_id, contexto.unidade_id, pagamento_id
        )
        if t.tipo is TipoTransacao.INICIACAO
        and t.provedor == "pagbank_checkout"
        and (t.id_externo or "").startswith("CHEC_")
    ]
    if len(encontrados) > 1:
        raise CheckoutCartaoInvalido("checkout_multiplo_para_pagamento")
    return encontrados[0] if encontrados else None


def criar_checkout_cartao_pdv(
    *,
    contexto: ContextoExecucao,
    pagamento_id: str,
    session_factory: Callable[[], Session],
    secret_store: SecretStore | None = None,
) -> ResultadoCheckoutCartao:
    _permissao(contexto, confirmar=False)
    with UnitOfWorkV1(session_factory) as uow:
        pagamento = _pagamento(uow, contexto, pagamento_id)
        if pagamento.saldo.valor <= 0:
            raise CheckoutCartaoInvalido("pagamento_ja_liquidado")
        assert uow.session is not None
        adapter = PagBankAdapterFactory(secret_store=secret_store).construir(
            session=uow.session,
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
        )
        anterior = _vinculo(uow, contexto, pagamento_id)
        if anterior:
            retorno = adapter.consultar_checkout_cartao(
                checkout_id=anterior.id_externo,
                pagamento_id=pagamento.id,
                valor=pagamento.saldo,
                metodo=pagamento.metodo.value,
            )
            return ResultadoCheckoutCartao(
                pagamento_id=pagamento_id,
                checkout_id=retorno.checkout_id,
                pagamento_url=retorno.pagamento_url,
                status_provedor=retorno.status,
                status_pagamento=pagamento.status.value,
                idempotente=True,
            )

        idempotency_key = "kordena-card-" + pagamento.id
        criado = adapter.criar_checkout_cartao(
            pagamento_id=pagamento.id,
            valor=pagamento.saldo,
            metodo=pagamento.metodo.value,
            idempotency_key=idempotency_key,
        )
        now = datetime.now(timezone.utc)
        trans = TransacaoPagamento(
            str(uuid4()),
            pagamento.id,
            pagamento.tenant_id,
            pagamento.unidade_id,
            TipoTransacao.INICIACAO,
            StatusTransacao.PENDENTE,
            Dinheiro(Decimal(0), pagamento.moeda),
            pagamento.metodo,
            "pagbank_checkout",
            criado.checkout_id,
            f"pagbank:checkout:{pagamento.id}",
            now,
            now,
            contexto.correlation_id,
            contexto.causation_id,
            (("checkout_status", criado.status),),
        )
        fingerprint = hashlib.sha256(
            f"{pagamento.id}:{criado.checkout_id}:{pagamento.saldo.valor}".encode()
        ).hexdigest()
        uow.pagamentos.append_transacao(trans, fingerprint)
        uow.commit()
        return ResultadoCheckoutCartao(
            pagamento_id=pagamento.id,
            checkout_id=criado.checkout_id,
            pagamento_url=criado.pagamento_url,
            status_provedor=criado.status,
            status_pagamento=pagamento.status.value,
            idempotente=False,
        )


def verificar_checkout_cartao_pdv(
    *,
    contexto: ContextoExecucao,
    pagamento_id: str,
    session_factory: Callable[[], Session],
    secret_store: SecretStore | None = None,
) -> ResultadoCheckoutCartao:
    _permissao(contexto, confirmar=True)
    with UnitOfWorkV1(session_factory) as uow:
        pagamento = _pagamento(uow, contexto, pagamento_id)
        vinculo = _vinculo(uow, contexto, pagamento_id)
        if vinculo is None or not vinculo.id_externo:
            raise CheckoutCartaoInvalido("checkout_pagbank_nao_iniciado")
        assert uow.session is not None
        adapter = PagBankAdapterFactory(secret_store=secret_store).construir(
            session=uow.session,
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
        )
        retorno = adapter.consultar_checkout_cartao(
            checkout_id=vinculo.id_externo,
            pagamento_id=pagamento.id,
            valor=pagamento.valor_previsto,
            metodo=pagamento.metodo.value,
        )
        if retorno.status == "pago" and pagamento.saldo.valor > 0:
            now = datetime.now(timezone.utc)
            trusted = ContextoExecucao.sistema(
                identidade="pagbank-checkout-reconciliacao",
                motivo="consulta autenticada do checkout PagBank com cartao pago",
                tenant_id=pagamento.tenant_id,
                unidade_id=pagamento.unidade_id,
                correlation_id=vinculo.correlation_id,
                solicitado_em=now,
            )
            result = confirmar_cartao_por_consulta_provedor(
                contexto=trusted,
                repositorio=uow.pagamentos,
                pagamento_id=pagamento.id,
                provedor="pagbank_checkout",
                cobranca=CobrancaProvedor(
                    retorno.checkout_id, "pago", pagamento.valor_previsto
                ),
                expected_version=pagamento.versao,
                timestamp=now,
            )
            if result is not None:
                if not result.idempotente:
                    uow.registrar_efeitos(
                        eventos=result.eventos,
                        auditorias=result.auditorias,
                    )
                finalizar_pagamento_liquidado_em_transacao(
                    recursos=uow.recursos,
                    pagamento=result.pagamento,
                    timestamp=now,
                )
                uow.commit()
                pagamento = result.pagamento

        return ResultadoCheckoutCartao(
            pagamento_id=pagamento.id,
            checkout_id=retorno.checkout_id,
            pagamento_url=retorno.pagamento_url,
            status_provedor=retorno.status,
            status_pagamento=pagamento.status.value,
            idempotente=True,
        )
