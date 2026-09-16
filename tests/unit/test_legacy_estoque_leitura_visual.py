from __future__ import annotations

import io
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

from PIL import Image

from application.legacy_estoque_leitura_visual import (
    PROMPT_LEITURA_VISUAL_ESTOQUE,
    AplicacaoLeituraVisualEstoqueV1,
)
from core.seguranca.contexto import ContextoExecucao


def _contexto() -> ContextoExecucao:
    return ContextoExecucao(
        "tenant-visual",
        "unidade-visual",
        "usuario-visual",
        frozenset(),
        frozenset(),
        "corr-visual",
        datetime(2026, 9, 9, tzinfo=timezone.utc),
        "teste",
        unidades_permitidas=frozenset({"unidade-visual"}),
    )


class _EstoqueCaptura:
    def __init__(self) -> None:
        self.itens: list[dict[str, Any]] = []

    def aplicar_lote_leitura(
        self,
        contexto: ContextoExecucao,
        *,
        itens: list[dict[str, Any]],
    ) -> int:
        assert contexto == _contexto()
        self.itens = itens
        return len(itens)


def _imagem_png() -> io.BytesIO:
    arquivo = io.BytesIO()
    Image.new("RGB", (2, 2), "white").save(arquivo, format="PNG")
    arquivo.seek(0)
    return arquivo


def test_leitura_visual_preserva_prompt_parsing_validade_e_lote() -> None:
    estoque = _EstoqueCaptura()
    aplicacao = AplicacaoLeituraVisualEstoqueV1(estoque)  # type: ignore[arg-type]
    chamadas: list[Any] = []
    itens_ia = [
        {
            "nome": "  Tomate  ",
            "unidade": "kg",
            "quantidade": "2.5",
            "valor_unitario": 8.0,
            "data_validade": "2026-10-20",
        },
        {
            "nome": "Queijo",
            "quantidade": 1,
            "data_validade": "data-inválida",
        },
        {"nome": "", "quantidade": 4},
        {"nome": "Sal", "quantidade": 0},
    ]

    def gerar(*, contents: Any) -> Any:
        chamadas.append(contents)
        return SimpleNamespace(text=f"```json\n{json.dumps(itens_ia)}\n```")

    resultado = aplicacao.executar(
        _contexto(),
        fonte_imagem=_imagem_png(),
        generate_content=gerar,
    )

    assert len(chamadas) == 1
    assert chamadas[0][0] == PROMPT_LEITURA_VISUAL_ESTOQUE
    assert isinstance(chamadas[0][1], Image.Image)
    assert resultado.itens_lidos == itens_ia
    assert resultado.processados == 2
    assert estoque.itens == [
        {
            "nome": "Tomate",
            "quantidade": 2.5,
            "unidade": "kg",
            "data_validade": datetime(2026, 10, 20),  # noqa: DTZ001
        },
        {
            "nome": "Queijo",
            "quantidade": 1.0,
            "unidade": "un",
            "data_validade": None,
        },
    ]
