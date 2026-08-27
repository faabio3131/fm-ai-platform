"""Caso de uso de despacho de alertas internos tenant-safe."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from core.notificacoes_internas.adapters import (
    PortaDiretorioNotificacoesInternas,
    PortaEntregaNotificacaoInterna,
)
from core.seguranca.auditoria import (
    EventoAuditoria,
    RepositorioAuditoria,
    sanitizar_metadata,
)
from core.seguranca.contexto import ContextoExecucao
from infra.integracoes.idempotencia_alertas import (
    chave_idempotencia_alerta_estoque_scoped,
)


@dataclass(frozen=True)
class ResultadoDespachoNotificacaoInterna:
    destinatario_id: str
    enviado: bool
    mensagem_id: str | None
    motivo: str


def _audit_id(
    *,
    contexto: ContextoExecucao,
    destinatario_id: str,
    idempotency_key: str,
) -> str:
    digest = hashlib.sha256(
        (
            f"{contexto.tenant_id}:{contexto.unidade_id}:"
            f"{destinatario_id}:{idempotency_key}"
        ).encode("utf-8")
    ).hexdigest()[:24]
    return f"audit_notif_envio_{digest}"


def _auditar(
    *,
    auditoria: RepositorioAuditoria | None,
    contexto: ContextoExecucao,
    destinatario_id: str,
    idempotency_key: str,
    enviado: bool,
) -> None:
    if auditoria is None:
        return
    auditoria.adicionar(
        EventoAuditoria(
            audit_id=_audit_id(
                contexto=contexto,
                destinatario_id=destinatario_id,
                idempotency_key=idempotency_key,
            ),
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
            usuario_id=contexto.usuario_id,
            papel_efetivo=next(iter(contexto.papeis), None),
            acao="notificacao_interna.alerta_estoque_despachar",
            recurso_tipo="DestinatarioNotificacaoInterna",
            recurso_id=destinatario_id,
            resultado="sucesso" if enviado else "falha",
            motivo="alerta_estoque",
            correlation_id=contexto.correlation_id,
            timestamp=datetime.now(timezone.utc),
            origem="application.notificacoes_internas",
            politica="sd_adr_006",
            metadata=sanitizar_metadata(
                {
                    "finalidade": "alerta_estoque",
                    "enviado": enviado,
                    "idempotency_key": idempotency_key,
                },
                rejeitar=True,
            ),
        )
    )


def despachar_alerta_estoque(
    *,
    contexto: ContextoExecucao,
    diretorio: PortaDiretorioNotificacoesInternas,
    entrega: PortaEntregaNotificacaoInterna,
    alerta: Mapping[str, Any],
    texto: str,
    data_referencia: date,
    auditoria: RepositorioAuditoria | None = None,
) -> tuple[ResultadoDespachoNotificacaoInterna, ...]:
    if not texto.strip():
        raise ValueError("texto de alerta obrigatorio")

    destinatarios = diretorio.listar_alertas_estoque(
        contexto=contexto,
    )
    resultados: list[ResultadoDespachoNotificacaoInterna] = []
    for destinatario in destinatarios:
        idempotency_key = chave_idempotencia_alerta_estoque_scoped(
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
            destinatario_id=destinatario.destinatario_id,
            alerta=alerta,
            data_referencia=data_referencia,
        )
        try:
            mensagem_id = entrega.enviar(
                contexto=contexto,
                referencia_contato=destinatario.referencia_contato,
                texto=texto,
                idempotency_key=idempotency_key,
            )
        except Exception:
            _auditar(
                auditoria=auditoria,
                contexto=contexto,
                destinatario_id=destinatario.destinatario_id,
                idempotency_key=idempotency_key,
                enviado=False,
            )
            resultados.append(
                ResultadoDespachoNotificacaoInterna(
                    destinatario_id=destinatario.destinatario_id,
                    enviado=False,
                    mensagem_id=None,
                    motivo="falha_provedor",
                )
            )
            continue

        _auditar(
            auditoria=auditoria,
            contexto=contexto,
            destinatario_id=destinatario.destinatario_id,
            idempotency_key=idempotency_key,
            enviado=True,
        )
        resultados.append(
            ResultadoDespachoNotificacaoInterna(
                destinatario_id=destinatario.destinatario_id,
                enviado=True,
                mensagem_id=mensagem_id,
                motivo="enviado",
            )
        )
    return tuple(resultados)
