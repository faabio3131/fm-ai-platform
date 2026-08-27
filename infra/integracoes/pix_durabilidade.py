"""Persistência durável do vínculo entre cobrança Pix externa e pagamento V1."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.dominio.dinheiro import Dinheiro
from core.pagamentos.adaptador_sqlalchemy import RepositorioPagamentosSQLAlchemy
from core.pagamentos.adapters import CobrancaProvedor
from core.pagamentos.fontes_financeiras import confirmar_pix_por_consulta_provedor
from core.pagamentos.modelos import (
    MetodoPagamento,
    ResultadoPagamento,
    StatusTransacao,
    TipoTransacao,
    TransacaoPagamento,
)
from core.pagamentos.modelos_orm import PagamentoORM, TransacaoPagamentoORM
from core.pagamentos.servicos import criar_obrigacao_pagamento
from core.seguranca.contexto import ContextoExecucao

from .pix_runtime import CobrancaPixRuntime


def _agora_utc() -> datetime:
    return datetime.now(timezone.utc)


def _fingerprint(*valores: object) -> str:
    bruto = "|".join(str(valor) for valor in valores)
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()


def _utc(valor: datetime) -> datetime:
    if valor.tzinfo is None or valor.utcoffset() is None:
        return valor.replace(tzinfo=timezone.utc)
    return valor.astimezone(timezone.utc)


@dataclass(frozen=True, kw_only=True)
class VinculoPixAberto:
    pagamento_id: str
    pedido_id: str
    provedor: str
    id_externo: str
    valor: Decimal
    terminal_id: str
    assinatura_checkout: str
    ocorrido_em: datetime


def registrar_vinculo_cobranca_pix(
    *,
    session: Session,
    contexto: ContextoExecucao,
    pagamento_id: str,
    pedido_id: str,
    valor: Decimal,
    provedor: str,
    id_externo: str,
    idempotency_key: str,
    timestamp: datetime | None = None,
    terminal_id: str | None = None,
    assinatura_checkout: str | None = None,
) -> TransacaoPagamento:
    """Registra cobrança externa sem depender de ``st.session_state``.

    A operação é idempotente por escopo. Se o pagamento ainda não existir, cria a
    obrigação financeira V1 e seu agregado pendente antes de registrar o vínculo
    externo. ``terminal_id`` e ``assinatura_checkout`` permitem recuperar uma
    cobrança aberta mesmo depois de a sessão do navegador desaparecer.
    """

    instante = timestamp or _agora_utc()
    if instante.tzinfo is None or instante.utcoffset() is None:
        raise ValueError("timestamp deve conter timezone")
    provedor_norm = provedor.strip().casefold()
    id_externo_norm = id_externo.strip()
    terminal_norm = (terminal_id or "").strip()
    assinatura_norm = (assinatura_checkout or "").strip()
    if not pagamento_id.strip() or not pedido_id.strip():
        raise ValueError("pagamento_id e pedido_id são obrigatórios")
    if valor <= 0:
        raise ValueError("valor Pix deve ser positivo")
    if not provedor_norm or not id_externo_norm:
        raise ValueError("provedor e id_externo são obrigatórios")
    if bool(terminal_norm) != bool(assinatura_norm):
        raise ValueError("terminal e assinatura devem ser informados em conjunto")

    repo = RepositorioPagamentosSQLAlchemy(session)
    pagamento = repo.buscar_pagamento(
        contexto.tenant_id,
        contexto.unidade_id,
        pagamento_id,
    )
    if pagamento is None:
        criar_obrigacao_pagamento(
            contexto=contexto,
            repositorio=repo,
            pagamento_id=pagamento_id,
            pedido_id=pedido_id,
            valor_previsto=Dinheiro(valor, "BRL"),
            metodo=MetodoPagamento.PIX,
            idempotency_key=f"pix-obrigacao:{pagamento_id}",
            timestamp=instante,
            provedor=provedor_norm,
        )
        pagamento = repo.buscar_pagamento(
            contexto.tenant_id,
            contexto.unidade_id,
            pagamento_id,
        )
    if pagamento is None:
        raise RuntimeError("pagamento Pix não foi persistido")

    existentes = repo.listar_transacoes(
        contexto.tenant_id,
        contexto.unidade_id,
        pagamento_id,
    )
    repetida = next(
        (
            transacao
            for transacao in existentes
            if transacao.provedor == provedor_norm
            and transacao.id_externo == id_externo_norm
            and transacao.tipo is TipoTransacao.INICIACAO
        ),
        None,
    )
    if repetida is not None:
        return repetida

    payload_resumo = [("origem", "pix_control_plane")]
    if terminal_norm:
        payload_resumo.extend(
            (
                ("terminal_id", terminal_norm),
                ("assinatura_checkout", assinatura_norm),
            )
        )

    transacao = TransacaoPagamento(
        transacao_id=str(uuid4()),
        pagamento_id=pagamento.id,
        tenant_id=pagamento.tenant_id,
        unidade_id=pagamento.unidade_id,
        tipo=TipoTransacao.INICIACAO,
        status=StatusTransacao.PENDENTE,
        valor=Dinheiro(valor, pagamento.moeda),
        metodo=MetodoPagamento.PIX,
        provedor=provedor_norm,
        id_externo=id_externo_norm,
        idempotency_key=idempotency_key,
        occurred_at=instante,
        processada_em=instante,
        correlation_id=contexto.correlation_id,
        causation_id=contexto.causation_id,
        payload_resumo=tuple(payload_resumo),
    )
    fingerprint = _fingerprint(
        pagamento.id,
        valor,
        provedor_norm,
        id_externo_norm,
        idempotency_key,
        terminal_norm,
        assinatura_norm,
    )
    salva = repo.append_transacao(transacao, fingerprint)
    return salva


def recuperar_vinculo_cobranca_pix(
    *,
    session: Session,
    contexto: ContextoExecucao,
    pagamento_id: str,
) -> TransacaoPagamento | None:
    """Recupera o vínculo externo mais recente no escopo tenant/unidade."""

    repo = RepositorioPagamentosSQLAlchemy(session)
    transacoes = repo.listar_transacoes(
        contexto.tenant_id,
        contexto.unidade_id,
        pagamento_id,
    )
    candidatas = tuple(
        transacao
        for transacao in transacoes
        if transacao.metodo is MetodoPagamento.PIX
        and transacao.provedor
        and transacao.id_externo
    )
    if not candidatas:
        return None
    return max(candidatas, key=lambda item: item.occurred_at)


def recuperar_pix_aberto_por_terminal(
    *,
    session: Session,
    contexto: ContextoExecucao,
    terminal_id: str,
    assinatura_checkout: str,
) -> VinculoPixAberto | None:
    """Recupera a cobrança pendente equivalente após perda do session_state.

    A busca exige tenant, unidade, terminal e assinatura funcional do checkout.
    Assim, uma cobrança de outro caixa, outra unidade ou outro carrinho nunca é
    reaproveitada silenciosamente.
    """

    terminal_norm = terminal_id.strip()
    assinatura_norm = assinatura_checkout.strip()
    if not terminal_norm or not assinatura_norm:
        raise ValueError("terminal e assinatura do checkout são obrigatórios")

    linhas = session.execute(
        select(TransacaoPagamentoORM, PagamentoORM)
        .join(
            PagamentoORM,
            (
                (PagamentoORM.tenant_id == TransacaoPagamentoORM.tenant_id)
                & (PagamentoORM.unidade_id == TransacaoPagamentoORM.unidade_id)
                & (PagamentoORM.id == TransacaoPagamentoORM.pagamento_id)
            ),
        )
        .where(
            TransacaoPagamentoORM.tenant_id == contexto.tenant_id,
            TransacaoPagamentoORM.unidade_id == contexto.unidade_id,
            TransacaoPagamentoORM.tipo == TipoTransacao.INICIACAO.value,
            TransacaoPagamentoORM.metodo == MetodoPagamento.PIX.value,
            TransacaoPagamentoORM.id_externo.is_not(None),
            PagamentoORM.status.in_(("pendente", "parcialmente_pago")),
        )
        .order_by(TransacaoPagamentoORM.occurred_at.desc())
    ).all()

    for transacao_row, pagamento_row in linhas:
        metadata = dict(transacao_row.payload_resumo or {})
        if metadata.get("terminal_id") != terminal_norm:
            continue
        if metadata.get("assinatura_checkout") != assinatura_norm:
            continue
        provedor = (transacao_row.provedor or "").strip().casefold()
        id_externo = (transacao_row.id_externo or "").strip()
        if not provedor or not id_externo:
            continue
        return VinculoPixAberto(
            pagamento_id=transacao_row.pagamento_id,
            pedido_id=pagamento_row.pedido_id,
            provedor=provedor,
            id_externo=id_externo,
            valor=Decimal(str(transacao_row.valor)),
            terminal_id=terminal_norm,
            assinatura_checkout=assinatura_norm,
            ocorrido_em=_utc(transacao_row.occurred_at),
        )
    return None


def confirmar_cobranca_pix_consultada(
    *,
    session: Session,
    contexto: ContextoExecucao,
    pagamento_id: str,
    cobranca: CobrancaPixRuntime,
    timestamp: datetime | None = None,
) -> ResultadoPagamento | None:
    """Persiste liquidação somente após consulta autenticada retornar estado pago.

    Estados pendentes não alteram o agregado financeiro. Quando a consulta é
    confirmada, a liquidação reutiliza a regra canônica de fonte financeira da V1,
    mantendo idempotência, versão otimista e vínculo com a referência externa.
    """

    repo = RepositorioPagamentosSQLAlchemy(session)
    pagamento = repo.buscar_pagamento(
        contexto.tenant_id,
        contexto.unidade_id,
        pagamento_id,
    )
    if pagamento is None:
        raise RuntimeError("pagamento Pix durável não encontrado")

    resultado = confirmar_pix_por_consulta_provedor(
        contexto=contexto,
        repositorio=repo,
        pagamento_id=pagamento_id,
        provedor=cobranca.provedor,
        cobranca=CobrancaProvedor(
            id_externo=cobranca.id_externo,
            status=cobranca.status,
            valor=Dinheiro(cobranca.valor, pagamento.moeda),
        ),
        expected_version=pagamento.versao,
        timestamp=timestamp or _agora_utc(),
    )
    return resultado
