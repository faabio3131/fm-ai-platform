"""Autoridade publica configuravel e indexada do Cardapio Digital V1.

O navegador conhece somente um ``public_id`` opaco. A traducao para tenant/unidade
ocorre no servidor por lookup indexado e, a partir desse escopo confiavel, reutiliza
a projecao canonica de catalogo do Delivery. O slug e configuravel e apenas visual.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from sqlalchemy.orm import Session

from core.delivery.modelos import ProdutoDelivery
from infra.administracao.modelos_orm import EmpresaAdminORM, UnidadeAdminORM
from infra.cardapio_publico.repositorio_sqlalchemy import (
    PublicacaoCardapioPersistida,
    RepositorioCardapioPublicoSQLAlchemy,
)
from infra.delivery.catalogo_sqlalchemy import CatalogoDeliverySQLAlchemy

_SLUG_INVALIDO = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class CardapioPublicoV1:
    publicacao: PublicacaoCardapioPersistida
    nome_empresa: str
    nome_unidade: str
    tipo_unidade: str
    catalogo: tuple[ProdutoDelivery, ...]


def normalizar_slug_publico(valor: str) -> str:
    bruto = unicodedata.normalize("NFKD", str(valor).strip())
    ascii_texto = bruto.encode("ascii", "ignore").decode("ascii").casefold()
    slug = _SLUG_INVALIDO.sub("-", ascii_texto).strip("-")
    if len(slug) < 3 or len(slug) > 80:
        raise ValueError("cardapio_publico.slug_invalido")
    return slug


def consultar_publicacao(
    *, session: Session, tenant_id: str, unidade_id: str
) -> PublicacaoCardapioPersistida | None:
    return RepositorioCardapioPublicoSQLAlchemy(session).obter_por_escopo(
        tenant_id=tenant_id,
        unidade_id=unidade_id,
    )


def salvar_publicacao(
    *,
    session: Session,
    tenant_id: str,
    unidade_id: str,
    slug: str,
    publicada: bool,
    versao_esperada: int,
) -> PublicacaoCardapioPersistida:
    return RepositorioCardapioPublicoSQLAlchemy(session).salvar(
        tenant_id=tenant_id,
        unidade_id=unidade_id,
        slug=normalizar_slug_publico(slug),
        publicada=bool(publicada),
        versao_esperada=versao_esperada,
    )


def resolver_cardapio_publico(
    *, session: Session, public_id: str
) -> CardapioPublicoV1 | None:
    referencia = str(public_id).strip()
    if len(referencia) != 32 or not all(c in "0123456789abcdef" for c in referencia):
        return None

    publicacao = RepositorioCardapioPublicoSQLAlchemy(session).obter_por_public_id(
        public_id=referencia
    )
    if publicacao is None or not publicacao.publicada:
        return None

    unidade = session.get(
        UnidadeAdminORM,
        (publicacao.tenant_id, publicacao.unidade_id),
    )
    empresa = session.get(EmpresaAdminORM, publicacao.tenant_id)
    if unidade is None or empresa is None or not unidade.ativa or not empresa.ativa:
        return None

    catalogo = CatalogoDeliverySQLAlchemy(session).listar(
        tenant_id=publicacao.tenant_id,
        unidade_id=publicacao.unidade_id,
    )
    return CardapioPublicoV1(
        publicacao=publicacao,
        nome_empresa=empresa.nome_exibicao,
        nome_unidade=unidade.nome_fantasia,
        tipo_unidade=unidade.tipo,
        catalogo=tuple(produto for produto in catalogo if produto.ativo),
    )
