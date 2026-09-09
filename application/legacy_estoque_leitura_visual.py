"""Boundary da leitura visual legada de nota fiscal e rótulo."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from PIL import Image

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
        img_pil = Image.open(fonte_imagem)
        prompt_ocr = PROMPT_LEITURA_VISUAL_ESTOQUE

        resp_cad = generate_content(contents=[prompt_ocr, img_pil])
        texto_ocr = (
            resp_cad.text.strip()
            .replace("```json", "")
            .replace("```", "")
            .strip()
        )
        itens_lidos = json.loads(texto_ocr)

        itens_para_aplicar = []
        for item in itens_lidos:
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

        processados = 0
        if itens_para_aplicar:
            processados = self._estoque.aplicar_lote_leitura(
                contexto,
                itens=itens_para_aplicar,
            )

        return ResultadoLeituraVisualEstoque(
            itens_lidos=itens_lidos,
            processados=processados,
        )
