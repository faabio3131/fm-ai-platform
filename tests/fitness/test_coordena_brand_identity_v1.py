from __future__ import annotations

from pathlib import Path

from core.branding import PRODUCT_NAME

ROOT = Path(__file__).resolve().parents[2]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


LEGACY_COMMERCIAL_TOKENS = (
    "F&M AI FOOD",
    "Acesso ao Gerente AI",
    "— Kordena",
)

MIGRATED_ACTIVE_SURFACES = (
    "infra/streamlit_app/auth_ui.py",
    "pages/6_Administracao_Proprietario.py",
    "pages/7_Integracoes_e_Credenciais.py",
    "pages/8_Atendimento_Garcom.py",
    "pages/9_Expedicao_Entrega.py",
    "tests/e2e/fase5/admin-proprietario.spec.ts",
)

LEGACY_SKILL_PATHS = (
    ".agents/skills/kordena-system-design-guardian/SKILL.md",
    ".agents/skills/kordena-validation-release-gate/SKILL.md",
    ".agents/skills/kordena-git-repository-governance/SKILL.md",
)


def test_coordena_is_the_canonical_product_name() -> None:
    assert PRODUCT_NAME == "Coordena"
    agents = _text("AGENTS.md")
    assert agents.startswith("# Coordena — instruções permanentes para agentes")
    assert "Nome comercial canônico atual:** `Coordena`" in agents


def test_migrated_active_surfaces_do_not_reintroduce_legacy_brand() -> None:
    for path in MIGRATED_ACTIVE_SURFACES:
        source = _text(path)
        assert "Coordena" in source or "PRODUCT_NAME" in source, path
        for token in LEGACY_COMMERCIAL_TOKENS:
            assert token not in source, f"{path}: legacy brand token {token!r}"


def test_admin_browser_contract_uses_canonical_coordena_login_heading() -> None:
    source = _text("tests/e2e/fase5/admin-proprietario.spec.ts")
    assert "Acesso ao Coordena" in source
    assert "Acesso ao Gerente AI" not in source


def test_legacy_skill_identifiers_are_explicitly_compatibility_only() -> None:
    for path in LEGACY_SKILL_PATHS:
        source = _text(path)
        assert "Coordena" in source, path
        assert "identificador técnico legado" in source, path
        assert 'canonical_product: "coordena"' in source, path


def test_repo_slug_and_internal_fm_ai_identifiers_are_not_renamed_by_brand_cutover() -> None:
    branding = _text("core/branding.py")
    migration = _text("docs/migracao-identidade-coordena-v1.md")
    assert 'PRODUCT_NAME = "Coordena"' in branding
    assert "fm-ai-platform" in migration
    assert "FM_AI_*" in migration


def test_legacy_root_app_brand_debt_is_explicitly_tracked_until_safe_pass_two() -> None:
    app = _text("app.py")
    migration = _text("docs/migracao-identidade-coordena-v1.md")
    assert "F&M AI FOOD" in app
    assert "Passagem 2 — raiz legada `app.py`" in migration
    assert "Não considerar a migração visual de marca integralmente fechada" in migration
