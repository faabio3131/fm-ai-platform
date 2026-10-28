"""Adaptador HTTP canônico do KDS V1."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Header, Query, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from application.impressao_composicao import montar_integracao_impressao_kds
from application.kds_roteamento import listar_itens_pendentes
from application.kds_runtime import ServicoKDSCanonico
from application.kds_transacoes import rotear_item_kds_v1, transicionar_kds_v1
from core.estados.maquinas import ErroTransicao
from core.kds.erros import ErroKDS
from core.kds.modelos import ItemFilaKDS, ProducaoItem, SetorProducao
from core.pedidos.modelos_orm import ItemPedidoORM
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.erros import CredenciaisInvalidas, ErroSeguranca
from http_api.auth import AuthSessionRuntime
from http_api.operational_auth import obter_identidade_operacional

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


class KDSRoteamentoItemOut(BaseModel):
    pedido_id: str
    pedido_item_id: str
    nome_produto: str
    quantidade: str
    status_pedido: str


class KDSRoteamentoPendenteOut(BaseModel):
    itens: list[KDSRoteamentoItemOut]


class KDSRoteamentoIn(BaseModel):
    pedido_item_id: str = Field(min_length=1, max_length=64)
    setor_id: str = Field(min_length=1, max_length=64)
    prioridade: int = Field(default=0, ge=0, le=100)


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


def _contexto_kds(
    request: Request,
    session: Session,
    *,
    auth_runtime: AuthSessionRuntime | None,
) -> ContextoExecucao:
    identidade = obter_identidade_operacional(
        request,
        session,
        auth_runtime=auth_runtime,
    ).identidade
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
    if isinstance(exc, ErroTransicao):
        codigo = exc.codigo
        http_status = (
            status.HTTP_403_FORBIDDEN
            if "permissao" in codigo
            else status.HTTP_409_CONFLICT
        )
        return JSONResponse(status_code=http_status, content={"erro": codigo})
    if isinstance(exc, ErroKDS):
        codigo = exc.codigo
        if codigo.endswith("_concorrente") or codigo in {
            "conflito_idempotencia",
            "conflito_transacional",
            "roteamento_pendente_indisponivel",
            "pedido_fora_fluxo_producao",
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


def build_kds_router(
    *,
    session_factory: SessionFactory,
    auth_runtime: AuthSessionRuntime | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/v1/kds", tags=["kds"])

    @router.get("/setores", response_model=KDSSetoresOut)
    def listar_setores(request: Request) -> KDSSetoresOut | JSONResponse:
        try:
            with session_factory() as session:
                contexto = _contexto_kds(
                    request,
                    session,
                    auth_runtime=auth_runtime,
                )
                setores = ServicoKDSCanonico(session).listar_setores(contexto)
                return KDSSetoresOut(setores=[_setor_out(setor) for setor in setores])
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _erro_http(exc)

    @router.get(
        "/roteamento-pendente",
        response_model=KDSRoteamentoPendenteOut,
    )
    def listar_roteamento_pendente(
        request: Request,
    ) -> KDSRoteamentoPendenteOut | JSONResponse:
        try:
            with session_factory() as session:
                contexto = _contexto_kds(
                    request,
                    session,
                    auth_runtime=auth_runtime,
                )
                itens = listar_itens_pendentes(session, contexto)
                return KDSRoteamentoPendenteOut(
                    itens=[
                        KDSRoteamentoItemOut(
                            pedido_id=item.pedido_id,
                            pedido_item_id=item.pedido_item_id,
                            nome_produto=item.nome_produto,
                            quantidade=str(item.quantidade),
                            status_pedido=item.status_pedido,
                        )
                        for item in itens
                    ]
                )
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _erro_http(exc)

    @router.post("/rotear", response_model=KDSTransicaoOut)
    def rotear_item(
        payload: KDSRoteamentoIn,
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
                contexto = _contexto_kds(
                    request,
                    session,
                    auth_runtime=auth_runtime,
                )
                pendentes = listar_itens_pendentes(session, contexto)
                pendente = next(
                    (
                        item
                        for item in pendentes
                        if item.pedido_item_id == payload.pedido_item_id
                    ),
                    None,
                )
                if pendente is None:
                    raise ErroKDS("roteamento_pendente_indisponivel")

                setores = ServicoKDSCanonico(session).listar_setores(contexto)
                if not any(
                    setor.setor_id == payload.setor_id and setor.ativo
                    for setor in setores
                ):
                    raise ErroKDS("setor_indisponivel")

                pedido_id = pendente.pedido_id
                quantidade = pendente.quantidade

            integracao_impressao = montar_integracao_impressao_kds(
                session_factory=session_factory,
                contexto=contexto,
            )
            resultado = rotear_item_kds_v1(
                session_factory=session_factory,
                contexto=contexto,
                pedido_id=pedido_id,
                pedido_item_id=payload.pedido_item_id,
                setor_id=payload.setor_id,
                quantidade=quantidade,
                idempotency_key=idempotency_key,
                prioridade=payload.prioridade,
                integracao_impressao=integracao_impressao,
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

    @router.get("/fila", response_model=KDSFilaOut)
    def listar_fila(
        request: Request,
        setor_id: str | None = Query(default=None, min_length=1, max_length=64),
    ) -> KDSFilaOut | JSONResponse:
        try:
            with session_factory() as session:
                contexto = _contexto_kds(
                    request,
                    session,
                    auth_runtime=auth_runtime,
                )
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
                contexto = _contexto_kds(
                    request,
                    session,
                    auth_runtime=auth_runtime,
                )
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
