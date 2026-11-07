"""PDV Asaas: UoW owns financial state; PSP is only an external evidence source."""
from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from application.finalizacao_pagamento import finalizar_pagamento_liquidado_em_transacao
from core.dominio.dinheiro import Dinheiro
from core.pagamentos.asaas import AdapterAsaas, ErroAsaas, PagadorAsaas
from core.pagamentos.modelos import (
    MetodoPagamento,
    StatusTransacao,
    TipoTransacao,
    TransacaoPagamento,
)
from core.pagamentos.servicos import _confirmar_pagamento_validado, registrar_estorno
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Permissao
from infra.pagamentos.asaas_runtime import AsaasAdapterFactory
from infra.transacoes.uow import UnitOfWorkV1


class ErroPagamentoAsaas(ValueError):
    pass


@dataclass(frozen=True)
class ResultadoPagamentoAsaas:
    pagamento_id: str
    order_id: str
    status_provedor: str
    status_pagamento: str
    pix_copia_cola: str | None
    qr_code_base64: str | None
    pagamento_url: str | None
    idempotente: bool


def _ref(kind: str, *parts: str) -> str:
    joined = "\x00".join(parts).encode("utf-8")
    return "kd-" + kind + "-" + hashlib.sha256(joined).hexdigest()


def _exigir(contexto: ContextoExecucao, *, confirmar: bool) -> None:
    needed = {Permissao.PDV_OPERAR, Permissao.PAGAMENTO_REGISTRAR}
    if confirmar:
        needed.add(Permissao.PAGAMENTO_CONFIRMAR)
    if not needed.issubset(contexto.permissoes):
        raise PermissionError("seguranca.pdv_pagamento_permissao_exigida")


def _pagamento(uow: UnitOfWorkV1, contexto: ContextoExecucao, payment_id: str):
    pagamento = uow.pagamentos.buscar_pagamento(
        contexto.tenant_id, contexto.unidade_id, payment_id,
    )
    if pagamento is None:
        raise LookupError("pagamento_nao_encontrado")
    if pagamento.metodo not in {MetodoPagamento.PIX, MetodoPagamento.CARTAO_CREDITO}:
        raise ErroPagamentoAsaas("asaas_metodo_nao_suportado")
    if pagamento.provedor != "asaas":
        raise ErroPagamentoAsaas("asaas_provedor_divergente")
    return pagamento


def _metodo(pagamento) -> str:
    return "PIX" if pagamento.metodo is MetodoPagamento.PIX else "CREDIT_CARD"


def _vinculo(uow: UnitOfWorkV1, contexto: ContextoExecucao, payment_id: str):
    records = [
        t for t in uow.pagamentos.listar_transacoes(
            contexto.tenant_id, contexto.unidade_id, payment_id
        ) if t.tipo is TipoTransacao.INICIACAO and t.provedor == "asaas"
        and t.id_externo
    ]
    if len(records) > 1:
        raise ErroPagamentoAsaas("asaas_multiplas_cobrancas")
    return records[0] if records else None


def _out(pagamento, charge, repeat: bool) -> ResultadoPagamentoAsaas:
    return ResultadoPagamentoAsaas(
        pagamento_id=pagamento.id, order_id=charge.id_externo,
        status_provedor=charge.status,
        status_pagamento=pagamento.status.value,
        pix_copia_cola=charge.pix_copia_cola,
        qr_code_base64=charge.pix_qr_base64,
        pagamento_url=charge.url_fatura,
        idempotente=repeat,
    )


def iniciar_cobranca_asaas_pdv(
    *,
    contexto: ContextoExecucao,
    pagamento_id: str,
    pagador: PagadorAsaas,
    session_factory: Callable[[], Session],
    adapter_factory: Any | None = None,
) -> ResultadoPagamentoAsaas:
    _exigir(contexto, confirmar=False)
    pagador.validar()
    with UnitOfWorkV1(session_factory) as uow:
        pagamento = _pagamento(uow, contexto, pagamento_id)
        if pagamento.saldo.valor <= 0:
            raise ErroPagamentoAsaas("asaas_pagamento_ja_liquidado")
        assert uow.session is not None
        factory = adapter_factory or AsaasAdapterFactory()
        adapter: AdapterAsaas = factory.construir(
            session=uow.session,
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
            servico="pagamentos.pix" if pagamento.metodo is MetodoPagamento.PIX else "pagamentos.cartao",
        )
        previous = _vinculo(uow, contexto, pagamento_id)
        ref = _ref("pay", contexto.tenant_id, contexto.unidade_id, pagamento_id)
        cpf = "".join(c for c in pagador.documento if c.isdigit())
        customer = adapter.obter_ou_criar_cliente(
            pagador, reference=_ref("cus", contexto.tenant_id, contexto.unidade_id, cpf),
        )
        charge = adapter.criar_cobranca(
            reference=ref, customer_id=customer,
            valor=pagamento.saldo, metodo=_metodo(pagamento),
            vencimento=datetime.now(timezone.utc).date(),
        )
        if previous:
            if charge.id_externo != previous.id_externo:
                raise ErroPagamentoAsaas("asaas_referencia_mudou")
            return _out(pagamento, charge, True)
        now = datetime.now(timezone.utc)
        transacao = TransacaoPagamento(
            str(uuid4()), pagamento.id, pagamento.tenant_id, pagamento.unidade_id,
            TipoTransacao.INICIACAO, StatusTransacao.PENDENTE,
            Dinheiro(Decimal("0.00"), pagamento.moeda),
            pagamento.metodo, "asaas", charge.id_externo,
            f"asaas:iniciar:{pagamento.id}", now, now,
            contexto.correlation_id, contexto.causation_id,
            (("status_provedor", charge.status),),
        )
        uow.pagamentos.append_transacao(
            transacao, hashlib.sha256(
                f"{pagamento.id}:{charge.id_externo}:{pagamento.saldo.valor}".encode()
            ).hexdigest(),
        )
        uow.commit()
        return _out(pagamento, charge, False)


def _verificar_em_transacao(
    *, uow: UnitOfWorkV1, contexto: ContextoExecucao, pagamento_id: str,
    adapter: AdapterAsaas,
) -> ResultadoPagamentoAsaas:
    pagamento = _pagamento(uow, contexto, pagamento_id)
    vinculo = _vinculo(uow, contexto, pagamento_id)
    if vinculo is None or not vinculo.id_externo:
        raise ErroPagamentoAsaas("asaas_cobranca_nao_iniciada")
    ref = _ref("pay", contexto.tenant_id, contexto.unidade_id, pagamento_id)
    charge = adapter.consultar_cobranca(
        id_externo=vinculo.id_externo, reference=ref,
        metodo=_metodo(pagamento), valor=pagamento.valor_previsto,
    )
    if charge.status == "estornado" and (
        pagamento.valor_pago - pagamento.valor_estornado
    ).valor > 0:
        now = datetime.now(timezone.utc)
        trusted = ContextoExecucao.sistema(
            identidade="asaas-refund-reconciliacao",
            motivo="estorno confirmado por consulta autenticada ao Asaas",
            tenant_id=pagamento.tenant_id, unidade_id=pagamento.unidade_id,
            correlation_id=vinculo.correlation_id, solicitado_em=now,
        )
        result = registrar_estorno(
            contexto=trusted, repositorio=uow.pagamentos,
            pagamento_id=pagamento.id,
            valor=pagamento.valor_pago - pagamento.valor_estornado,
            motivo="asaas_estorno_confirmado_por_consulta",
            idempotency_key=f"asaas:estorno:{vinculo.id_externo}",
            expected_version=pagamento.versao,
            timestamp=now,
        )
        if not result.idempotente:
            uow.registrar_efeitos(eventos=result.eventos, auditorias=result.auditorias)
        uow.commit()
        pagamento = result.pagamento
    if charge.status == "pago" and pagamento.saldo.valor > 0:
        now = datetime.now(timezone.utc)
        trusted = ContextoExecucao.sistema(
            identidade="asaas-reconciliacao",
            motivo="consulta autenticada Asaas v3 vinculada ao pagamento canonico",
            tenant_id=pagamento.tenant_id,
            unidade_id=pagamento.unidade_id,
            correlation_id=vinculo.correlation_id,
            solicitado_em=now,
        )
        result = _confirmar_pagamento_validado(
            contexto=trusted, repositorio=uow.pagamentos, pagamento_id=pagamento.id,
            valor=charge.valor, metodo=pagamento.metodo,
            idempotency_key=f"asaas:consulta:{vinculo.id_externo}:pago",
            expected_version=pagamento.versao, timestamp=now,
            referencia_externa=vinculo.id_externo, fonte_financeira_validada=True,
        )
        if not result.idempotente:
            uow.registrar_efeitos(eventos=result.eventos, auditorias=result.auditorias)
        finalizar_pagamento_liquidado_em_transacao(
            recursos=uow.recursos, pagamento=result.pagamento, timestamp=now,
        )
        uow.commit()
        pagamento = result.pagamento
    return _out(pagamento, charge, True)


def verificar_cobranca_asaas_pdv(
    *,
    contexto: ContextoExecucao,
    pagamento_id: str,
    session_factory: Callable[[], Session],
    adapter_factory: Any | None = None,
) -> ResultadoPagamentoAsaas:
    _exigir(contexto, confirmar=True)
    with UnitOfWorkV1(session_factory) as uow:
        pagamento = _pagamento(uow, contexto, pagamento_id)
        assert uow.session is not None
        factory = adapter_factory or AsaasAdapterFactory()
        adapter = factory.construir(
            session=uow.session, tenant_id=pagamento.tenant_id,
            unidade_id=pagamento.unidade_id,
            servico="pagamentos.pix" if pagamento.metodo is MetodoPagamento.PIX else "pagamentos.cartao",
        )
        return _verificar_em_transacao(
            uow=uow, contexto=contexto, pagamento_id=pagamento_id, adapter=adapter,
        )


def receber_webhook_asaas(
    *,
    payload: dict[str, Any], header_token: str | None,
    session_factory: Callable[[], Session],
    adapter_factory: Any | None = None,
) -> bool:
    """Webhook is only a trigger: a second authenticated GET proves actual payment.

    Resolve ledger binding before selecting tenant credentials; do not accept tenant
    or unit from the public body. GET never promotes refunds or authorizations.
    """
    payment = payload.get("payment")
    if not isinstance(payment, dict):
        raise ErroAsaas("asaas_webhook_invalido")
    external_id = payment.get("id")
    if not isinstance(external_id, str):
        raise ErroAsaas("asaas_webhook_invalido")
    with UnitOfWorkV1(session_factory) as uow:
        binding = uow.pagamentos.buscar_transacao_externa(
            "asaas", external_id, TipoTransacao.INICIACAO,
        )
        if binding is None:
            return False
        assert uow.session is not None
        factory = adapter_factory or AsaasAdapterFactory()
        pagamento = uow.pagamentos.buscar_pagamento(
            binding.tenant_id, binding.unidade_id, binding.pagamento_id,
        )
        if pagamento is None:
            raise ErroAsaas("asaas_vinculo_sem_pagamento")
        adapter = factory.construir(
            session=uow.session, tenant_id=binding.tenant_id,
            unidade_id=binding.unidade_id,
            servico="pagamentos.pix" if pagamento.metodo is MetodoPagamento.PIX else "pagamentos.cartao",
        )
        evento = adapter.autenticar_webhook(recebido=header_token, payload=payload)
        if evento.pagamento_externo != binding.id_externo or evento.referencia != _ref(
            "pay", binding.tenant_id, binding.unidade_id, binding.pagamento_id
        ):
            raise ErroAsaas("asaas_webhook_vinculo_divergente")
        if evento.evento not in {"PAYMENT_RECEIVED", "PAYMENT_CONFIRMED", "PAYMENT_REFUNDED", "PAYMENT_REFUND_CONFIRMED"}:
            return True
        context = ContextoExecucao.sistema(
            identidade="asaas-webhook",
            motivo="evento autenticado e nova consulta financeira",
            tenant_id=binding.tenant_id, unidade_id=binding.unidade_id,
            correlation_id=binding.correlation_id,
            solicitado_em=datetime.now(timezone.utc),
        )
        _verificar_em_transacao(
            uow=uow, contexto=context, pagamento_id=binding.pagamento_id,
            adapter=adapter,
        )
        return True
