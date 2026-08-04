"""Lista modelos Gemini disponíveis sem exibir ou persistir credenciais."""

from __future__ import annotations

import os
import sys
from typing import Any

from google import genai


def _supported_methods(model: Any) -> tuple[str, ...]:
    methods = getattr(model, "supported_actions", None)
    if methods is None:
        methods = getattr(model, "supported_generation_methods", ())
    return tuple(methods or ())


def main() -> int:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        print("ERRO: GEMINI_API_KEY não está configurada no ambiente.", file=sys.stderr)
        return 1

    try:
        client = genai.Client(api_key=api_key)
        models = client.models.list(config={"page_size": 1000})
        compatible = [
            (model, _supported_methods(model))
            for model in models
            if "generateContent" in _supported_methods(model)
        ]
    except Exception:
        print(
            "ERRO: não foi possível consultar os modelos Gemini com a chave configurada.",
            file=sys.stderr,
        )
        return 1

    print(f"Modelos compatíveis com generateContent: {len(compatible)}")
    for model, methods in compatible:
        print("-")
        print(f"nome: {getattr(model, 'name', '')}")
        print(f"display_name: {getattr(model, 'display_name', '')}")
        print(f"versão: {getattr(model, 'version', '')}")
        print(f"métodos suportados: {', '.join(methods)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
