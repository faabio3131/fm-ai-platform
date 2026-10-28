"""Boundary da importação legada de cardápio por Gemini."""

from __future__ import annotations

import io
import json
from collections.abc import Callable
from typing import Any, cast

from application.legacy_cardapio_transacoes import AplicacaoLegacyCardapioV1
from core.seguranca.contexto import ContextoExecucao

PROMPT_IMPORTACAO_CARDAPIO = """
                    Você é um especialista em ERP gastronômico. Analise o cardápio fornecido e extraia todos os produtos/pratos cadastráveis.
                    Retorne EXATAMENTE um JSON no seguinte formato (sem formatação markdown ```json, apenas a string json pura):
                    [
                        {
                            "nome": "Nome do Prato",
                            "categoria": "Hambúrgueres",
                            "preco": 39.90,
                            "ingredientes": "Descrição ou ingredientes"
                        }
                    ]
                    """


class AplicacaoImportacaoCardapioGeminiV1:
    """Extrai e persiste o cardápio com o comportamento legado original."""

    def __init__(self, cardapio: AplicacaoLegacyCardapioV1) -> None:
        self._cardapio = cardapio

    def importar(
        self,
        contexto: ContextoExecucao,
        *,
        generate_content: Callable[..., Any],
        texto_cardapio: str = "",
        arquivo_bytes: bytes | None = None,
        arquivo_mime: str | None = None,
        ao_ativar_contingencia_pdf: Callable[[], None] | None = None,
        antes_de_persistir: Callable[[], None] | None = None,
    ) -> int:
        prompt = PROMPT_IMPORTACAO_CARDAPIO

        if arquivo_bytes is not None:
            mime = cast(str, arquivo_mime)
            try:
                from google.genai import types

                part_arquivo = types.Part.from_bytes(
                    data=arquivo_bytes,
                    mime_type=mime,
                )
                contents = [part_arquivo, prompt]
                response = generate_content(contents=contents)
            except Exception:
                if mime == "application/pdf":
                    if ao_ativar_contingencia_pdf is not None:
                        ao_ativar_contingencia_pdf()
                    import pypdf

                    leitor_pdf = pypdf.PdfReader(io.BytesIO(arquivo_bytes))
                    texto_extraido = ""
                    for pagina in leitor_pdf.pages:
                        texto_extraido += pagina.extract_text() + "\n"

                    response = generate_content(
                        contents=(
                            f"{prompt}\n\nTexto extraído do PDF:\n{texto_extraido}"
                        )
                    )
                else:
                    raise
        else:
            response = generate_content(
                contents=f"{prompt}\n\n{texto_cardapio}"
            )

        texto_limpo = (
            response.text.strip().replace("```json", "").replace("```", "")
        )
        produtos_extraidos = json.loads(texto_limpo)

        produtos_para_salvar = []
        for prod in produtos_extraidos:
            cmv_est = round(float(prod.get("preco", 0)) * 0.32, 2)
            produtos_para_salvar.append(
                {
                    "nome": prod.get("nome"),
                    "categoria": prod.get("categoria", "Geral"),
                    "preco_venda": float(prod.get("preco", 0)),
                    "custo_total_cmv": cmv_est,
                    "descricao_bruta": prod.get("ingredientes", ""),
                }
            )

        if antes_de_persistir is not None:
            antes_de_persistir()

        return self._cardapio.importar_produtos(
            contexto,
            produtos=tuple(produtos_para_salvar),
        )
