"""Adaptador HTTP fino para Almoxarifado e Validades legados da V1."""

from __future__ import annotations

import io
from collections.abc import Callable, Sequence
from datetime import date, datetime
from typing import Any, cast

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from application.legacy_estoque_forecasting import AplicacaoForecastingEstoqueV1
from application.legacy_estoque_leitura_visual import AplicacaoLeituraVisualEstoqueV1
from application.legacy_estoque_transacoes import AplicacaoLegacyEstoqueV1
from core.seguranca.autenticacao import IdentidadeUsuario
from core.seguranca.erros import (
    CredenciaisInvalidas,
    ErroSeguranca,
    ReferenciaSegredoInvalida,
    SegredoAusente,
)
from core.seguranca.permissoes import Permissao
from core.seguranca.segredos import SecretStore
from gemini_config import generate_content as real_generate_content
from http_api.auth import AuthSessionRuntime
from http_api.operational_auth import obter_identidade_operacional
from infra.integracoes.fabrica_adapters import FabricaAdaptersExternos
from infra.legacy_expiration_alert import status_validade_legado
from infra.legacy_product_scope import (
    ErroEscopoLojaLegada,
    listar_insumos_legados,
    obter_insumo_por_id_legado,
)
from infra.legacy_schema import contatos_gerenciais
from test_mode import is_test_mode, mock_generate_content, mock_whatsapp_send

SessionFactory = Callable[[], Session]
generate_content = mock_generate_content if is_test_mode() else real_generate_content


class InsumoCreateIn(BaseModel):
    nome: str = Field(min_length=1, max_length=240)
    unidade_medida: str = Field(min_length=1, max_length=32)
    saldo_atual: float = Field(ge=0)
    estoque_minimo: float = Field(ge=0)
    custo_unitario: float = Field(ge=0)
    data_fabricacao: date | datetime | None = None
    data_validade: date | datetime | None = None
    dias_alerta_vencimento: int = Field(ge=1, le=3650)


class ItemLeituraLoteIn(BaseModel):
    nome: str = Field(min_length=1, max_length=240)
    quantidade: float = Field(gt=0)
    unidade: str = Field(default="un", min_length=1, max_length=32)
    data_validade: date | datetime | None = None


class LeituraLoteIn(BaseModel):
    itens: list[ItemLeituraLoteIn] = Field(min_length=1, max_length=500)


def _erro(http_status: int, codigo: str) -> JSONResponse:
    return JSONResponse(status_code=http_status, content={"erro": codigo})


def _dto_insumo(row: Any) -> dict[str, object]:
    mapping = row._mapping
    saldo = float(mapping.get("saldo_atual") or 0.0)
    minimo = float(mapping.get("estoque_minimo") or 0.0)
    custo = float(mapping.get("custo_unitario") or 0.0)
    validade = mapping.get("data_validade")
    fabricacao = mapping.get("data_fabricacao")
    dias_alerta = int(mapping.get("dias_alerta_vencimento") or 15)
    return {
        "id": str(mapping["id"]),
        "nome": str(mapping.get("nome") or ""),
        "unidade_medida": str(mapping.get("unidade_medida") or "un"),
        "saldo_atual": saldo,
        "estoque_minimo": minimo,
        "custo_unitario": custo,
        "valor_total": saldo * custo,
        "data_fabricacao": (
            fabricacao.isoformat() if fabricacao is not None else None
        ),
        "data_validade": validade.isoformat() if validade is not None else None,
        "dias_alerta_vencimento": dias_alerta,
        "status_estoque": "reposicao" if saldo < minimo else "ok",
        "status_validade": status_validade_legado(
            data_validade=validade,
            dias_alerta_vencimento=dias_alerta,
        ),
    }


def build_estoque_router(
    *,
    session_factory: SessionFactory,
    auth_runtime: AuthSessionRuntime,
    whatsapp_secret_store_factory: Callable[[Session], SecretStore],
) -> APIRouter:
    router = APIRouter(prefix="/v1/estoque", tags=["estoque"])
    aplicacao = AplicacaoLegacyEstoqueV1(session_factory)
    aplicacao_forecasting = AplicacaoForecastingEstoqueV1()
    aplicacao_leitura_visual = AplicacaoLeituraVisualEstoqueV1(aplicacao)

    def _identidade(request: Request) -> tuple[IdentidadeUsuario, str]:
        with session_factory() as session:
            resolvida = obter_identidade_operacional(
                request,
                session,
                auth_runtime=auth_runtime,
            )
        return resolvida.identidade, resolvida.modo

    def _contexto(
        request: Request,
        *,
        permissao: Permissao,
        exigir_step_up: bool,
    ) -> Any:
        identidade, modo = _identidade(request)
        if permissao not in identidade.permissoes:
            raise PermissionError("seguranca.permissao_insuficiente")

        if exigir_step_up and modo == "session":
            if Permissao.ADMIN_ACESSAR not in identidade.permissoes:
                raise PermissionError("seguranca.admin_acesso_exigido")
            _, elevado, _ = auth_runtime.admin_status(request)
            if not elevado:
                raise PermissionError("seguranca.admin_step_up_exigido")

        return identidade.contexto(
            origem="estoque_http_v1",
            correlation_id=request.headers.get("x-correlation-id") or None,
        )

    def _tratar_erro(exc: Exception) -> JSONResponse:
        if isinstance(exc, CredenciaisInvalidas):
            return _erro(status.HTTP_401_UNAUTHORIZED, CredenciaisInvalidas.codigo)
        if isinstance(exc, (PermissionError, ErroSeguranca)):
            return _erro(
                status.HTTP_403_FORBIDDEN,
                str(exc) or "seguranca.permissao_insuficiente",
            )
        if isinstance(exc, (ReferenciaSegredoInvalida, SegredoAusente)):
            return _erro(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "auth.sessao_indisponivel",
            )
        if isinstance(exc, ErroEscopoLojaLegada):
            return _erro(
                status.HTTP_409_CONFLICT,
                "estoque.escopo_indisponivel",
            )
        if isinstance(exc, IntegrityError):
            return _erro(
                status.HTTP_409_CONFLICT,
                "estoque.integridade_impede_operacao",
            )
        raise exc

    def _listar(contexto: Any) -> list[dict[str, object]]:
        with session_factory() as session:
            rows = listar_insumos_legados(
                session,
                tenant_id=contexto.tenant_id,
                unidade_id=contexto.unidade_id,
            )
        return [_dto_insumo(row) for row in rows]

    @router.get("/insumos")
    def listar_insumos(request: Request) -> JSONResponse:
        try:
            contexto = _contexto(
                request,
                permissao=Permissao.ESTOQUE_VISUALIZAR,
                exigir_step_up=False,
            )
            itens = _listar(contexto)
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "itens": itens,
                    "valor_total": sum(
                        cast(float, item["valor_total"]) for item in itens
                    ),
                },
            )
        except Exception as exc:  # noqa: BLE001 - fronteira HTTP fail-closed
            return _tratar_erro(exc)

    @router.post("/insumos")
    def criar_insumo(payload: InsumoCreateIn, request: Request) -> JSONResponse:
        try:
            contexto = _contexto(
                request,
                permissao=Permissao.ESTOQUE_AJUSTAR,
                exigir_step_up=True,
            )
            insumo_id = aplicacao.salvar_insumo(
                contexto,
                valores={
                    "nome": payload.nome.strip(),
                    "unidade_medida": payload.unidade_medida.strip(),
                    "saldo_atual": payload.saldo_atual,
                    "estoque_minimo": payload.estoque_minimo,
                    "custo_unitario": payload.custo_unitario,
                    "data_fabricacao": payload.data_fabricacao,
                    "data_validade": payload.data_validade,
                    "dias_alerta_vencimento": payload.dias_alerta_vencimento,
                },
            )
            with session_factory() as session:
                row = obter_insumo_por_id_legado(
                    session,
                    tenant_id=contexto.tenant_id,
                    unidade_id=contexto.unidade_id,
                    insumo_id=insumo_id,
                )
            if row is None:
                return _erro(
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                    "estoque.persistencia_inconsistente",
                )
            return JSONResponse(
                status_code=status.HTTP_201_CREATED,
                content=_dto_insumo(row),
            )
        except Exception as exc:  # noqa: BLE001 - fronteira HTTP fail-closed
            return _tratar_erro(exc)

    @router.post("/leituras")
    def aplicar_leitura(payload: LeituraLoteIn, request: Request) -> JSONResponse:
        try:
            contexto = _contexto(
                request,
                permissao=Permissao.ESTOQUE_AJUSTAR,
                exigir_step_up=True,
            )
            total = aplicacao.aplicar_lote_leitura(
                contexto,
                itens=tuple(item.model_dump() for item in payload.itens),
            )
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={"processados": total, "itens": _listar(contexto)},
            )
        except Exception as exc:  # noqa: BLE001 - fronteira HTTP fail-closed
            return _tratar_erro(exc)

    @router.post("/forecasting-alertas")
    def executar_forecasting_alertas(request: Request) -> JSONResponse:
        try:
            contexto = _contexto(
                request,
                permissao=Permissao.ESTOQUE_AJUSTAR,
                exigir_step_up=True,
            )
            with session_factory() as session:

                def listar_destinatarios_legados() -> Sequence[Any]:
                    return session.execute(
                        select(contatos_gerenciais).where(
                            contatos_gerenciais.c.receber_alertas_estoque == 1
                        )
                    ).all()

                def enviar_whatsapp_control_plane(
                    *,
                    destinatario: str,
                    texto: str,
                    idempotency_key: str,
                ) -> str:
                    with session_factory() as session_integracao:
                        adapter = FabricaAdaptersExternos(
                            session=session_integracao,
                            secret_store=whatsapp_secret_store_factory(
                                session_integracao
                            ),
                        ).meta(
                            contexto=contexto,
                            configuracao_id="mensageria.whatsapp--meta",
                        )
                        return adapter.enviar_whatsapp(
                            destinatario=destinatario,
                            texto=texto,
                            idempotency_key=idempotency_key,
                        )

                resultado = aplicacao_forecasting.executar(
                    session,
                    tenant_id=contexto.tenant_id,
                    unidade_id=contexto.unidade_id,
                    contexto_notificacoes=lambda: contexto,
                    generate_content=generate_content,
                    is_test_mode=is_test_mode(),
                    mock_whatsapp_send=mock_whatsapp_send,
                    listar_destinatarios_legados=listar_destinatarios_legados,
                    enviar_whatsapp_control_plane=enviar_whatsapp_control_plane,
                )
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={"mensagem": resultado},
            )
        except Exception as exc:  # noqa: BLE001 - fronteira HTTP fail-closed
            return _tratar_erro(exc)

    @router.post("/leituras-visuais")
    async def aplicar_leitura_visual(request: Request) -> JSONResponse:
        try:
            contexto = _contexto(
                request,
                permissao=Permissao.ESTOQUE_AJUSTAR,
                exigir_step_up=True,
            )
            content_type = (
                request.headers.get("content-type", "")
                .partition(";")[0]
                .strip()
                .casefold()
            )
            if content_type not in {"image/jpeg", "image/png"}:
                return _erro(
                    status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                    "estoque.leitura_visual_tipo_invalido",
                )
            arquivo = await request.body()
            if not arquivo:
                return _erro(
                    status.HTTP_400_BAD_REQUEST,
                    "estoque.leitura_visual_arquivo_obrigatorio",
                )

            resultado = aplicacao_leitura_visual.executar(
                contexto,
                fonte_imagem=io.BytesIO(arquivo),
                generate_content=generate_content,
            )
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "processados": resultado.processados,
                    "itens_lidos": resultado.itens_lidos,
                    "itens": _listar(contexto),
                },
            )
        except (
            CredenciaisInvalidas,
            PermissionError,
            ErroSeguranca,
            ReferenciaSegredoInvalida,
            SegredoAusente,
            ErroEscopoLojaLegada,
            IntegrityError,
        ) as exc:
            return _tratar_erro(exc)
        except Exception:  # noqa: BLE001 - erro do provider/imagem sanitizado
            return _erro(
                status.HTTP_502_BAD_GATEWAY,
                "estoque.leitura_visual_falhou",
            )

    @router.delete("/insumos/{insumo_id}")
    def excluir_insumo(insumo_id: str, request: Request) -> JSONResponse:
        try:
            try:
                parsed_id = int(insumo_id)
            except (TypeError, ValueError):
                return _erro(
                    status.HTTP_404_NOT_FOUND,
                    "estoque.insumo_nao_encontrado",
                )
            contexto = _contexto(
                request,
                permissao=Permissao.ESTOQUE_AJUSTAR,
                exigir_step_up=True,
            )
            with session_factory() as session:
                existente = obter_insumo_por_id_legado(
                    session,
                    tenant_id=contexto.tenant_id,
                    unidade_id=contexto.unidade_id,
                    insumo_id=parsed_id,
                )
            if existente is None:
                return _erro(
                    status.HTTP_404_NOT_FOUND,
                    "estoque.insumo_nao_encontrado",
                )
            aplicacao.excluir_insumo(contexto, insumo_id=parsed_id)
            return JSONResponse(status_code=status.HTTP_200_OK, content={"ok": True})
        except Exception as exc:  # noqa: BLE001 - fronteira HTTP fail-closed
            return _tratar_erro(exc)

    return router
