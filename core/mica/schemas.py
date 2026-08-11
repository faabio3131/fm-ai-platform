"""Parsing estrito das respostas estruturadas da Mica V1."""

from __future__ import annotations

import json
from typing import Any

from .erros import ErroMica
from .modelos import IntencaoMica, ItemIntencaoMica

_CHAVES_RAIZ = frozenset({"cliente_nome", "itens", "resposta_whatsapp"})
_CHAVES_ITEM = frozenset({"nome_produto", "quantidade"})


def _objeto(valor: Any, codigo: str) -> dict[str, Any]:
    if not isinstance(valor, dict):
        raise ErroMica(codigo)
    return valor


def parse_intencao_mica(raw: str) -> IntencaoMica:
    """Aceita somente JSON puro e o contrato exato; não corrige nem inventa campos."""
    texto = raw.strip()
    if not texto.startswith("{") or not texto.endswith("}"):
        raise ErroMica("schema_mica_invalido", "resposta deve ser JSON puro")
    try:
        payload = _objeto(json.loads(texto), "schema_mica_invalido")
    except (json.JSONDecodeError, TypeError) as exc:
        raise ErroMica("schema_mica_invalido") from exc
    if frozenset(payload) != _CHAVES_RAIZ:
        raise ErroMica("schema_mica_invalido", "campos raiz divergentes")
    cliente_nome = payload["cliente_nome"]
    resposta = payload["resposta_whatsapp"]
    itens_raw = payload["itens"]
    if not isinstance(cliente_nome, str) or not isinstance(resposta, str):
        raise ErroMica("schema_mica_invalido")
    if not isinstance(itens_raw, list) or not itens_raw:
        raise ErroMica("carrinho_vazio")
    itens: list[ItemIntencaoMica] = []
    for bruto in itens_raw:
        item = _objeto(bruto, "schema_item_mica_invalido")
        if frozenset(item) != _CHAVES_ITEM:
            raise ErroMica("schema_item_mica_invalido")
        nome = item["nome_produto"]
        quantidade = item["quantidade"]
        if not isinstance(nome, str) or isinstance(quantidade, bool) or not isinstance(quantidade, int):
            raise ErroMica("schema_item_mica_invalido")
        try:
            itens.append(ItemIntencaoMica(nome_produto=nome, quantidade=quantidade))
        except ValueError as exc:
            raise ErroMica("schema_item_mica_invalido") from exc
    try:
        return IntencaoMica(
            cliente_nome=cliente_nome,
            itens=tuple(itens),
            resposta_whatsapp=resposta,
        )
    except ValueError as exc:
        raise ErroMica("schema_mica_invalido") from exc
