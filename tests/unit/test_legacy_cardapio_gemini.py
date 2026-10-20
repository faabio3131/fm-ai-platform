from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pypdf

from application.legacy_cardapio_gemini import (
    PROMPT_IMPORTACAO_CARDAPIO,
    AplicacaoImportacaoCardapioGeminiV1,
)
from core.seguranca.contexto import ContextoExecucao


def _contexto() -> ContextoExecucao:
    return ContextoExecucao(
        "tenant-cardapio",
        "unidade-cardapio",
        "usuario-cardapio",
        frozenset(),
        frozenset(),
        "corr-cardapio",
        datetime(2026, 9, 9, tzinfo=timezone.utc),
        "teste",
        unidades_permitidas=frozenset({"unidade-cardapio"}),
    )


class _CardapioCaptura:
    def __init__(self) -> None:
        self.produtos: tuple[dict[str, Any], ...] = ()

    def importar_produtos(
        self,
        contexto: ContextoExecucao,
        *,
        produtos: tuple[dict[str, Any], ...],
    ) -> int:
        assert contexto == _contexto()
        self.produtos = produtos
        return len(produtos)


def test_importacao_texto_preserva_prompt_parsing_cmv_e_persistencia() -> None:
    cardapio = _CardapioCaptura()
    aplicacao = AplicacaoImportacaoCardapioGeminiV1(cardapio)  # type: ignore[arg-type]
    chamadas: list[Any] = []
    ordem: list[str] = []

    def gerar(*, contents: Any) -> Any:
        chamadas.append(contents)
        return SimpleNamespace(
            text="```json\n"
            + json.dumps(
                [
                    {
                        "nome": "Prato IA",
                        "categoria": "Massas",
                        "preco": "39.90",
                        "ingredientes": "massa e molho",
                    },
                    {"nome": "Água"},
                ]
            )
            + "\n```"
        )

    resultado = aplicacao.importar(
        _contexto(),
        generate_content=gerar,
        texto_cardapio="Prato IA 39,90",
        antes_de_persistir=lambda: ordem.append("sessao_fechada"),
    )

    assert chamadas == [f"{PROMPT_IMPORTACAO_CARDAPIO}\n\nPrato IA 39,90"]
    assert ordem == ["sessao_fechada"]
    assert resultado == 2
    assert cardapio.produtos == (
        {
            "nome": "Prato IA",
            "categoria": "Massas",
            "preco_venda": 39.9,
            "custo_total_cmv": 12.77,
            "descricao_bruta": "massa e molho",
        },
        {
            "nome": "Água",
            "categoria": "Geral",
            "preco_venda": 0.0,
            "custo_total_cmv": 0.0,
            "descricao_bruta": "",
        },
    )


def test_importacao_pdf_preserva_contingencia_pypdf(monkeypatch) -> None:
    cardapio = _CardapioCaptura()
    aplicacao = AplicacaoImportacaoCardapioGeminiV1(cardapio)  # type: ignore[arg-type]
    chamadas: list[Any] = []
    contingencia: list[bool] = []

    class _Leitor:
        pages = (
            SimpleNamespace(extract_text=lambda: "Produto PDF 20,00"),
            SimpleNamespace(extract_text=lambda: "Ingredientes"),
        )

    monkeypatch.setattr(pypdf, "PdfReader", lambda _: _Leitor())

    def gerar(*, contents: Any) -> Any:
        chamadas.append(contents)
        if isinstance(contents, list):
            raise TypeError("arquivo direto rejeitado")
        return SimpleNamespace(
            text='[{"nome":"Produto PDF","preco":20,"ingredientes":"x"}]'
        )

    resultado = aplicacao.importar(
        _contexto(),
        generate_content=gerar,
        arquivo_bytes=b"pdf",
        arquivo_mime="application/pdf",
        ao_ativar_contingencia_pdf=lambda: contingencia.append(True),
    )

    assert resultado == 1
    assert contingencia == [True]
    assert len(chamadas) == 2
    assert chamadas[1] == (
        f"{PROMPT_IMPORTACAO_CARDAPIO}\n\nTexto extraído do PDF:\n"
        "Produto PDF 20,00\nIngredientes\n"
    )
