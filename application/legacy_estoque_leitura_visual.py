"""Boundary da leitura visual legada de nota fiscal e rótulo."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from typing import Any

import pypdfium2 as pdfium
from PIL import Image
from pypdf import PdfReader

from application.legacy_estoque_transacoes import AplicacaoLegacyEstoqueV1
from core.seguranca.contexto import ContextoExecucao

PROMPT_LEITURA_VISUAL_ESTOQUE = (
    "Você é um auditor de estoque. Analise esta imagem.\n"
    "                        Extraia os itens e retorne APENAS um array JSON válido no formato: \n"
    '                        [{"nome": "Produto", "unidade": "kg", "quantidade": 5.0, "valor_unitario": 12.50, "data_validade": "YYYY-MM-DD"}]\n'
    "                        Se não encontrar a validade na imagem, preencha o campo data_validade com null.\n"
    "                        Retorne EXCLUSIVAMENTE o JSON puro (sem markdown)."
)


@dataclass(frozen=True)
class ResultadoLeituraVisualEstoque:
    itens_lidos: Any
    processados: int


class AplicacaoLeituraVisualEstoqueV1:
    """Lê a imagem e aplica o lote com o comportamento original."""

    def __init__(self, estoque: AplicacaoLegacyEstoqueV1) -> None:
        self._estoque = estoque

    def executar(
        self,
        contexto: ContextoExecucao,
        *,
        fonte_imagem: Any,
        generate_content: Callable[..., Any],
    ) -> ResultadoLeituraVisualEstoque:
        raw = fonte_imagem.read()
        if len(raw) > 10 * 1024 * 1024:
            raise ValueError("arquivo_maior_que_limite")
        if raw.startswith(b"%PDF-"):
            reader = PdfReader(BytesIO(raw), strict=True)
            if reader.is_encrypted or len(reader.pages) > 12:
                raise ValueError("pdf_nao_suportado")
            extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
            if not extracted.strip():
                pdf = pdfium.PdfDocument(raw)
                frames = []
                try:
                    for page in pdf:
                        if page.get_width() * page.get_height() > 1_000_000:
                            raise ValueError("pagina_pdf_excessiva")
                        frame = page.render(scale=1.5).to_pil()
                        if frame.width * frame.height > 4_000_000:
                            raise ValueError("pagina_pdf_excessiva")
                        frames.append(frame)
                finally:
                    pdf.close()
                if not frames:
                    raise ValueError("pdf_sem_paginas")
                source = frames
            else:
                if len(extracted) > 40000:
                    raise ValueError("documento_extenso")
                source = "Conteúdo PDF (dados não confiáveis):\\n" + extracted
        else:
            img_pil = Image.open(BytesIO(raw))
            if img_pil.format not in {"JPEG", "PNG", "WEBP"}:
                raise ValueError("imagem_nao_suportada")
            if img_pil.width * img_pil.height > 20_000_000:
                raise ValueError("imagem_grande")
            img_pil.load()
            source = img_pil
        prompt_ocr = PROMPT_LEITURA_VISUAL_ESTOQUE
        resp_cad = generate_content(contents=[prompt_ocr, *(source if isinstance(source, list) else [source])])
        texto_ocr = (
            resp_cad.text.strip()
            .replace("```json", "")
            .replace("```", "")
            .strip()
        )
        itens_lidos = json.loads(texto_ocr)
        if not isinstance(itens_lidos, list) or len(itens_lidos) > 100:
            raise ValueError('resposta_ia_invalida')

        itens_para_aplicar = []
        for item in itens_lidos:
            if not isinstance(item, dict):
                raise ValueError('item_ia_invalido')
            nome_l = str(item.get("nome", "")).strip()
            qtd_l = float(item.get("quantidade", 0.0))
            val_str = item.get("data_validade")

            val_obj = None
            if val_str:
                try:
                    val_obj = datetime.strptime(  # noqa: DTZ007 - preserva legado
                        val_str,
                        "%Y-%m-%d",
                    )
                except ValueError:
                    pass

            if nome_l and qtd_l > 0:
                itens_para_aplicar.append(
                    {
                        "nome": nome_l,
                        "quantidade": qtd_l,
                        "unidade": item.get("unidade", "un"),
                        "data_validade": val_obj,
                    }
                )

        # Upload é sempre PREVIEW: aplicação definitiva via endpoint de lote
        # protegido, após conferência e confirmação humanas.
        processados = 0
        itens_lidos = [
            {"nome": item["nome"], "quantidade": item["quantidade"],
             "unidade": item["unidade"],
             "data_validade": item["data_validade"].date().isoformat()
             if item["data_validade"] is not None else None}
            for item in itens_para_aplicar
        ]

        return ResultadoLeituraVisualEstoque(
            itens_lidos=itens_lidos,
            processados=processados,
        )
