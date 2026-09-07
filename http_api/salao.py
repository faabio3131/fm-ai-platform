"""Adaptador HTTP canônico de Salão, Mesas e Comandas V1."""

from __future__ import annotations

import base64
from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from uuid import NAMESPACE_URL, uuid4, uuid5

from fastapi import APIRouter, Header, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from application.salao_pedidos import lancar_pedido_salao_v1
from application.salao_transacoes import AplicacaoSalaoV1
from core.dominio.dinheiro import Dinheiro
from core.dominio.enums import CanalAtendimento, OrigemPedido, PedidoStatus
from core.dominio.erros import ConflitoIdempotencia
from core.dominio.ids import (
    CorrelationId,
    IdempotencyKey,
    PedidoId,
    PedidoItemId,
    ProdutoId,
    TenantId,
    UnidadeId,
)
from core.dominio.pedidos import ItemPedido, Pedido
from core.dominio.tipos import QuantidadeItem
from core.pedidos.modelos_orm import ItemPedidoORM
from core.salao import (
    Comanda,
    ErroSalao,
    RepositorioSalaoSQLAlchemy,
    ServicoSalao,
    StatusMesa,
)
from core.salao.modelos_orm import EventoSalaoORM
from core.seguranca.autenticacao import ServicoAutenticacao
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.erros import CredenciaisInvalidas, ErroSeguranca
from infra.legacy_product_scope import ErroEscopoLojaLegada, obter_produto_por_id_legado
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy

SessionFactory = Callable[[], Session]
_MAX_IDEMPOTENCY_KEY = 96


class SalaoMesaOut(BaseModel):
    id: str
    numero: str
    nome: str | None
    capacidade: int
    status: str


class SalaoComandaMapaOut(BaseModel):
    id: str
    mesa_id: str | None
    status_comanda: str
    total: Decimal
    aberta_em: datetime


class SalaoMapaOut(BaseModel):
    mesas: list[SalaoMesaOut]
    comandas: list[SalaoComandaMapaOut]


class AbrirComandaIn(BaseModel):
    mesa_id: str = Field(min_length=1, max_length=64)
    responsavel_nome: str | None = Field(default=None, min_length=1, max_length=120)
    quantidade_pessoas: int | None = Field(default=None, ge=1, le=1000)


class LancamentoPedidoItemIn(BaseModel):
    produto_id: str = Field(min_length=1, max_length=128)
    quantidade: int = Field(gt=0, le=1000)
    observacao: str | None = Field(default=None, max_length=500)


class LancamentoPedidoIn(BaseModel):
    itens: list[LancamentoPedidoItemIn] = Field(min_length=1, max_length=200)


class SalaoComandaOut(BaseModel):
    id: str
    numero: str
    mesa_id: str | None
    status_comanda: str
    total: Decimal
    saldo: Decimal
    aberta_em: datetime
    versao: int


class SalaoMutacaoComandaOut(BaseModel):
    idempotente: bool
    comanda: SalaoComandaOut


class SalaoItemPedidoOut(BaseModel):
    id: str
    pedido_id: str
    nome: str
    quantidade: int
    preco_unitario: Decimal
    subtotal: Decimal
    observacao: str | None


class SalaoPedidoOut(BaseModel):
    pedido_id: str
    valor: Decimal
    criado_em: datetime
    itens: list[SalaoItemPedidoOut]


class SalaoComandaDetalheOut(SalaoComandaOut):
    pedidos: list[SalaoPedidoOut]


class SalaoLancamentoPedidoOut(BaseModel):
    idempotente: bool
    comanda: SalaoComandaOut
    pedido: SalaoPedidoOut


class _RecursoSalaoNaoEncontrado(Exception):
    def __init__(self, codigo: str) -> None:
        self.codigo = codigo
        super().__init__(codigo)


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


def _contexto_salao(request: Request, session: Session) -> ContextoExecucao:
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
        origem="salao_http_v1",
        correlation_id=request.headers.get("x-correlation-id") or None,
    )


def _evento_por_chave(
    session: Session,
    contexto: ContextoExecucao,
    idempotency_key: str,
) -> EventoSalaoORM | None:
    return session.scalar(
        select(EventoSalaoORM).where(
            EventoSalaoORM.tenant_id == contexto.tenant_id,
            EventoSalaoORM.unidade_id == contexto.unidade_id,
            EventoSalaoORM.idempotency_key == idempotency_key,
        )
    )


def _comanda_out(comanda: Comanda) -> SalaoComandaOut:
    return SalaoComandaOut(
        id=comanda.comanda_id,
        numero=comanda.numero,
        mesa_id=comanda.mesa_id,
        status_comanda=comanda.status.name,
        total=comanda.total,
        saldo=comanda.saldo,
        aberta_em=comanda.aberta_em,
        versao=comanda.versao,
    )


def _produto_legado_id(valor: str) -> int:
    normalizado = valor.strip().removeprefix("legacy:produto:")
    try:
        produto_id = int(normalizado)
    except (TypeError, ValueError) as exc:
        raise _RecursoSalaoNaoEncontrado("produto_indisponivel") from exc
    if produto_id <= 0:
        raise _RecursoSalaoNaoEncontrado("produto_indisponivel")
    return produto_id


def _stable_id(prefixo: str, *, key: str, sufixo: str) -> str:
    valor = uuid5(NAMESPACE_URL, f"fm-ai-salao-v1:{key}:{sufixo}")
    return f"{prefixo}-{valor}"


def _montar_pedido_salao(
    *,
    payload: LancamentoPedidoIn,
    contexto: ContextoExecucao,
    session_factory: SessionFactory,
    idempotency_key: str,
) -> Pedido:
    tenant = TenantId(contexto.tenant_id)
    unidade = UnidadeId(contexto.unidade_id)
    itens: list[ItemPedido] = []
    subtotal = Dinheiro(Decimal("0.00"))

    with session_factory() as session:
        for indice, entrada in enumerate(payload.itens):
            produto_id = _produto_legado_id(entrada.produto_id)
            row = obter_produto_por_id_legado(
                session,
                tenant_id=contexto.tenant_id,
                unidade_id=contexto.unidade_id,
                produto_id=produto_id,
            )
            if row is None:
                raise _RecursoSalaoNaoEncontrado("produto_indisponivel")
            produto = dict(row._mapping)
            if not bool(produto.get("ativo", True)):
                raise _RecursoSalaoNaoEncontrado("produto_indisponivel")
            nome = str(produto.get("nome") or "").strip()
            preco_bruto = produto.get("preco_venda")
            if not nome or preco_bruto is None:
                raise _RecursoSalaoNaoEncontrado("produto_indisponivel")
            try:
                preco = Dinheiro(Decimal(str(preco_bruto)))
            except (InvalidOperation, ValueError) as exc:
                raise _RecursoSalaoNaoEncontrado("produto_indisponivel") from exc
            if preco.valor < 0:
                raise _RecursoSalaoNaoEncontrado("produto_indisponivel")

            quantidade = QuantidadeItem(entrada.quantidade)
            item_subtotal = preco * quantidade.valor
            subtotal = subtotal + item_subtotal
            itens.append(
                ItemPedido(
                    id=PedidoItemId(
                        _stable_id(
                            "item",
                            key=idempotency_key,
                            sufixo=f"{indice}:{produto_id}",
                        )
                    ),
                    tenant_id=tenant,
                    unidade_id=unidade,
                    produto_id=ProdutoId(f"legacy:produto:{produto_id}"),
                    nome_produto=nome,
                    quantidade=quantidade,
                    preco_unitario=preco,
                    subtotal=item_subtotal,
                    observacao=(
                        entrada.observacao.strip() if entrada.observacao else None
                    ),
                )
            )

    agora = datetime.now(timezone.utc)
    return Pedido.novo(
        id=PedidoId(_stable_id("salao", key=idempotency_key, sufixo="pedido")),
        tenant_id=tenant,
        unidade_id=unidade,
        origem=OrigemPedido.SALAO,
        canal=CanalAtendimento.SALAO,
        status=PedidoStatus.RASCUNHO,
        cliente_id=None,
        criado_em=agora,
        atualizado_em=agora,
        versao=1,
        correlation_id=CorrelationId(contexto.correlation_id),
        idempotency_key=IdempotencyKey(idempotency_key),
        subtotal=subtotal,
        descontos=Dinheiro(Decimal("0.00")),
        taxas=Dinheiro(Decimal("0.00")),
        total=subtotal,
        itens=tuple(itens),
        observacoes=(),
    )


def _pedido_out(pedido: Pedido) -> SalaoPedidoOut:
    return SalaoPedidoOut(
        pedido_id=str(pedido.id),
        valor=pedido.total.valor,
        criado_em=pedido.criado_em,
        itens=[
            SalaoItemPedidoOut(
                id=str(item.id),
                pedido_id=str(pedido.id),
                nome=item.nome_produto,
                quantidade=item.quantidade.valor,
                preco_unitario=item.preco_unitario.valor,
                subtotal=item.subtotal.valor,
                observacao=item.observacao,
            )
            for item in pedido.itens
        ],
    )


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
    if isinstance(exc, _RecursoSalaoNaoEncontrado):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"erro": exc.codigo},
        )
    if isinstance(exc, (ConflitoIdempotencia, IntegrityError)):
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"erro": "conflito_transacional"},
        )
    if isinstance(exc, ErroEscopoLojaLegada):
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"erro": "catalogo_indisponivel_no_escopo"},
        )
    if isinstance(exc, ErroSalao):
        codigo = exc.codigo
        if codigo.startswith("seguranca.") or "permiss" in codigo:
            http_status = status.HTTP_403_FORBIDDEN
        elif codigo in {
            "recurso_indisponivel",
            "comanda_indisponivel",
            "pedido_indisponivel",
        }:
            http_status = status.HTTP_404_NOT_FOUND
        elif codigo.endswith("_concorrente") or codigo in {
            "conflito_idempotencia",
            "conflito_transacional",
            "mesa_indisponivel",
            "mesa_codigo_conflitante",
            "comanda_numero_conflitante",
            "transicao_comanda_invalida",
        }:
            http_status = status.HTTP_409_CONFLICT
        else:
            http_status = status.HTTP_400_BAD_REQUEST
        return JSONResponse(status_code=http_status, content={"erro": codigo})
    if isinstance(exc, ValueError):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"erro": str(exc) or "requisicao_invalida"},
        )
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"erro": "salao_indisponivel"},
    )


def build_salao_router(*, session_factory: SessionFactory) -> APIRouter:
    router = APIRouter(prefix="/v1/salao", tags=["salao"])

    @router.get("/mapa", response_model=SalaoMapaOut)
    def listar_mapa(request: Request) -> SalaoMapaOut | JSONResponse:
        try:
            with session_factory() as session:
                contexto = _contexto_salao(request, session)
                snapshot = ServicoSalao(
                    RepositorioSalaoSQLAlchemy(session),
                    agora=lambda: datetime.now(timezone.utc),
                ).listar_mapa(contexto)
                return SalaoMapaOut(
                    mesas=[
                        SalaoMesaOut(
                            id=mesa.mesa_id,
                            numero=mesa.codigo,
                            nome=mesa.nome,
                            capacidade=mesa.capacidade,
                            status=mesa.status.name,
                        )
                        for mesa in snapshot.mesas
                    ],
                    comandas=[
                        SalaoComandaMapaOut(
                            id=comanda.comanda_id,
                            mesa_id=comanda.mesa_id,
                            status_comanda=comanda.status.name,
                            total=comanda.total,
                            aberta_em=comanda.aberta_em,
                        )
                        for comanda in snapshot.comandas
                    ],
                )
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _erro_http(exc)

    @router.post("/comandas/abrir", response_model=SalaoMutacaoComandaOut)
    def abrir_comanda(
        payload: AbrirComandaIn,
        request: Request,
        idempotency_key: str = Header(
            ...,
            alias="Idempotency-Key",
            min_length=1,
            max_length=128,
        ),
    ) -> JSONResponse:
        try:
            with session_factory() as session:
                contexto = _contexto_salao(request, session)
                repositorio = RepositorioSalaoSQLAlchemy(session)
                evento = _evento_por_chave(session, contexto, idempotency_key)
                mesa = repositorio.obter_mesa(
                    contexto.tenant_id,
                    contexto.unidade_id,
                    payload.mesa_id,
                )
                if mesa is None:
                    raise _RecursoSalaoNaoEncontrado("mesa_indisponivel")

                if evento is not None:
                    if evento.tipo != "comanda.aberta":
                        raise ErroSalao("conflito_idempotencia")
                    existente = repositorio.obter_comanda(
                        contexto.tenant_id,
                        contexto.unidade_id,
                        evento.agregado_id,
                    )
                    if existente is None:
                        raise RuntimeError("replay sem comanda persistida")
                    if existente.mesa_id != payload.mesa_id:
                        raise ErroSalao("conflito_idempotencia")
                    comanda_id = existente.comanda_id
                    numero = existente.numero
                    replay = True
                else:
                    if not mesa.ativo or mesa.status is not StatusMesa.LIVRE:
                        raise ErroSalao("mesa_indisponivel")
                    comanda_id = str(uuid4())
                    numero = f"WEB-{comanda_id.split('-', maxsplit=1)[0].upper()}"
                    replay = False
                expected_mesa_version = mesa.versao

            comanda = AplicacaoSalaoV1(session_factory).abrir_comanda(
                contexto,
                comanda_id=comanda_id,
                numero=numero,
                mesa_id=payload.mesa_id,
                expected_mesa_version=expected_mesa_version,
                idempotency_key=idempotency_key,
            )
            body = SalaoMutacaoComandaOut(
                idempotente=replay,
                comanda=_comanda_out(comanda),
            )
            return JSONResponse(
                status_code=(
                    status.HTTP_200_OK if replay else status.HTTP_201_CREATED
                ),
                content=body.model_dump(mode="json"),
            )
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _erro_http(exc)

    @router.post(
        "/comandas/{comanda_id}/pedidos",
        response_model=SalaoLancamentoPedidoOut,
    )
    def lancar_pedido(
        comanda_id: str,
        payload: LancamentoPedidoIn,
        request: Request,
        idempotency_key: str = Header(
            ...,
            alias="Idempotency-Key",
            min_length=1,
            max_length=_MAX_IDEMPOTENCY_KEY,
        ),
    ) -> JSONResponse:
        try:
            with session_factory() as session:
                contexto = _contexto_salao(request, session)
                comanda = RepositorioSalaoSQLAlchemy(session).obter_comanda(
                    contexto.tenant_id,
                    contexto.unidade_id,
                    comanda_id,
                )
                if comanda is None:
                    raise _RecursoSalaoNaoEncontrado("comanda_indisponivel")
                expected_version = comanda.versao

            pedido = _montar_pedido_salao(
                payload=payload,
                contexto=contexto,
                session_factory=session_factory,
                idempotency_key=idempotency_key,
            )
            resultado = lancar_pedido_salao_v1(
                session_factory=session_factory,
                contexto=contexto,
                comanda_id=comanda_id,
                pedido=pedido,
                expected_comanda_version=expected_version,
                idempotency_key=idempotency_key,
            )
            body = SalaoLancamentoPedidoOut(
                idempotente=resultado.idempotente,
                comanda=_comanda_out(resultado.comanda),
                pedido=_pedido_out(resultado.pedido),
            )
            return JSONResponse(
                status_code=(
                    status.HTTP_200_OK
                    if resultado.idempotente
                    else status.HTTP_201_CREATED
                ),
                content=body.model_dump(mode="json"),
            )
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _erro_http(exc)

    @router.get("/comandas/{comanda_id}", response_model=SalaoComandaDetalheOut)
    def obter_comanda(
        comanda_id: str,
        request: Request,
    ) -> SalaoComandaDetalheOut | JSONResponse:
        try:
            with session_factory() as session:
                contexto = _contexto_salao(request, session)
                repositorio = RepositorioSalaoSQLAlchemy(session)
                ServicoSalao(
                    repositorio,
                    agora=lambda: datetime.now(timezone.utc),
                ).listar_mapa(contexto)
                comanda = repositorio.obter_comanda(
                    contexto.tenant_id,
                    contexto.unidade_id,
                    comanda_id,
                )
                if comanda is None:
                    raise _RecursoSalaoNaoEncontrado("comanda_indisponivel")

                vinculos = repositorio.listar_pedidos(
                    contexto.tenant_id,
                    contexto.unidade_id,
                    comanda_id,
                )
                pedido_ids = [vinculo.pedido_id for vinculo in vinculos]
                itens_por_pedido: dict[str, list[SalaoItemPedidoOut]] = {
                    pedido_id: [] for pedido_id in pedido_ids
                }
                if pedido_ids:
                    itens = session.scalars(
                        select(ItemPedidoORM)
                        .where(
                            ItemPedidoORM.tenant_id == contexto.tenant_id,
                            ItemPedidoORM.unidade_id == contexto.unidade_id,
                            ItemPedidoORM.pedido_id.in_(pedido_ids),
                        )
                        .order_by(ItemPedidoORM.pedido_id, ItemPedidoORM.ordem)
                    ).all()
                    for item in itens:
                        itens_por_pedido[item.pedido_id].append(
                            SalaoItemPedidoOut(
                                id=item.id,
                                pedido_id=item.pedido_id,
                                nome=item.nome_produto,
                                quantidade=item.quantidade,
                                preco_unitario=Decimal(str(item.preco_unitario)),
                                subtotal=Decimal(str(item.subtotal)),
                                observacao=item.observacao,
                            )
                        )

                base = _comanda_out(comanda)
                return SalaoComandaDetalheOut(
                    **base.model_dump(),
                    pedidos=[
                        SalaoPedidoOut(
                            pedido_id=vinculo.pedido_id,
                            valor=vinculo.valor,
                            criado_em=vinculo.criado_em,
                            itens=itens_por_pedido.get(vinculo.pedido_id, []),
                        )
                        for vinculo in vinculos
                    ],
                )
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _erro_http(exc)

    @router.post(
        "/comandas/{comanda_id}/solicitar-conta",
        response_model=SalaoMutacaoComandaOut,
    )
    def solicitar_conta(
        comanda_id: str,
        request: Request,
        idempotency_key: str = Header(
            ...,
            alias="Idempotency-Key",
            min_length=1,
            max_length=128,
        ),
    ) -> SalaoMutacaoComandaOut | JSONResponse:
        try:
            with session_factory() as session:
                contexto = _contexto_salao(request, session)
                repositorio = RepositorioSalaoSQLAlchemy(session)
                comanda = repositorio.obter_comanda(
                    contexto.tenant_id,
                    contexto.unidade_id,
                    comanda_id,
                )
                if comanda is None:
                    raise _RecursoSalaoNaoEncontrado("comanda_indisponivel")
                evento = _evento_por_chave(session, contexto, idempotency_key)
                if evento is not None and (
                    evento.tipo != "comanda.conta_solicitada"
                    or evento.agregado_id != comanda_id
                ):
                    raise ErroSalao("conflito_idempotencia")
                replay = evento is not None
                expected_version = comanda.versao

            atualizado = AplicacaoSalaoV1(session_factory).solicitar_conta(
                contexto,
                comanda_id=comanda_id,
                expected_version=expected_version,
                idempotency_key=idempotency_key,
            )
            return SalaoMutacaoComandaOut(
                idempotente=replay,
                comanda=_comanda_out(atualizado),
            )
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _erro_http(exc)

    return router
