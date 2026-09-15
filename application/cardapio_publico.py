"""Autoridade publica configuravel do Cardapio Digital V1.

A identificacao publica nunca usa tenant_id/unidade_id recebidos do navegador.
Cada unidade recebe um ``public_id`` opaco persistido na configuracao operacional;
o slug e somente apresentacao configuravel. Depois da resolucao, o catalogo continua
sendo a projecao canonica do Delivery para o escopo interno confiavel.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.administracao import ConfiguracaoEstabelecimento
from core.delivery.modelos import ProdutoDelivery
from infra.administracao.modelos_orm import (
    ConfiguracaoEstabelecimentoORM,
    EmpresaAdminORM,
    UnidadeAdminORM,
)
from infra.delivery.catalogo_sqlalchemy import CatalogoDeliverySQLAlchemy

_CHAVE_PUBLICACAO = "cardapio_publico"
_SLUG_INVALIDO = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class PublicacaoCardapioV1:
    public_id: str
    slug: str
    publicada: bool


@dataclass(frozen=True)
class CardapioPublicoV1:
    publicacao: PublicacaoCardapioV1
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


def _publicacao(config: ConfiguracaoEstabelecimento) -> PublicacaoCardapioV1 | None:
    bruto = config.parametros_operacionais.get(_CHAVE_PUBLICACAO)
    if not isinstance(bruto, dict):
        return None
    public_id = str(bruto.get("public_id", "")).strip()
    slug = str(bruto.get("slug", "")).strip()
    publicada = bruto.get("publicada") is True
    if not public_id or not slug:
        return None
    return PublicacaoCardapioV1(public_id=public_id, slug=slug, publicada=publicada)


def publicacao_da_configuracao(
    config: ConfiguracaoEstabelecimento,
) -> PublicacaoCardapioV1 | None:
    return _publicacao(config)


def aplicar_publicacao_na_configuracao(
    *,
    config: ConfiguracaoEstabelecimento,
    slug: str,
    publicada: bool,
) -> ConfiguracaoEstabelecimento:
    normalizado = normalizar_slug_publico(slug)
    atual = _publicacao(config)
    public_id = atual.public_id if atual is not None else uuid4().hex
    parametros = dict(config.parametros_operacionais)
    parametros[_CHAVE_PUBLICACAO] = {
        "public_id": public_id,
        "slug": normalizado,
        "publicada": bool(publicada),
    }
    return ConfiguracaoEstabelecimento(
        tenant_id=config.tenant_id,
        unidade_id=config.unidade_id,
        formas_pagamento=config.formas_pagamento,
        taxa_servico_percentual=config.taxa_servico_percentual,
        parametros_operacionais=parametros,
        politica_financeira=config.politica_financeira,
        versao=config.versao,
        atualizado_em=config.atualizado_em,
    )


def _config_from_row(row: ConfiguracaoEstabelecimentoORM) -> ConfiguracaoEstabelecimento:
    return ConfiguracaoEstabelecimento(
        tenant_id=row.tenant_id,
        unidade_id=row.unidade_id,
        formas_pagamento=tuple(row.formas_pagamento or ()),
        taxa_servico_percentual=Decimal(row.taxa_servico_percentual),
        parametros_operacionais=dict(row.parametros_operacionais or {}),
        politica_financeira=dict(row.politica_financeira or {}),
        versao=int(row.versao),
        atualizado_em=row.atualizado_em,
    )


def resolver_cardapio_publico(
    *, session: Session, public_id: str
) -> CardapioPublicoV1 | None:
    referencia = str(public_id).strip()
    if len(referencia) != 32 or not all(c in "0123456789abcdef" for c in referencia):
        return None

    for row in session.scalars(select(ConfiguracaoEstabelecimentoORM)).all():
        config = _config_from_row(row)
        publicacao = _publicacao(config)
        if publicacao is None or publicacao.public_id != referencia:
            continue
        if not publicacao.publicada:
            return None
        unidade = session.get(UnidadeAdminORM, (row.tenant_id, row.unidade_id))
        empresa = session.get(EmpresaAdminORM, row.tenant_id)
        if unidade is None or empresa is None or not unidade.ativa or not empresa.ativa:
            return None
        catalogo = CatalogoDeliverySQLAlchemy(session).listar(
            tenant_id=row.tenant_id,
            unidade_id=row.unidade_id,
        )
        return CardapioPublicoV1(
            publicacao=publicacao,
            nome_empresa=empresa.nome_exibicao,
            nome_unidade=unidade.nome_fantasia,
            tipo_unidade=unidade.tipo,
            catalogo=tuple(produto for produto in catalogo if produto.ativo),
        )
    return None
