"""Fronteira transacional do Cardápio/Ficha Técnica legado."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, TypeVar, cast

from sqlalchemy import MetaData, Table, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.seguranca.auditoria import EventoAuditoria, sanitizar_metadata
from core.seguranca.contexto import ContextoExecucao
from infra.legacy_product_scope import (
    inserir_ficha_tecnica_legada,
    listar_fichas_produto_legadas,
    obter_insumo_por_id_legado,
    inserir_produto_legado,
    obter_produto_por_id_legado,
)
from infra.seguranca.modelos_orm import EventoAuditoriaORM
from infra.seguranca.auditoria_sqlalchemy import RepositorioAuditoriaSQLAlchemy
from infra.transacoes.uow import UnitOfWorkV1

T = TypeVar("T")

SessionFactory = Callable[[], Session]


class ConflitoIdempotenciaCatalogo(RuntimeError):
    """A mesma chave idempotente foi reutilizada com outra intenção."""


class ConflitoFichaCatalogo(RuntimeError):
    """Ficha de rascunho já existe ou produto não é mais rascunho."""


@dataclass(frozen=True)
class ResultadoCadastroProduto:
    produto_id: int
    idempotente: bool


def _session_ativa(uow: UnitOfWorkV1) -> Session:
    if uow.session is None:
        raise RuntimeError("UnitOfWorkV1 sem Session ativa")

    return uow.session


def _audit_id_catalogo(
    *,
    contexto: ContextoExecucao,
    idempotency_key: str,
) -> str:
    material = (
        f"catalogo-produto-v1:{contexto.tenant_id}:"
        f"{contexto.unidade_id}:{idempotency_key}"
    )
    return "cat-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:60]


def _produto_replay(
    session: Session,
    *,
    contexto: ContextoExecucao,
    audit_id: str,
    request_fingerprint: str,
) -> int | None:
    row = session.get(EventoAuditoriaORM, audit_id)
    if row is None:
        return None

    metadata = dict(row.metadata_segura or {})
    if (
        row.tenant_id != contexto.tenant_id
        or row.unidade_id != contexto.unidade_id
        or row.acao != "catalogo.produto.criar"
        or metadata.get("request_fingerprint") != request_fingerprint
        or not row.recurso_id
    ):
        raise ConflitoIdempotenciaCatalogo(
            "chave idempotente já utilizada com outro payload"
        )

    try:
        return int(row.recurso_id)
    except (TypeError, ValueError) as exc:
        raise ConflitoIdempotenciaCatalogo(
            "registro idempotente do catálogo está inconsistente"
        ) from exc


class AplicacaoLegacyCardapioV1:
    """Write boundary autoritativo para produto/ficha técnica legados."""

    def __init__(
        self,
        session_factory: SessionFactory,
    ) -> None:
        self._session_factory = session_factory

    def _executar(
        self,
        acao: Callable[[Session], T],
    ) -> T:
        with UnitOfWorkV1(
            self._session_factory
        ) as uow:
            session = _session_ativa(uow)

            resultado = acao(session)

            uow.commit()

            return resultado

    def salvar_prato_com_ficha(
        self,
        contexto: ContextoExecucao,
        *,
        valores_produto: Mapping[str, Any],
        itens_ficha: Sequence[
            Mapping[str, Any]
        ],
    ) -> int:
        def acao(
            session: Session,
        ) -> int:
            produto_id = inserir_produto_legado(
                session,
                tenant_id=contexto.tenant_id,
                unidade_id=contexto.unidade_id,
                valores=dict(
                    valores_produto
                ),
            )

            for item in itens_ficha:
                inserir_ficha_tecnica_legada(
                    session,
                    tenant_id=contexto.tenant_id,
                    unidade_id=contexto.unidade_id,
                    produto_id=produto_id,
                    insumo_id=int(
                        item["insumo_id"]
                    ),
                    quantidade=item[
                        "quantidade"
                    ],
                )

            return produto_id

        return self._executar(acao)

    def salvar_prato_com_ficha_idempotente(
        self,
        contexto: ContextoExecucao,
        *,
        valores_produto: Mapping[str, Any],
        itens_ficha: Sequence[Mapping[str, Any]],
        idempotency_key: str,
        request_fingerprint: str,
    ) -> ResultadoCadastroProduto:
        key = idempotency_key.strip()
        fingerprint = request_fingerprint.strip()
        if not key or not fingerprint:
            raise ValueError("idempotência do catálogo incompleta")

        audit_id = _audit_id_catalogo(
            contexto=contexto,
            idempotency_key=key,
        )

        try:
            with UnitOfWorkV1(self._session_factory) as uow:
                session = _session_ativa(uow)
                replay = _produto_replay(
                    session,
                    contexto=contexto,
                    audit_id=audit_id,
                    request_fingerprint=fingerprint,
                )
                if replay is not None:
                    return ResultadoCadastroProduto(
                        produto_id=replay,
                        idempotente=True,
                    )

                produto_id = inserir_produto_legado(
                    session,
                    tenant_id=contexto.tenant_id,
                    unidade_id=contexto.unidade_id,
                    valores=dict(valores_produto),
                )
                for item in itens_ficha:
                    inserir_ficha_tecnica_legada(
                        session,
                        tenant_id=contexto.tenant_id,
                        unidade_id=contexto.unidade_id,
                        produto_id=produto_id,
                        insumo_id=int(item["insumo_id"]),
                        quantidade=item["quantidade"],
                    )

                papel_efetivo = next(
                    iter(sorted(contexto.papeis, key=lambda item: item.value)),
                    None,
                )
                evento = EventoAuditoria(
                    audit_id=audit_id,
                    tenant_id=contexto.tenant_id,
                    unidade_id=contexto.unidade_id,
                    usuario_id=contexto.usuario_id,
                    papel_efetivo=papel_efetivo,
                    acao="catalogo.produto.criar",
                    recurso_tipo="produto_legado",
                    recurso_id=str(produto_id),
                    resultado="sucesso",
                    motivo="cadastro canônico HTTP de produto",
                    correlation_id=contexto.correlation_id,
                    timestamp=datetime.now(timezone.utc),
                    origem=contexto.origem,
                    politica="catalogo-http-v1",
                    depois_resumido=(
                        ("produto_id", produto_id),
                        ("ativo", bool(valores_produto.get("ativo", True))),
                    ),
                    metadata=sanitizar_metadata(
                        {"request_fingerprint": fingerprint}
                    ),
                )
                uow.registrar_efeitos(auditorias=(evento,))
                uow.commit()
                return ResultadoCadastroProduto(
                    produto_id=produto_id,
                    idempotente=False,
                )
        except IntegrityError:
            with self._session_factory() as session:
                replay = _produto_replay(
                    session,
                    contexto=contexto,
                    audit_id=audit_id,
                    request_fingerprint=fingerprint,
                )
            if replay is None:
                raise
            return ResultadoCadastroProduto(
                produto_id=replay,
                idempotente=True,
            )

    def atualizar_produto(
        self,
        contexto: ContextoExecucao,
        *,
        produto_id: int,
        valores: Mapping[str, Any],
    ) -> bool:
        payload = {
            chave: valor
            for chave, valor in valores.items()
            if chave in {"preco_venda", "ativo"}
        }
        if not payload:
            raise ValueError("nenhum campo atualizável informado")

        def acao(session: Session) -> bool:
            produto = obter_produto_por_id_legado(
                session,
                tenant_id=contexto.tenant_id,
                unidade_id=contexto.unidade_id,
                produto_id=produto_id,
            )
            if produto is None:
                return False

            table = Table(
                "produtos",
                MetaData(),
                autoload_with=session.connection(),
            )
            loja_id = produto._mapping.get("loja_id")
            resultado = cast(
                CursorResult[Any],
                session.execute(
                    update(table)
                    .where(table.c.id == produto_id)
                    .where(table.c.loja_id == loja_id)
                    .values(**payload)
                ),
            )
            if resultado.rowcount != 1:
                raise RuntimeError(
                    "atualização de produto não atingiu exatamente "
                    "um registro da unidade"
                )
            return True

        return self._executar(acao)

    def vincular_ficha_a_rascunho(
        self,
        contexto: ContextoExecucao,
        *,
        produto_id: int,
        itens_ficha: Sequence[Mapping[str, Any]],
    ) -> bool:
        """Vincula insumos a produto IA inativo, calculando CMV real uma vez.

        A escrita permanece na Application/UoW e não ativa a venda implicitamente.
        Repetição ou produto já ativo falham fechado, sem duplicar consumo.
        """
        if not itens_ficha:
            raise ValueError("ficha técnica exige insumos")
        ids = [int(item["insumo_id"]) for item in itens_ficha]
        if len(set(ids)) != len(ids):
            raise ConflitoFichaCatalogo("insumo duplicado na ficha técnica")

        def acao(session: Session) -> bool:
            produto = obter_produto_por_id_legado(
                session,
                tenant_id=contexto.tenant_id,
                unidade_id=contexto.unidade_id,
                produto_id=produto_id,
            )
            if produto is None:
                return False
            if bool(produto.ativo):
                raise ConflitoFichaCatalogo("produto ativo não aceita vinculação inicial")
            existentes = listar_fichas_produto_legadas(
                session,
                tenant_id=contexto.tenant_id,
                unidade_id=contexto.unidade_id,
                produto_id=produto_id,
            )
            if existentes:
                raise ConflitoFichaCatalogo("produto já possui ficha técnica")

            custo = Decimal("0")
            validos: list[tuple[int, Decimal]] = []
            for item in itens_ficha:
                insumo_id = int(item["insumo_id"])
                quantidade = Decimal(str(item["quantidade"]))
                if not quantidade.is_finite() or quantidade <= 0:
                    raise ValueError("quantidade da ficha inválida")
                insumo = obter_insumo_por_id_legado(
                    session,
                    tenant_id=contexto.tenant_id,
                    unidade_id=contexto.unidade_id,
                    insumo_id=insumo_id,
                )
                if insumo is None:
                    from infra.legacy_product_scope import ErroEscopoLojaLegada
                    raise ErroEscopoLojaLegada("insumo indisponível na unidade")
                custo += quantidade * Decimal(str(insumo.custo_unitario or 0))
                validos.append((insumo_id, quantidade))

            for insumo_id, quantidade in validos:
                inserir_ficha_tecnica_legada(
                    session,
                    tenant_id=contexto.tenant_id,
                    unidade_id=contexto.unidade_id,
                    produto_id=produto_id,
                    insumo_id=insumo_id,
                    quantidade=quantidade,
                )

            preco = Decimal(str(produto.preco_venda or 0))
            custo = custo.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            margem = (
                f"{((preco - custo) / preco * 100):.1f}%"
                if preco > 0 else "0.0%"
            )
            table = Table("produtos", MetaData(), autoload_with=session.connection())
            result = cast(
                CursorResult[Any],
                session.execute(
                    update(table)
                    .where(table.c.id == produto_id)
                    .where(table.c.loja_id == produto._mapping["loja_id"])
                    .where(table.c.ativo.is_(False))
                    .values(custo_total_cmv=float(custo), margem_exibicao=margem)
                ),
            )
            if result.rowcount != 1:
                raise ConflitoFichaCatalogo("rascunho alterado durante operação")
            papel = next(
                iter(sorted(contexto.papeis, key=lambda x: x.value)),
                None,
            )
            evento = EventoAuditoria(
                audit_id="cat-ficha-" + hashlib.sha256(
                    f"{contexto.tenant_id}:{contexto.unidade_id}:"
                    f"{produto_id}:{contexto.correlation_id}".encode()
                ).hexdigest()[:52],
                tenant_id=contexto.tenant_id,
                unidade_id=contexto.unidade_id,
                usuario_id=contexto.usuario_id,
                papel_efetivo=papel,
                acao="catalogo.ficha.vincular",
                recurso_tipo="produto_legado",
                recurso_id=str(produto_id),
                resultado="sucesso",
                motivo="vínculo de insumos em rascunho, sem ativação",
                correlation_id=contexto.correlation_id,
                timestamp=datetime.now(timezone.utc),
                origem=contexto.origem,
                politica="catalogo-http-v1",
                depois_resumido=(
                    ("itens_ficha", len(validos)),
                    ("ativo", False),
                ),
                metadata=sanitizar_metadata({"cmv_calculado": str(custo)}),
            )
            RepositorioAuditoriaSQLAlchemy(session).adicionar(evento)
            return True

        return self._executar(acao)

    def importar_produtos(
        self,
        contexto: ContextoExecucao,
        *,
        produtos: Sequence[
            Mapping[str, Any]
        ],
    ) -> int:
        def acao(
            session: Session,
        ) -> int:
            total = 0

            for valores in produtos:
                inserir_produto_legado(
                    session,
                    tenant_id=contexto.tenant_id,
                    unidade_id=contexto.unidade_id,
                    valores=dict(valores),
                )

                total += 1

            return total

        return self._executar(acao)
