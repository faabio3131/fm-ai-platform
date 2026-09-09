"""Adaptador HTTP fino para Clientes e Cashback canônicos da V1."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from application.crm_cashback_comercial import (
    CashbackComercialInvalido,
    creditar_cashback_manual,
)
from core.crm.erros import ErroCRM
from core.seguranca.autenticacao import IdentidadeUsuario
from core.seguranca.erros import CredenciaisInvalidas, ErroSeguranca
from core.seguranca.permissoes import Permissao
from http_api.auth import AuthSessionRuntime
from http_api.operational_auth import obter_identidade_operacional
from infra.crm.cashback_sqlalchemy import RepositorioCashbackSQLAlchemy
from infra.crm.cliente_legado_schema import crm_cliente_legado_v1
from infra.crm.clientes_sqlalchemy import LeitorClientesCRMSQLAlchemy
from infra.legacy_schema import clientes as clientes_legados

SessionFactory = Callable[[], Session]
_MAX_IDEMPOTENCY_KEY = 96


class CreditoCashbackIn(BaseModel):
    valor: Decimal = Field(gt=0)


def _erro(http_status: int, codigo: str) -> JSONResponse:
    return JSONResponse(status_code=http_status, content={"erro": codigo})


def _idempotency_key(request: Request) -> str:
    key = request.headers.get("idempotency-key", "").strip()
    if not key:
        raise ValueError("idempotency_key_obrigatoria")
    if len(key) > _MAX_IDEMPOTENCY_KEY:
        raise ValueError("idempotency_key_excede_limite")
    return key


def _identidade(
    request: Request,
    session: Session,
    *,
    auth_runtime: AuthSessionRuntime,
) -> tuple[IdentidadeUsuario, str]:
    resolvida = obter_identidade_operacional(
        request,
        session,
        auth_runtime=auth_runtime,
    )
    return resolvida.identidade, resolvida.modo


def _exigir(
    identidade: IdentidadeUsuario,
    *permissoes: Permissao,
) -> None:
    ausentes = [
        permissao.value
        for permissao in permissoes
        if permissao not in identidade.permissoes
    ]
    if ausentes:
        raise PermissionError("seguranca.permissao_insuficiente")


def _tratar_erro(exc: Exception) -> JSONResponse:
    if isinstance(exc, CredenciaisInvalidas):
        return _erro(status.HTTP_401_UNAUTHORIZED, "credenciais_invalidas")
    if isinstance(exc, (ErroSeguranca, PermissionError)):
        return _erro(
            status.HTTP_403_FORBIDDEN,
            str(getattr(exc, "codigo", str(exc) or "seguranca.permissao_insuficiente")),
        )
    if isinstance(exc, ValueError):
        return _erro(status.HTTP_400_BAD_REQUEST, str(exc) or "crm.entrada_invalida")
    if isinstance(exc, CashbackComercialInvalido):
        return _erro(status.HTTP_409_CONFLICT, str(exc))
    if isinstance(exc, ErroCRM):
        return _erro(status.HTTP_400_BAD_REQUEST, str(exc))
    return _erro(status.HTTP_503_SERVICE_UNAVAILABLE, "crm.indisponivel")


def _legacy_por_cliente(
    session: Session,
    *,
    tenant_id: str,
    unidade_id: str,
) -> dict[str, dict[str, Any]]:
    rows = session.execute(
        select(
            crm_cliente_legado_v1.c.cliente_id,
            crm_cliente_legado_v1.c.legacy_cliente_id,
            clientes_legados.c.nome,
            clientes_legados.c.whatsapp,
            clientes_legados.c.ultima_compra,
            clientes_legados.c.total_gasto,
            clientes_legados.c.status,
        )
        .join(
            clientes_legados,
            clientes_legados.c.id == crm_cliente_legado_v1.c.legacy_cliente_id,
        )
        .where(
            crm_cliente_legado_v1.c.tenant_id == tenant_id,
            crm_cliente_legado_v1.c.unidade_id == unidade_id,
        )
    ).mappings()
    return {
        str(row["cliente_id"]): {
            "legacy_cliente_id": int(row["legacy_cliente_id"]),
            "nome": str(row["nome"] or ""),
            "whatsapp": str(row["whatsapp"] or ""),
            "ultima_compra": row["ultima_compra"],
            "total_gasto": str(
                Decimal(str(row["total_gasto"] or 0)).quantize(Decimal("0.01"))
            ),
            "status": str(row["status"] or ""),
        }
        for row in rows
    }


def _cliente_out(
    cliente: Any,
    *,
    legado: dict[str, Any] | None,
    saldo: Decimal,
) -> dict[str, Any]:
    return {
        "cliente_id": cliente.cliente_id,
        "origem": cliente.origem.value,
        "canais": [contato.canal.value for contato in cliente.contatos],
        "criado_em": cliente.criado_em.isoformat(),
        "versao": cliente.versao,
        "saldo_cashback": str(saldo),
        "legacy_cliente_id": legado["legacy_cliente_id"] if legado else None,
        "nome": legado["nome"] if legado else None,
        "whatsapp": legado["whatsapp"] if legado else None,
        "ultima_compra": (
            legado["ultima_compra"].isoformat()
            if legado and legado["ultima_compra"] is not None
            else None
        ),
        "total_gasto": legado["total_gasto"] if legado else None,
        "status": legado["status"] if legado else None,
    }


def _movimento_out(movimento: Any) -> dict[str, Any]:
    return {
        "movimento_id": movimento.movimento_id,
        "tipo": movimento.tipo.value,
        "valor": str(movimento.valor),
        "origem": movimento.origem,
        "referencia": movimento.referencia,
        "ocorrido_em": movimento.ocorrido_em.isoformat(),
    }


def build_crm_router(
    *,
    session_factory: SessionFactory,
    auth_runtime: AuthSessionRuntime,
) -> APIRouter:
    router = APIRouter(prefix="/v1/crm", tags=["crm"])

    @router.get("/clientes", response_model=None)
    def listar_clientes(request: Request) -> dict[str, Any] | JSONResponse:
        try:
            with session_factory() as session:
                identidade, _ = _identidade(
                    request,
                    session,
                    auth_runtime=auth_runtime,
                )
                _exigir(identidade, Permissao.CLIENTE_VISUALIZAR)
                clientes = LeitorClientesCRMSQLAlchemy(session).listar(
                    tenant_id=identidade.tenant_id,
                    unidade_id=identidade.unidade_id,
                )
                legados = _legacy_por_cliente(
                    session,
                    tenant_id=identidade.tenant_id,
                    unidade_id=identidade.unidade_id,
                )
                cashback = RepositorioCashbackSQLAlchemy(session)
                itens = [
                    _cliente_out(
                        cliente,
                        legado=legados.get(cliente.cliente_id),
                        saldo=cashback.saldo(
                            tenant_id=identidade.tenant_id,
                            unidade_id=identidade.unidade_id,
                            cliente_id=cliente.cliente_id,
                        ),
                    )
                    for cliente in clientes
                ]
            return {
                "itens": itens,
                "saldo_total": str(
                    sum(
                        (Decimal(item["saldo_cashback"]) for item in itens),
                        Decimal("0.00"),
                    )
                ),
            }
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _tratar_erro(exc)

    @router.get("/clientes/{cliente_id}/cashback", response_model=None)
    def consultar_cashback(
        cliente_id: str,
        request: Request,
    ) -> dict[str, Any] | JSONResponse:
        try:
            with session_factory() as session:
                identidade, _ = _identidade(
                    request,
                    session,
                    auth_runtime=auth_runtime,
                )
                _exigir(identidade, Permissao.CLIENTE_VISUALIZAR)
                cliente = LeitorClientesCRMSQLAlchemy(session).obter(
                    tenant_id=identidade.tenant_id,
                    unidade_id=identidade.unidade_id,
                    cliente_id=cliente_id,
                )
                if cliente is None:
                    return _erro(
                        status.HTTP_404_NOT_FOUND, "crm.cliente_nao_encontrado"
                    )
                cashback = RepositorioCashbackSQLAlchemy(session)
                saldo = cashback.saldo(
                    tenant_id=identidade.tenant_id,
                    unidade_id=identidade.unidade_id,
                    cliente_id=cliente_id,
                )
                historico = cashback.historico(
                    tenant_id=identidade.tenant_id,
                    unidade_id=identidade.unidade_id,
                    cliente_id=cliente_id,
                )
            return {
                "cliente_id": cliente_id,
                "saldo": str(saldo),
                "movimentos": [_movimento_out(movimento) for movimento in historico],
            }
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _tratar_erro(exc)

    @router.post("/clientes/{cliente_id}/cashback/creditos", response_model=None)
    def creditar_cashback(
        cliente_id: str,
        payload: CreditoCashbackIn,
        request: Request,
    ) -> dict[str, Any] | JSONResponse:
        try:
            key = _idempotency_key(request)
            with session_factory() as session:
                identidade, modo = _identidade(
                    request,
                    session,
                    auth_runtime=auth_runtime,
                )
                _exigir(identidade, Permissao.CLIENTE_EDITAR)
                if modo == "session":
                    _exigir(identidade, Permissao.ADMIN_ACESSAR)
                    _, elevado, _ = auth_runtime.admin_status(request)
                    if not elevado:
                        raise PermissionError("seguranca.admin_step_up_exigido")
                legacy_cliente_id = session.scalar(
                    select(crm_cliente_legado_v1.c.legacy_cliente_id).where(
                        crm_cliente_legado_v1.c.tenant_id == identidade.tenant_id,
                        crm_cliente_legado_v1.c.unidade_id == identidade.unidade_id,
                        crm_cliente_legado_v1.c.cliente_id == cliente_id,
                    )
                )
            if legacy_cliente_id is None:
                return _erro(status.HTTP_409_CONFLICT, "cliente_legado_sem_mapping_crm")
            resultado = creditar_cashback_manual(
                session_factory=session_factory,
                tenant_id=identidade.tenant_id,
                unidade_id=identidade.unidade_id,
                legacy_cliente_id=int(legacy_cliente_id),
                valor=payload.valor,
                referencia=f"crm-http://bonus/{identidade.usuario_id}",
                idempotency_key=key,
            )
            return {
                "cliente_id": resultado.cliente_id,
                "legacy_cliente_id": resultado.legacy_cliente_id,
                "saldo": str(resultado.saldo),
            }
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _tratar_erro(exc)

    return router
