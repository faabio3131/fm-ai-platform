"""Orquestração PagBank/PIX sobre o ledger financeiro canônico."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from core.dominio.dinheiro import Dinheiro
from core.dominio.ids import (
    CorrelationId,
    EventoId,
    IdempotencyKey,
    TenantId,
    UnidadeId,
)
from core.eventos.modelos import EnvelopeMensagem
from core.pagamentos.modelos import (
    MetodoPagamento,
    Pagamento,
    StatusTransacao,
    TipoTransacao,
    TransacaoPagamento,
)
from core.pagamentos.pagbank import AdapterPagBank, ClientePagBank
from core.pagamentos.servicos import processar_webhook
from core.seguranca.auditoria import EventoAuditoria, sanitizar_metadata
from core.seguranca.contexto import ContextoExecucao
from infra.transacoes.uow import RecursosTransacionaisV1


class PagBankAplicacaoInvalida(RuntimeError):
    pass


@dataclass(frozen=True)
class ResultadoCriacaoPixPagBank:
    pagamento: Pagamento
    order_id: str
    status: str
    payload_exibicao: tuple[tuple[str, str], ...]
    idempotente: bool = False


def _hash(*valores: object) -> str:
    return hashlib.sha256(
        json.dumps(valores, default=str, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def criar_pix_pagbank_em_transacao(
    *,
    contexto: ContextoExecucao,
    recursos: RecursosTransacionaisV1,
    adapter: AdapterPagBank,
    pagamento_id: str,
    cliente: ClientePagBank,
    idempotency_key: str,
    timestamp: datetime,
) -> ResultadoCriacaoPixPagBank:
    pagamento = recursos.pagamentos.buscar_pagamento(
        contexto.tenant_id, contexto.unidade_id, pagamento_id
    )
    if pagamento is None:
        raise PagBankAplicacaoInvalida("pagamento não encontrado")
    if pagamento.metodo is not MetodoPagamento.PIX:
        raise PagBankAplicacaoInvalida("PagBank PIX exige pagamento PIX")
    if pagamento.saldo.valor <= 0:
        raise PagBankAplicacaoInvalida("pagamento já liquidado")

    existente = next(
        (
            t
            for t in recursos.pagamentos.listar_transacoes(
                contexto.tenant_id, contexto.unidade_id, pagamento_id
            )
            if t.provedor == "pagbank"
            and t.tipo is TipoTransacao.INICIACAO
            and t.id_externo
        ),
        None,
    )
    if existente:
        return ResultadoCriacaoPixPagBank(
            pagamento,
            existente.id_externo or "",
            "pendente",
            (),
            True,
        )

    cobranca = adapter.criar_pix(
        pagamento_id=pagamento_id,
        valor=pagamento.saldo,
        idempotency_key=idempotency_key,
        cliente=cliente,
    )
    transacao = TransacaoPagamento(
        str(uuid4()),
        pagamento.id,
        pagamento.tenant_id,
        pagamento.unidade_id,
        TipoTransacao.INICIACAO,
        StatusTransacao.PENDENTE,
        Dinheiro(0, pagamento.moeda),
        MetodoPagamento.PIX,
        "pagbank",
        cobranca.id_externo,
        f"pagbank:order:{idempotency_key}",
        timestamp,
        timestamp,
        contexto.correlation_id,
        contexto.causation_id,
        (("order_status", cobranca.status),),
    )
    transacao = recursos.pagamentos.append_transacao(
        transacao,
        _hash(pagamento.id, cobranca.id_externo, pagamento.saldo.valor),
    )
    evento = EnvelopeMensagem(
        EventoId(str(uuid4())),
        "pagamento.cobranca_externa_criada",
        pagamento.id,
        "pagamento",
        TenantId(pagamento.tenant_id),
        UnidadeId(pagamento.unidade_id),
        CorrelationId(contexto.correlation_id),
        None,
        IdempotencyKey(f"{transacao.idempotency_key}:evento"),
        timestamp,
        {"provedor": "pagbank", "order_id": cobranca.id_externo},
        pagamento.versao,
    )
    auditoria = EventoAuditoria(
        str(uuid4()),
        pagamento.tenant_id,
        pagamento.unidade_id,
        contexto.usuario_id,
        next(iter(contexto.papeis), None),
        "pagamento.criar_pix_pagbank",
        "pagamento",
        pagamento.id,
        "sucesso",
        "cobranca_externa_criada",
        contexto.correlation_id,
        timestamp,
        contexto.origem,
        "pay002_pagbank",
        causation_id=contexto.causation_id,
        metadata=sanitizar_metadata({"provedor": "pagbank", "order_id": cobranca.id_externo}),
    )
    recursos.registrar_efeitos(eventos=(evento,), auditorias=(auditoria,))
    return ResultadoCriacaoPixPagBank(
        pagamento,
        cobranca.id_externo,
        cobranca.status,
        cobranca.payload_exibicao,
    )


def processar_webhook_pagbank_em_transacao(
    *,
    recursos: RecursosTransacionaisV1,
    adapter: AdapterPagBank,
    payload_bruto: bytes,
    assinatura: str,
):
    webhook = adapter.normalizar_webhook_assinado(
        payload_bruto=payload_bruto, assinatura=assinatura
    )
    if not webhook.assinatura_validada:
        return None
    vinculo = recursos.pagamentos.buscar_transacao_externa(
        "pagbank", webhook.id_externo, TipoTransacao.INICIACAO
    )
    if vinculo is None:
        return None
    pagamento = recursos.pagamentos.buscar_pagamento(
        vinculo.tenant_id, vinculo.unidade_id, vinculo.pagamento_id
    )
    if pagamento is None:
        raise PagBankAplicacaoInvalida("vínculo PagBank sem pagamento interno")
    contexto = ContextoExecucao.sistema(
        identidade="pagbank-webhook",
        motivo="webhook PagBank com autenticidade validada",
        tenant_id=vinculo.tenant_id,
        unidade_id=vinculo.unidade_id,
        correlation_id=vinculo.correlation_id,
        solicitado_em=webhook.timestamp,
    )
    resultado = processar_webhook(
        contexto=contexto,
        repositorio=recursos.pagamentos,
        pagamento_id=vinculo.pagamento_id,
        webhook=webhook,
        expected_version=pagamento.versao,
    )
    if resultado is not None and not resultado.idempotente:
        recursos.registrar_efeitos(
            eventos=resultado.eventos, auditorias=resultado.auditorias
        )
    return resultado
