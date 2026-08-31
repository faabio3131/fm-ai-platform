"""Parsing estrito das respostas estruturadas do Assistente de Atendimento V1."""

from __future__ import annotations

import json
from typing import Any

from .atendimento_modelos import IntencaoAtendimento, ItemIntencaoAtendimento
from .erros import ErroAssistenteAtendimento

_CHAVES_RAIZ = frozenset({"cliente_nome", "itens", "resposta_cliente"})
_CHAVES_ITEM = frozenset({"nome_produto", "quantidade"})


def _objeto(valor: Any, codigo: str) -> dict[str, Any]:
    if not isinstance(valor, dict):
        raise ErroAssistenteAtendimento(codigo)
    return valor


def parse_intencao_atendimento(raw: str) -> IntencaoAtendimento:
    """Aceita somente JSON puro e o contrato exato; não corrige nem inventa campos."""

    texto = raw.strip()
    if not texto.startswith("{") or not texto.endswith("}"):
        raise ErroAssistenteAtendimento(
            "schema_atendimento_invalido",
            "resposta deve ser JSON puro",
        )

    try:
        payload = _objeto(json.loads(texto), "schema_atendimento_invalido")
    except (json.JSONDecodeError, TypeError) as exc:
        raise ErroAssistenteAtendimento("schema_atendimento_invalido") from exc

    if frozenset(payload) != _CHAVES_RAIZ:
        raise ErroAssistenteAtendimento(
            "schema_atendimento_invalido",
            "campos raiz divergentes",
        )

    cliente_nome = payload["cliente_nome"]
    resposta = payload["resposta_cliente"]
    itens_raw = payload["itens"]

    if not isinstance(cliente_nome, str) or not isinstance(resposta, str):
        raise ErroAssistenteAtendimento("schema_atendimento_invalido")

    if not isinstance(itens_raw, list) or not itens_raw:
        raise ErroAssistenteAtendimento("carrinho_vazio")

    itens: list[ItemIntencaoAtendimento] = []

    for bruto in itens_raw:
        item = _objeto(bruto, "schema_item_atendimento_invalido")
        if frozenset(item) != _CHAVES_ITEM:
            raise ErroAssistenteAtendimento("schema_item_atendimento_invalido")

        nome = item["nome_produto"]
        quantidade = item["quantidade"]
        if (
            not isinstance(nome, str)
            or isinstance(quantidade, bool)
            or not isinstance(quantidade, int)
        ):
            raise ErroAssistenteAtendimento("schema_item_atendimento_invalido")

        try:
            itens.append(
                ItemIntencaoAtendimento(
                    nome_produto=nome,
                    quantidade=quantidade,
                )
            )
        except ValueError as exc:
            raise ErroAssistenteAtendimento(
                "schema_item_atendimento_invalido"
            ) from exc

    try:
        return IntencaoAtendimento(
            cliente_nome=cliente_nome,
            itens=tuple(itens),
            resposta_cliente=resposta,
        )
    except ValueError as exc:
        raise ErroAssistenteAtendimento("schema_atendimento_invalido") from exc
