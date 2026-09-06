"""Adaptador HTTP canônico do KDS V1."""

from __future__ import annotations

import base64
from collections.abc import Callable
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Header, Query, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from application.kds_runtime import ServicoKDSCanonico
from application.kds_transacoes import transicionar_kds_v1
from core.kds.erros import ErroKDS
from core.kds.modelos import ItemFilaKDS, ProducaoItem, SetorProducao
from core.pedidos.modelos_orm import ItemPedidoORM
from core.seguranca.autenticacao import ServicoAutenticacao
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.erros import CredenciaisInvalidas, ErroSeguranca
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy

SessionFactory = Callable[[], Session]
DestinoKDS = Literal[
    "aceita",
    "em_preparo",
    "pausada",
    "pronta",
    "retirada",
    "cancelada",
]


class KDSSetorOut(BaseModel):
    setor_id: str
    codigo: str
    nome: str
    ordem: int
    sla_segundos: int | None
    ativo: bool
    criado_em: datetime
    atualizado_em: datetime


class KDSSetoresOut(BaseModel):
    setores: list[KDSSetorOut]


class KDSSLAOut(BaseModel):
    estado: str
    decorrido_segundos: int
    restante_segundos: int | None
    percentual: float | None


class KDSItemOut(BaseModel):
    pedido_item_id: str
    nome: str
    quantidade: int
    observacoes: str | None


class KDSTicketOut(BaseModel):
    producao_id: str
    pedido_id: str
    pedido_item_id: str
    setor_id: str
    setor_nome: str
    status: str
    prioridade: int
    quantidade: str
    tentativa: int
    versao: int
    criado_em: datetime
    atualizado_em: datetime
    aceita_em: datetime | None
    iniciada_em: datetime | None
    pausa_iniciada_em: datetime | None
    pronta_em: datetime | None
    retirada_em: datetime | None
    sla: KDSSLAOut
    itens: list[KDSItemOut]


class KDSFilaOut(BaseModel):
    tickets: list[KDSTicketOut]
    atualizado_em: datetime
    degradado: bool
    somente_leitura: bool
    motivo_degradacao: str | None


class KDSTransicaoIn(BaseModel):
    producao_id: str = Field(min_length=1, max_length=64)
    destino: DestinoKDS
    versao_esperada: int = Field(ge=1)
    motivo: str | None = Field(default=None, max_length=500)


class KDSTransicaoOut(BaseModel):
    producao_id: str
    pedido_id: str
    setor_id: str
    status: str
    versao: int
    pedido_status: str
    idempotente: bool
    atualizado_em: datetime


def _credenciais_basic(request: Request) -> tuple[str, str]:
    cabecalho = request.headers.get("authorization", "")
    esquema, _, valor = cabecalho.partition(" ")
    if esquema.casefold() != "basic" or not valor:
        raise CredenciaisInvalidas("credenciais invalidas")
    try:
        decodificado = base64.b64decode(valor, validate=True).decode("utf-8")
        email, password = decodificado.split(":", 1)
    except (ValueError, UnicodeDecodeError) as exc:
        raise CredenciaisInvalidas("credenciais invalidas") from exc
    return email, password


def _contexto_kds(request: Request, session: Session) -> ContextoExecucao:
    tenant_id = request.headers.get("x-tenant-id", "").strip()
    unidade_id = request.headers.get("x-unit-id", "").strip()
    if not tenant_id or not unidade_id:
        raise CredenciaisInvalidas("credenciais invalidas")

    email, password = _credenciais_basic(request)
    identidade = ServicoAutenticacao(
        RepositorioIdentidadesSQLAlchemy(session)
    ).autenticar(email=email, password=password)
    identidade = identidade.no_escopo_ativo(
        tenant_id=tenant_id,
        unidade_id=unidade_id,
    )
    return identidade.contexto(
        origem="kds_http_v1",
        correlation_id=request.headers.get("x-correlation-id") or None,
    )


def _setor_out(setor: SetorProducao) -> KDSSetorOut:
    return KDSSetorOut(
        setor_id=setor.setor_id,
        codigo=setor.codigo,
        nome=setor.nome,
        ordem=setor.ordem,
        sla_segundos=setor.sla_segundos,
        ativo=setor.ativo,
        criado_em=setor.criado_em,
        atualizado_em=setor.atualizado_em,
    )


def _precondicoes_transicao(atual: ProducaoItem, destino: str) -> dict[str, bool]:
    if destino == "aceita":
        return {"setor_correto": True}
    if destino == "em_preparo" and atual.status == "pausada":
        return {"impedimento_resolvido": True}
    if destino == "em_preparo":
        return {"estoque_resolvido": True, "estacao_apta": True}
    if destino == "pronta":
        return {"quantidade_concluida": True, "checklist_concluido": True}
    if destino == "retirada":
        return {"conferencia_realizada": True, "posse_transferida": True}
    return {}


def _erro_http(exc: Exception) -> JSONResponse:
    if isinstance(exc, CredenciaisInvalidas):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"erro": exc.codigo},
        )
    if isinstance(exc, ErroSeguranca):
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"erro": exc.codigo},
        )
    if isinstance(exc, ErroKDS):
        codigo = exc.codigo
        if codigo.endswith("_concorrente") or codigo in {
            "conflito_idempotencia",
            "conflito_transacional",
        }:
            http_status = status.HTTP_409_CONFLICT
        elif codigo in {
            "producao_indisponivel",
            "setor_indisponivel",
        }:
            http_status = status.HTTP_404_NOT_FOUND
        elif codigo in {
            "permissao_insuficiente",
            "aprovacao_exigida",
            "confirmacao_exigida",
        }:
            http_status = status.HTTP_403_FORBIDDEN
        elif codigo in {
            "kds_offline_somente_leitura",
            "pedido_item_indisponivel",
        }:
            http_status = status.HTTP_503_SERVICE_UNAVAILABLE
        else:
            http_status = status.HTTP_400_BAD_REQUEST
        return JSONResponse(status_code=http_status, content={"erro": codigo})
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"erro": "kds_indisponivel"},
    )


def _item_fila_out(
    item_fila: ItemFilaKDS,
    item_pedido: ItemPedidoORM,
) -> KDSTicketOut:
    producao = item_fila.producao
    return KDSTicketOut(
        producao_id=producao.producao_id,
        pedido_id=producao.pedido_id,
        pedido_item_id=producao.pedido_item_id,
        setor_id=producao.setor_id,
        setor_nome=item_fila.setor.nome,
        status=producao.status,
        prioridade=producao.prioridade,
        quantidade=str(producao.quantidade),
        tentativa=producao.tentativa,
        versao=producao.versao,
        criado_em=producao.criado_em,
        atualizado_em=producao.atualizado_em,
        aceita_em=producao.aceita_em,
        iniciada_em=producao.iniciada_em,
        pausa_iniciada_em=producao.pausa_iniciada_em,
        pronta_em=producao.pronta_em,
        retirada_em=producao.retirada_em,
        sla=KDSSLAOut(
            estado=item_fila.sla.estado.value,
            decorrido_segundos=item_fila.sla.decorrido_segundos,
            restante_segundos=item_fila.sla.restante_segundos,
            percentual=item_fila.sla.percentual,
        ),
        itens=[
            KDSItemOut(
                pedido_item_id=item_pedido.id,
                nome=item_pedido.nome_produto,
                quantidade=item_pedido.quantidade,
                observacoes=item_pedido.observacao,
            )
        ],
    )


def build_kds_router(*, session_factory: SessionFactory) -> APIRouter:
    router = APIRouter(prefix="/v1/kds", tags=["kds"])

    @router.get("/setores", response_model=KDSSetoresOut)
    def listar_setores(request: Request) -> KDSSetoresOut | JSONResponse:
        try:
            with session_factory() as session:
                contexto = _contexto_kds(request, session)
                setores = ServicoKDSCanonico(session).listar_setores(contexto)
                return KDSSetoresOut(setores=[_setor_out(setor) for setor in setores])
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _erro_http(exc)

    @router.get("/fila", response_model=KDSFilaOut)
    def listar_fila(
        request: Request,
        setor_id: str | None = Query(default=None, min_length=1, max_length=64),
    ) -> KDSFilaOut | JSONResponse:
        try:
            with session_factory() as session:
                contexto = _contexto_kds(request, session)
                canonico = ServicoKDSCanonico(session)
                setores = canonico.listar_setores(contexto)
                if setor_id is not None and not any(
                    setor.setor_id == setor_id for setor in setores
                ):
                    raise ErroKDS("setor_indisponivel")

                fila = canonico.listar_fila(contexto, setor_id=setor_id)
                ids = [item.producao.pedido_item_id for item in fila.itens]
                itens_por_id: dict[str, ItemPedidoORM] = {}
                if ids:
                    itens = session.scalars(
                        select(ItemPedidoORM).where(
                            ItemPedidoORM.tenant_id == contexto.tenant_id,
                            ItemPedidoORM.unidade_id == contexto.unidade_id,
                            ItemPedidoORM.id.in_(ids),
                        )
                    ).all()
                    itens_por_id = {item.id: item for item in itens}

                tickets: list[KDSTicketOut] = []
                for item_fila in fila.itens:
                    item_pedido = itens_por_id.get(item_fila.producao.pedido_item_id)
                    if item_pedido is None:
                        raise ErroKDS("pedido_item_indisponivel")
                    tickets.append(_item_fila_out(item_fila, item_pedido))

                return KDSFilaOut(
                    tickets=tickets,
                    atualizado_em=fila.atualizado_em,
                    degradado=fila.degradado,
                    somente_leitura=fila.somente_leitura,
                    motivo_degradacao=fila.motivo_degradacao,
                )
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _erro_http(exc)

    @router.post("/transicionar", response_model=KDSTransicaoOut)
    def transicionar_producao(
        payload: KDSTransicaoIn,
        request: Request,
        idempotency_key: str = Header(
            ...,
            alias="Idempotency-Key",
            min_length=1,
            max_length=128,
        ),
    ) -> KDSTransicaoOut | JSONResponse:
        try:
            with session_factory() as session:
                contexto = _contexto_kds(request, session)
                atual = ServicoKDSCanonico(session).kds_repo.obter_producao(
                    contexto.tenant_id,
                    contexto.unidade_id,
                    payload.producao_id,
                )
                if atual is None:
                    raise ErroKDS("producao_indisponivel")
                precondicoes = _precondicoes_transicao(atual, payload.destino)

            resultado = transicionar_kds_v1(
                session_factory=session_factory,
                contexto=contexto,
                producao_id=payload.producao_id,
                destino=payload.destino,
                versao_esperada=payload.versao_esperada,
                idempotency_key=idempotency_key,
                precondicoes=precondicoes,
                motivo=payload.motivo,
            )
            return KDSTransicaoOut(
                producao_id=resultado.item.producao_id,
                pedido_id=resultado.item.pedido_id,
                setor_id=resultado.item.setor_id,
                status=resultado.item.status,
                versao=resultado.item.versao,
                pedido_status=resultado.pedido_status.value,
                idempotente=resultado.idempotente,
                atualizado_em=resultado.item.atualizado_em,
            )
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _erro_http(exc)

    return router
