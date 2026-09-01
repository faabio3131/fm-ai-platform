from __future__ import annotations

import ast
from pathlib import Path

from core.ai_router import AIUsageEvent

FORBIDDEN_PROVIDER_SDKS = (
    "google.genai",
    "google.generativeai",
    "openai",
    "anthropic",
)


def imports(path: Path) -> tuple[str, ...]:
    tree = ast.parse(
        path.read_text(encoding="utf-8"),
        filename=str(path),
    )

    encontrados: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            encontrados.extend(
                alias.name for alias in node.names
            )

        elif isinstance(node, ast.ImportFrom) and node.module:
            encontrados.append(node.module)

    return tuple(encontrados)


def test_af15_router_nao_importa_sdk_de_provider() -> None:
    path = Path("core/ai_router.py")

    for modulo in imports(path):
        assert not modulo.startswith(
            FORBIDDEN_PROVIDER_SDKS
        )


def test_af15_gerente_ia_consumidor_nao_conhece_provider() -> None:
    path = Path(
        "application/gerente_ia_runtime.py"
    )

    for modulo in imports(path):
        assert not modulo.startswith(
            FORBIDDEN_PROVIDER_SDKS
        )

    texto = path.read_text(encoding="utf-8")

    proibidos = (
        "PlanejadorGeminiCore",
        "PortaGeminiTenant",
        "FabricaAdaptersExternos",
        "GoogleGenAITenantGateway",
        "genai.Client",
    )

    for proibido in proibidos:
        assert proibido not in texto


def test_af18_router_core_nao_contem_segredos() -> None:
    texto = Path("core/ai_router.py").read_text(
        encoding="utf-8"
    ).lower()

    assert "api_key" not in texto
    assert "client_secret" not in texto
    assert "authorization" not in texto


def test_af19_evento_nao_possui_payload_sensivel() -> None:
    campos = set(AIUsageEvent.__dataclass_fields__)

    proibidos = {
        "prompt",
        "response",
        "contents",
        "conteudo",
        "api_key",
        "secret",
        "segredo",
        "credential",
    }

    assert not (campos & proibidos)

    obrigatorios = {
        "tenant_id",
        "unidade_id",
        "request_id",
        "correlation_id",
        "capability",
        "provider",
        "model",
        "route_reason",
        "fallback_used",
        "latency_ms",
        "outcome",
        "price_snapshot_id",
        "timestamp",
    }

    assert obrigatorios <= campos
