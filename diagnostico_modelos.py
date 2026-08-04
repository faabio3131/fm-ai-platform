"""Lista modelos Gemini disponíveis sem exibir ou persistir credenciais."""

from __future__ import annotations

import os
import re
import sys
from typing import Any

from google import genai


def _supported_methods(model: Any) -> tuple[str, ...]:
    methods = getattr(model, "supported_actions", None)
    if methods is None:
        methods = getattr(model, "supported_generation_methods", ())
    return tuple(methods or ())


def _sanitize_message(message: str, api_key: str) -> str:
    message = message.replace(api_key, "[REDACTED]")
    return re.sub(
        r'(?i)(authorization|x-goog-api-key)(\s*[:=]\s*)[^,\r\n}]+',
        "[REDACTED]",
        message,
    )[:2000]


def _diagnostic_value(value: Any, api_key: str) -> str:
    if not isinstance(value, (str, int, float, bool)):
        return "indisponível"
    return _sanitize_message(str(value), api_key)


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
    except Exception as exc:
        response = getattr(exc, "response", None)
        http_status = getattr(exc, "status_code", None)
        if http_status is None and response is not None:
            http_status = getattr(response, "status_code", None)
        api_code = getattr(exc, "code", None)
        if http_status is None and isinstance(api_code, int) and 100 <= api_code <= 599:
            http_status = api_code
        api_status = getattr(exc, "status", None) or getattr(exc, "reason", None)
        message = str(getattr(exc, "message", None) or exc)
        message = _sanitize_message(message, api_key)
        print(f"TIPO_ERRO: {type(exc).__name__}", file=sys.stderr)
        print(f"HTTP_STATUS: {_diagnostic_value(http_status, api_key)}", file=sys.stderr)
        print(f"CODIGO_API: {_diagnostic_value(api_code, api_key)}", file=sys.stderr)
        print(f"STATUS_API: {_diagnostic_value(api_status, api_key)}", file=sys.stderr)
        print(f"MENSAGEM: {message}", file=sys.stderr)
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
