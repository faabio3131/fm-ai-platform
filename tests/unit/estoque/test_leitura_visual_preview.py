"""Contrato de extração segura: nenhuma escrita durante o upload."""
from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace

import pytest
from PIL import Image
from pypdf import PdfWriter

from application.legacy_estoque_leitura_visual import AplicacaoLeituraVisualEstoqueV1


class EstoqueNaoGravavel:
    def aplicar_lote_leitura(self, *args, **kwargs):
        raise AssertionError("O upload nunca pode gravar dados")


def _imagem() -> BytesIO:
    buffer = BytesIO()
    Image.new("RGB", (120, 80), color="white").save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


def test_upload_png_so_extrai_previa_sem_mutacao():
    app = AplicacaoLeituraVisualEstoqueV1(EstoqueNaoGravavel())
    recebido = []
    def gerar(*, contents):
        recebido.extend(contents)
        return SimpleNamespace(text='[{"nome":"Bacon","quantidade":2,"unidade":"kg","data_validade":"2026-10-11"}]')
    resultado = app.executar(None, fonte_imagem=_imagem(), generate_content=gerar)
    assert resultado.processados == 0
    assert resultado.itens_lidos == [{"nome":"Bacon","quantidade":2.0,"unidade":"kg","data_validade":"2026-10-11"}]
    assert len(recebido) == 2


def test_pdf_digitalizado_renderiza_paginas_sem_gravacao():
    pdf = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=100)
    writer.write(pdf)
    pdf.seek(0)
    app = AplicacaoLeituraVisualEstoqueV1(EstoqueNaoGravavel())
    captured = []
    def gerar(*, contents):
        captured.extend(contents)
        return SimpleNamespace(text='[{"nome":"Pão brioche","quantidade":12,"unidade":"un","data_validade":null}]')
    result = app.executar(None, fonte_imagem=pdf, generate_content=gerar)
    assert result.processados == 0
    assert result.itens_lidos[0]["nome"] == "Pão brioche"
    assert isinstance(captured[1], Image.Image)


def test_resposta_ia_nao_lista_e_rejeitada_sem_gravacao():
    app = AplicacaoLeituraVisualEstoqueV1(EstoqueNaoGravavel())
    with pytest.raises(ValueError, match="resposta_ia_invalida"):
        app.executar(None, fonte_imagem=_imagem(), generate_content=lambda **_: SimpleNamespace(text='{"nome":"Bacon"}'))
