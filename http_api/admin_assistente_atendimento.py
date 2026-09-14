"""Adaptador HTTP fino para a administração do Assistente de Atendimento V1.

Reutiliza a autoridade existente: AssistenteAtendimentoAdmin (Application),
HandoffAssistenteTransacionalV1.
NÃO cria segunda autoridade.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from application.assistente_atendimento_admin import criar_assistente_atendimento_admin
from application.assistente_handoff_transacoes import HandoffAssistenteTransacionalV1
from application.gerente_ia_transacoes import configurar_identidade_assistente_v1
from core.seguranca.auditoria import EventoAuditoria
from core.seguranca.autorizacao import AutorizarAcao
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Permissao
from http_api.auth import AuthSessionRuntime
from infra.assistente_atendimento.canal_estado_sqlalchemy import (
    EncryptedSQLAlchemyChannelStateStore,
)
from infra.seguranca.auditoria_sqlalchemy import RepositorioAuditoriaSQLAlchemy
from infra.seguranca.segredos_sqlalchemy import EncryptedSQLAlchemySecretStore
from infra.transacoes.uow import UnitOfWorkV1


def _erro(http_status: int, codigo: str) -> JSONResponse:
    return JSONResponse(status_code=http_status, content={"erro": codigo})


def _tratar_erro_assistente(exc: Exception) -> JSONResponse:
    if isinstance(exc, PermissionError):
        return _erro(403, str(getattr(exc, "codigo", str(exc) or "seguranca.permissao_insuficiente")))
    if isinstance(exc, LookupError):
        return _erro(404, str(exc) or "admin.nao_encontrado")
    if isinstance(exc, (ValueError, TypeError)):
        return _erro(400, "admin.cadastro_invalido")
    if hasattr(exc, "codigo"):
        codigo = str(exc.codigo)
        if codigo == "configuracao_assistente_desatualizada":
            return _erro(409, codigo)
        return _erro(400, codigo)
    return _erro(503, "admin.assistente_indisponivel")


class IdentidadeAssistenteOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: str
    unidade_id: str
    nome_publico: str
    atributos: dict[str, Any]
    versao: int
    atualizado_em: str | None = None


class IdentidadeAssistentePutIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nome_publico: str
    atributos: dict[str, Any] = {}
    versao_esperada: int | None = None


class ConversaResumoOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    conversa_id: str
    estado: str
    pedido_id: str | None = None
    pagamento_id: str | None = None
    entrega_id: str | None = None
    versao: int
    atualizado_em: str


class ConversasListOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    conversas: list[ConversaResumoOut]


class ConversaDetalheOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    conversa_id: str
    estado: str
    pedido_id: str | None = None
    pagamento_id: str | None = None
    entrega_id: str | None = None
    ultimo_inbound_id: str | None = None
    ultimo_outbound_id: str | None = None
    versao: int
    handoff_contexto: dict[str, Any] | None = None


class HandoffIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    motivo: str


class HandoffOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str
    conversa_id: str
    motivo: str


def _contexto_admin(request: Request, auth_runtime: AuthSessionRuntime) -> ContextoExecucao:
    identidade = auth_runtime.resolver_identidade(request)
    if identidade is None:
        from core.seguranca.erros import CredenciaisInvalidas
        raise CredenciaisInvalidas("credenciais invalidas")
    if Permissao.ADMIN_ACESSAR not in identidade.permissoes:
        raise PermissionError("seguranca.admin_acesso_exigido")
    return identidade.contexto(
        origem=request.headers.get("x-correlation-id") or "admin_assistente_atendimento_http_v1",
        correlation_id=request.headers.get("x-correlation-id") or None,
    )


def _contexto_admin_step_up(request: Request, auth_runtime: AuthSessionRuntime) -> ContextoExecucao:
    identidade = auth_runtime.resolver_identidade(request)
    if identidade is None:
        from core.seguranca.erros import CredenciaisInvalidas
        raise CredenciaisInvalidas("credenciais invalidas")
    if Permissao.ADMIN_ACESSAR not in identidade.permissoes:
        raise PermissionError("seguranca.admin_acesso_exigido")
    _, elevado, _ = auth_runtime.admin_status(request)
    if not elevado:
        raise PermissionError("seguranca.admin_step_up_exigido")
    return identidade.contexto(
        origem=request.headers.get("x-correlation-id") or "admin_assistente_atendimento_http_v1.mutacao",
        correlation_id=request.headers.get("x-correlation-id") or None,
    )


def build_admin_assistente_atendimento_router(
    *,
    session_factory: Callable[[], Session],
    auth_runtime: AuthSessionRuntime,
    master_key: str | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/v1/admin/assistente-atendimento", tags=["admin-assistente-atendimento"])

    admin_svc = criar_assistente_atendimento_admin(
        session_factory=session_factory,
        master_key=master_key,
    )

    @router.get("/identidade", response_model=None)
    def obter_identidade(request: Request) -> IdentidadeAssistenteOut | JSONResponse:
        try:
            contexto = _contexto_admin(request, auth_runtime)
            decisao = AutorizarAcao().executar(
                contexto=contexto,
                permissao=Permissao.ATENDIMENTO_VISUALIZAR,
                recurso="identidade_assistente_atendimento",
                tenant_recurso=contexto.tenant_id,
                unidade_recurso=contexto.unidade_id,
            )
            if not decisao.autorizado:
                raise PermissionError(decisao.codigo)

            identidade = admin_svc.obter_identidade(contexto=contexto)
            return IdentidadeAssistenteOut(
                tenant_id=identidade.tenant_id,
                unidade_id=identidade.unidade_id,
                nome_publico=identidade.nome_publico,
                atributos=dict(identidade.atributos),
                versao=identidade.versao,
                atualizado_em=str(identidade.atualizado_em) if identidade.atualizado_em else None,
            )
        except Exception as exc:  # noqa: BLE001
            return _tratar_erro_assistente(exc)

    @router.put("/identidade", response_model=None)
    def configurar_identidade(payload: IdentidadeAssistentePutIn, request: Request) -> IdentidadeAssistenteOut | JSONResponse:
        try:
            identidade_http = auth_runtime.resolver_identidade(request)
            if identidade_http is None:
                from core.seguranca.erros import CredenciaisInvalidas
                raise CredenciaisInvalidas("credenciais invalidas")
            if Permissao.ADMIN_ACESSAR not in identidade_http.permissoes:
                raise PermissionError("seguranca.admin_acesso_exigido")
            _, elevado, _ = auth_runtime.admin_status(request)
            if not elevado:
                raise PermissionError("seguranca.admin_step_up_exigido")

            _ = identidade_http.contexto(
                origem=request.headers.get("x-correlation-id") or "admin_assistente_atendimento_http_v1.configurar",
                correlation_id=request.headers.get("x-correlation-id") or None,
            )

            identidade = configurar_identidade_assistente_v1(
                session_factory=session_factory,
                secret_store=EncryptedSQLAlchemySecretStore(next(session_factory()), master_key=master_key),
                email=identidade_http.email,
                password=identidade_http.senha_hash or "",
                origem="admin_http_v1",
                correlation_id=request.headers.get("x-correlation-id"),
                nome_publico=payload.nome_publico,
                atributos=payload.atributos,
                versao_esperada=payload.versao_esperada,
            )
            return IdentidadeAssistenteOut(
                tenant_id=identidade.tenant_id,
                unidade_id=identidade.unidade_id,
                nome_publico=identidade.nome_publico,
                atributos=dict(identidade.atributos),
                versao=identidade.versao,
                atualizado_em=str(identidade.atualizado_em) if identidade.atualizado_em else None,
            )
        except Exception as exc:  # noqa: BLE001
            return _tratar_erro_assistente(exc)

    @router.get("/conversas", response_model=None)
    def listar_conversas(request: Request) -> ConversasListOut | JSONResponse:
        try:
            contexto = _contexto_admin(request, auth_runtime)
            decisao = AutorizarAcao().executar(
                contexto=contexto,
                permissao=Permissao.ATENDIMENTO_VISUALIZAR,
                recurso="conversa_atendimento",
                tenant_recurso=contexto.tenant_id,
                unidade_recurso=contexto.unidade_id,
            )
            if not decisao.autorizado:
                raise PermissionError(decisao.codigo)

            with session_factory() as session:
                rows = session.execute(
                    """
                    SELECT conversa_id, estado, pedido_id, pagamento_id, entrega_id, versao, atualizado_em
                    FROM assistente_canal_conversas_v1
                    WHERE tenant_id = :tenant_id AND unidade_id = :unidade_id
                    ORDER BY atualizado_em DESC
                    LIMIT 100
                    """,
                    {"tenant_id": contexto.tenant_id, "unidade_id": contexto.unidade_id},
                ).mappings().all()

            conversas = [
                ConversaResumoOut(
                    conversa_id=str(row["conversa_id"]),
                    estado=str(row["estado"]),
                    pedido_id=str(row["pedido_id"]) if row["pedido_id"] else None,
                    pagamento_id=str(row["pagamento_id"]) if row["pagamento_id"] else None,
                    entrega_id=str(row["entrega_id"]) if row["entrega_id"] else None,
                    versao=int(row["versao"]),
                    atualizado_em=str(row["atualizado_em"]),
                )
                for row in rows
            ]
            return ConversasListOut(conversas=conversas)
        except Exception as exc:  # noqa: BLE001
            return _tratar_erro_assistente(exc)

    @router.get("/conversas/{conversa_id}", response_model=None)
    def obter_conversa(conversa_id: str, request: Request) -> ConversaDetalheOut | JSONResponse:
        try:
            contexto = _contexto_admin(request, auth_runtime)
            decisao = AutorizarAcao().executar(
                contexto=contexto,
                permissao=Permissao.ATENDIMENTO_VISUALIZAR,
                recurso="conversa_atendimento",
                tenant_recurso=contexto.tenant_id,
                unidade_recurso=contexto.unidade_id,
            )
            if not decisao.autorizado:
                raise PermissionError(decisao.codigo)

            estado_canal = admin_svc.obter_estado_canal(contexto=contexto, conversa_id=conversa_id)
            if estado_canal is None:
                return _erro(404, "conversa_nao_encontrada")

            handoff = HandoffAssistenteTransacionalV1(session_factory)
            contexto_handoff = handoff.ultimo_contexto(contexto=contexto, conversa_id=conversa_id)

            return ConversaDetalheOut(
                conversa_id=estado_canal.conversa_id,
                estado=estado_canal.estado,
                pedido_id=estado_canal.pedido_id,
                pagamento_id=estado_canal.pagamento_id,
                entrega_id=estado_canal.entrega_id,
                ultimo_inbound_id=estado_canal.ultimo_inbound_id,
                ultimo_outbound_id=estado_canal.ultimo_outbound_id,
                versao=estado_canal.versao,
                handoff_contexto=contexto_handoff,
            )
        except Exception as exc:  # noqa: BLE001
            return _tratar_erro_assistente(exc)

    @router.post("/conversas/{conversa_id}/handoff", response_model=None)
    def forcar_handoff(conversa_id: str, payload: HandoffIn, request: Request) -> HandoffOut | JSONResponse:
        try:
            identidade_http = auth_runtime.resolver_identidade(request)
            if identidade_http is None:
                from core.seguranca.erros import CredenciaisInvalidas
                raise CredenciaisInvalidas("credenciais invalidas")
            if Permissao.ADMIN_ACESSAR not in identidade_http.permissoes:
                raise PermissionError("seguranca.admin_acesso_exigido")
            _, elevado, _ = auth_runtime.admin_status(request)
            if not elevado:
                raise PermissionError("seguranca.admin_step_up_exigido")

            contexto = identidade_http.contexto(
                origem=request.headers.get("x-correlation-id") or "admin_assistente_atendimento_http_v1.handoff",
                correlation_id=request.headers.get("x-correlation-id") or None,
            )

            decisao = AutorizarAcao().executar(
                contexto=contexto,
                permissao=Permissao.ATENDIMENTO_GERENCIAR,
                recurso="conversa_atendimento",
                tenant_recurso=contexto.tenant_id,
                unidade_recurso=contexto.unidade_id,
            )
            if not decisao.autorizado:
                raise PermissionError(decisao.codigo)

            with session_factory() as session:
                uow = UnitOfWorkV1.adotar_session(session)
                try:
                    handoff = HandoffAssistenteTransacionalV1(session_factory)
                    handoff.registrar(
                        contexto=contexto,
                        conversa_id=conversa_id,
                        motivo=payload.motivo,
                        metadata_segura={"forcado_por": "administrador", "email": identidade_http.email},
                    )
                    store = EncryptedSQLAlchemyChannelStateStore(session)
                    estado = store.obter_por_conversa(contexto=contexto, conversa_id=conversa_id)
                    if estado is not None:
                        store.salvar(
                            contexto=contexto,
                            canal="whatsapp",
                            recipient=estado.recipient,
                            conversa_id=conversa_id,
                            estado="handoff_humano",
                            state=estado.state,
                            pedido_id=estado.pedido_id,
                            pagamento_id=estado.pagamento_id,
                            entrega_id=estado.entrega_id,
                            versao_esperada=estado.versao,
                        )
                    auditoria = RepositorioAuditoriaSQLAlchemy(session)
                    auditoria.adicionar(EventoAuditoria(
                        audit_id=f"audit-{hash(conversa_id)}",
                        tenant_id=contexto.tenant_id,
                        unidade_id=contexto.unidade_id,
                        usuario_id=contexto.usuario_id,
                        papel_efetivo=min(contexto.papeis, key=lambda p: p.value) if contexto.papeis else None,
                        acao="assistente_atendimento.handoff_forcado",
                        recurso_tipo="conversa_atendimento",
                        recurso_id=conversa_id,
                        resultado="sucesso",
                        motivo=payload.motivo,
                        correlation_id=contexto.correlation_id,
                    ))
                    uow.commit()
                except Exception:
                    uow.rollback()
                    raise
                finally:
                    session.close()

            return HandoffOut(status="handoff_registrado", conversa_id=conversa_id, motivo=payload.motivo)
        except Exception as exc:  # noqa: BLE001
            return _tratar_erro_assistente(exc)

    return router