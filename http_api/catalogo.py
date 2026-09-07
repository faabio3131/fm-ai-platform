"""HTTP canônico de gestão do catálogo/cardápio V1 sobre o legado escopado."""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Header, Query, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from application.legacy_cardapio_transacoes import (
    AplicacaoLegacyCardapioV1,
    ConflitoIdempotenciaCatalogo,
)
from core.seguranca.autenticacao import IdentidadeUsuario, ServicoAutenticacao
from core.seguranca.erros import (
    CredenciaisInvalidas,
    ErroSeguranca,
    ReferenciaSegredoInvalida,
    SegredoAusente,
)
from core.seguranca.permissoes import Permissao
from http_api.auth import AuthSessionRuntime
from infra.legacy_product_scope import (
    ErroEscopoLojaLegada,
    listar_produtos_legados,
    obter_produto_por_id_legado,
)
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy

SessionFactory = Callable[[], Session]


class ProdutoCreateIn(BaseModel):
    nome: str = Field(min_length=1, max_length=240)
    categoria: str = Field(min_length=1, max_length=160)
    preco: float = Field(ge=0)
    ativo: bool = True


class ProdutoPatchIn(BaseModel):
    preco: float | None = Field(default=None, ge=0)
    ativo: bool | None = None


def _erro(http_status: int, codigo: str) -> JSONResponse:
    return JSONResponse(status_code=http_status, content={"erro": codigo})


def _credenciais_basic(request: Request) -> tuple[str, str] | None:
    cabecalho = request.headers.get("authorization", "").strip()
    esquema, _, valor = cabecalho.partition(" ")
    if esquema.casefold() != "basic" or not valor:
        return None
    try:
        decodificado = base64.b64decode(valor, validate=True).decode("utf-8")
        email, password = decodificado.split(":", 1)
    except (ValueError, UnicodeDecodeError):
        return None
    return email, password


def _dto_produto(row: Any) -> dict[str, object]:
    mapping = row._mapping
    return {
        "id": str(mapping["id"]),
        "nome": str(mapping.get("nome") or ""),
        "categoria": str(mapping.get("categoria") or ""),
        "preco": float(mapping.get("preco_venda") or 0.0),
        "ativo": bool(mapping.get("ativo", True)),
    }


def _fingerprint(payload: ProdutoCreateIn) -> str:
    normalizado = json.dumps(
        payload.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(normalizado.encode("utf-8")).hexdigest()


def build_catalogo_router(
    *,
    session_factory: SessionFactory,
    auth_runtime: AuthSessionRuntime,
) -> APIRouter:
    router = APIRouter(prefix="/v1/catalogo", tags=["catalogo"])
    aplicacao = AplicacaoLegacyCardapioV1(session_factory)

    def _identidade(request: Request) -> IdentidadeUsuario:
        identidade_sessao = auth_runtime.resolver_identidade(request)
        if identidade_sessao is not None:
            return identidade_sessao

        credenciais = _credenciais_basic(request)
        tenant_id = request.headers.get("x-tenant-id", "").strip()
        unidade_id = request.headers.get("x-unit-id", "").strip()
        if credenciais is None or not tenant_id or not unidade_id:
            raise CredenciaisInvalidas("credenciais invalidas")

        email, password = credenciais
        with session_factory() as session:
            identidade = ServicoAutenticacao(
                RepositorioIdentidadesSQLAlchemy(session)
            ).autenticar(email=email, password=password)
        return identidade.no_escopo_ativo(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
        )

    def _contexto(request: Request, *, exigir_escrita: bool) -> Any:
        identidade = _identidade(request)
        if (
            exigir_escrita
            and Permissao.CONFIGURACAO_ALTERAR not in identidade.permissoes
        ):
            raise PermissionError("permissao insuficiente")
        return identidade.contexto(
            origem="catalogo_http_v1",
            correlation_id=request.headers.get("x-correlation-id") or None,
        )

    def _produto_scoped(
        *,
        contexto: Any,
        produto_id: str,
    ) -> Any | None:
        try:
            parsed = int(produto_id)
        except (TypeError, ValueError):
            return None
        with session_factory() as session:
            return obter_produto_por_id_legado(
                session,
                tenant_id=contexto.tenant_id,
                unidade_id=contexto.unidade_id,
                produto_id=parsed,
            )

    @router.get("/produtos")
    def listar_produtos(
        request: Request,
        categoria: str | None = Query(default=None),
        apenas_ativos: bool = Query(default=False),
    ) -> JSONResponse:
        try:
            contexto = _contexto(request, exigir_escrita=False)
            with session_factory() as session:
                rows = listar_produtos_legados(
                    session,
                    tenant_id=contexto.tenant_id,
                    unidade_id=contexto.unidade_id,
                )

            categoria_normalizada = (
                categoria.strip().casefold()
                if isinstance(categoria, str) and categoria.strip()
                else None
            )
            produtos = []
            for row in rows:
                dto = _dto_produto(row)
                if (
                    categoria_normalizada is not None
                    and str(dto["categoria"]).casefold() != categoria_normalizada
                ):
                    continue
                if apenas_ativos and not bool(dto["ativo"]):
                    continue
                produtos.append(dto)
            return JSONResponse(status_code=status.HTTP_200_OK, content=produtos)
        except CredenciaisInvalidas:
            return _erro(
                status.HTTP_401_UNAUTHORIZED,
                CredenciaisInvalidas.codigo,
            )
        except (ReferenciaSegredoInvalida, SegredoAusente):
            return _erro(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "auth.sessao_indisponivel",
            )
        except ErroEscopoLojaLegada:
            return _erro(
                status.HTTP_409_CONFLICT,
                "catalogo.escopo_indisponivel",
            )

    @router.get("/categorias")
    def listar_categorias(request: Request) -> JSONResponse:
        try:
            contexto = _contexto(request, exigir_escrita=False)
            with session_factory() as session:
                rows = listar_produtos_legados(
                    session,
                    tenant_id=contexto.tenant_id,
                    unidade_id=contexto.unidade_id,
                )
            categorias = sorted(
                {
                    str(row._mapping.get("categoria") or "").strip()
                    for row in rows
                    if str(row._mapping.get("categoria") or "").strip()
                },
                key=str.casefold,
            )
            return JSONResponse(status_code=status.HTTP_200_OK, content=categorias)
        except CredenciaisInvalidas:
            return _erro(
                status.HTTP_401_UNAUTHORIZED,
                CredenciaisInvalidas.codigo,
            )
        except (ReferenciaSegredoInvalida, SegredoAusente):
            return _erro(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "auth.sessao_indisponivel",
            )
        except ErroEscopoLojaLegada:
            return _erro(
                status.HTTP_409_CONFLICT,
                "catalogo.escopo_indisponivel",
            )

    @router.post("/produtos")
    def criar_produto(
        payload: ProdutoCreateIn,
        request: Request,
        idempotency_key: str | None = Header(
            default=None,
            alias="Idempotency-Key",
        ),
    ) -> JSONResponse:
        try:
            contexto = _contexto(request, exigir_escrita=True)
            key = (idempotency_key or "").strip()
            if not key:
                return _erro(
                    status.HTTP_400_BAD_REQUEST,
                    "catalogo.idempotency_key_obrigatoria",
                )
            if len(key) > 128:
                return _erro(
                    status.HTTP_400_BAD_REQUEST,
                    "catalogo.idempotency_key_invalida",
                )

            resultado = aplicacao.salvar_prato_com_ficha_idempotente(
                contexto,
                valores_produto={
                    "nome": payload.nome.strip(),
                    "categoria": payload.categoria.strip(),
                    "preco_venda": payload.preco,
                    "ativo": payload.ativo,
                },
                itens_ficha=(),
                idempotency_key=key,
                request_fingerprint=_fingerprint(payload),
            )
            produto = _produto_scoped(
                contexto=contexto,
                produto_id=str(resultado.produto_id),
            )
            if produto is None:
                return _erro(
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                    "catalogo.persistencia_inconsistente",
                )
            return JSONResponse(
                status_code=(
                    status.HTTP_200_OK
                    if resultado.idempotente
                    else status.HTTP_201_CREATED
                ),
                content=_dto_produto(produto),
            )
        except CredenciaisInvalidas:
            return _erro(
                status.HTTP_401_UNAUTHORIZED,
                CredenciaisInvalidas.codigo,
            )
        except PermissionError:
            return _erro(
                status.HTTP_403_FORBIDDEN,
                "seguranca.permissao_insuficiente",
            )
        except ConflitoIdempotenciaCatalogo:
            return _erro(
                status.HTTP_409_CONFLICT,
                "catalogo.idempotencia_conflitante",
            )
        except (ReferenciaSegredoInvalida, SegredoAusente):
            return _erro(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "auth.sessao_indisponivel",
            )
        except ErroEscopoLojaLegada:
            return _erro(
                status.HTTP_409_CONFLICT,
                "catalogo.escopo_indisponivel",
            )

    @router.patch("/produtos/{produto_id}")
    def atualizar_produto(
        produto_id: str,
        payload: ProdutoPatchIn,
        request: Request,
    ) -> JSONResponse:
        try:
            contexto = _contexto(request, exigir_escrita=True)
            valores: dict[str, object] = {}
            if payload.preco is not None:
                valores["preco_venda"] = payload.preco
            if payload.ativo is not None:
                valores["ativo"] = payload.ativo
            if not valores:
                return _erro(
                    status.HTTP_400_BAD_REQUEST,
                    "catalogo.patch_vazio",
                )
            try:
                parsed_id = int(produto_id)
            except (TypeError, ValueError):
                return _erro(
                    status.HTTP_404_NOT_FOUND,
                    "catalogo.produto_nao_encontrado",
                )

            atualizado = aplicacao.atualizar_produto(
                contexto,
                produto_id=parsed_id,
                valores=valores,
            )
            if not atualizado:
                return _erro(
                    status.HTTP_404_NOT_FOUND,
                    "catalogo.produto_nao_encontrado",
                )
            produto = _produto_scoped(
                contexto=contexto,
                produto_id=produto_id,
            )
            if produto is None:
                return _erro(
                    status.HTTP_404_NOT_FOUND,
                    "catalogo.produto_nao_encontrado",
                )
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content=_dto_produto(produto),
            )
        except CredenciaisInvalidas:
            return _erro(
                status.HTTP_401_UNAUTHORIZED,
                CredenciaisInvalidas.codigo,
            )
        except PermissionError:
            return _erro(
                status.HTTP_403_FORBIDDEN,
                "seguranca.permissao_insuficiente",
            )
        except (ReferenciaSegredoInvalida, SegredoAusente):
            return _erro(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "auth.sessao_indisponivel",
            )
        except ErroEscopoLojaLegada:
            return _erro(
                status.HTTP_409_CONFLICT,
                "catalogo.escopo_indisponivel",
            )
        except ErroSeguranca:
            return _erro(
                status.HTTP_403_FORBIDDEN,
                "seguranca.permissao_insuficiente",
            )

    return router
