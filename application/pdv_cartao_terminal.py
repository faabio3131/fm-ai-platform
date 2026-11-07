"""Conciliação de cartão presencial com terminal externo e comprovante.

Não captura cartão, não processa PAN/CVV e não finge aprovação bancária. O
operador atesta autorização já realizada no dispositivo físico e fornece
referência auditável (NSU/autorização) antes de fechar o pagamento canônico.
"""
from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from application.finalizacao_pagamento import finalizar_pagamento_liquidado_em_transacao
from core.pagamentos.modelos import MetodoPagamento, TipoTransacao
from core.pagamentos.servicos import confirmar_pagamento_presencial
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Permissao
from infra.transacoes.uow import UnitOfWorkV1

_CARTOES = frozenset({MetodoPagamento.CARTAO_CREDITO, MetodoPagamento.CARTAO_DEBITO})
_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9./_-]{3,79}$")


class CartaoTerminalInvalido(ValueError):
    """Inconsistência de confirmação presencial."""


@dataclass(frozen=True)
class ConfirmacaoCartaoTerminal:
    pagamento_id: str
    status: str
    metodo: str
    referencia_terminal: str
    idempotente: bool


def confirmar_cartao_terminal_pdv(
    *,
    contexto: ContextoExecucao,
    pagamento_id: str,
    referencia_terminal: str,
    autorizado_no_terminal: bool,
    session_factory: Callable[[], Session],
) -> ConfirmacaoCartaoTerminal:
    if not {Permissao.PDV_OPERAR, Permissao.PAGAMENTO_CONFIRMAR}.issubset(
        contexto.permissoes
    ):
        raise PermissionError("seguranca.cartao_confirmar_permissao_exigida")
    referencia = referencia_terminal.strip().upper()
    if not autorizado_no_terminal or not _REF.fullmatch(referencia):
        raise CartaoTerminalInvalido("cartao_requer_aprovacao_e_nsu")
    if not pagamento_id.strip():
        raise CartaoTerminalInvalido("pagamento_id_invalido")
    chave = "pdv-terminal:" + hashlib.sha256(
        f"{contexto.tenant_id}:{contexto.unidade_id}:{pagamento_id}:"
        f"{referencia}".encode("utf-8")
    ).hexdigest()
    with UnitOfWorkV1(session_factory) as uow:
        pagamento = uow.pagamentos.buscar_pagamento(
            contexto.tenant_id, contexto.unidade_id, pagamento_id
        )
        if pagamento is None:
            raise LookupError("pagamento_nao_encontrado")
        if pagamento.metodo not in _CARTOES:
            raise CartaoTerminalInvalido("pagamento_nao_e_cartao")
        anteriores = uow.pagamentos.listar_transacoes(
            contexto.tenant_id, contexto.unidade_id, pagamento_id
        )
        if any(
            t.tipo is TipoTransacao.INICIACAO
            and t.provedor == "pagbank_checkout"
            for t in anteriores
        ):
            raise CartaoTerminalInvalido(
                "checkout_online_ativo_nao_pode_ser_confirmado_com_nsu"
            )
        if pagamento.saldo.valor == 0:
            if not any(
                t.tipo is TipoTransacao.CONFIRMACAO
                and t.idempotency_key == chave
                and t.id_externo == referencia
                for t in anteriores
            ):
                raise CartaoTerminalInvalido("pagamento_quitado_com_outra_referencia")
            return ConfirmacaoCartaoTerminal(
                pagamento_id=pagamento_id,
                status=pagamento.status.value,
                metodo=pagamento.metodo.value,
                referencia_terminal=referencia,
                idempotente=True,
            )
        agora = datetime.now(timezone.utc)
        resultado = confirmar_pagamento_presencial(
            contexto=contexto,
            repositorio=uow.pagamentos,
            pagamento_id=pagamento_id,
            valor=pagamento.saldo,
            metodo=pagamento.metodo,
            idempotency_key=chave,
            expected_version=pagamento.versao,
            timestamp=agora,
            referencia_externa=referencia,
        )
        if not resultado.idempotente:
            uow.registrar_efeitos(
                eventos=resultado.eventos,
                auditorias=resultado.auditorias,
            )
        finalizar_pagamento_liquidado_em_transacao(
            recursos=uow.recursos,
            pagamento=resultado.pagamento,
            timestamp=agora,
        )
        uow.commit()
        return ConfirmacaoCartaoTerminal(
            pagamento_id=pagamento_id,
            status=resultado.pagamento.status.value,
            metodo=pagamento.metodo.value,
            referencia_terminal=referencia,
            idempotente=resultado.idempotente,
        )
