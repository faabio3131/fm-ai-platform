from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_wp004_root_replaces_foundation_harness() -> None:
    page = _read("web/src/app/page.tsx")
    assert "DashboardHome" in page
    assert "Frontend foundation status" not in page


def test_wp003_root_layout_mounts_persistent_shell() -> None:
    layout = _read("web/src/app/layout.tsx")
    assert "AuthSessionGuard" in layout
    assert "UnifiedAppShell" in layout
    assert "<UnifiedAppShell>{children}</UnifiedAppShell>" in layout


def test_wp003_auth_guard_is_fail_closed_by_default() -> None:
    guard = _read("web/src/features/auth/components/AuthSessionGuard.tsx")
    assert 'const PUBLIC_PATHS = ["/login"] as const;' in guard
    assert "return !PUBLIC_PATHS.some" in guard
    assert "PROTECTED_PREFIXES" not in guard


def test_wp003_module_registry_governs_current_routes_with_rbac() -> None:
    registry = _read("web/src/features/shell/module-registry.ts")
    required_contracts = {
        'id: "pdv"': '"pdv.operar"',
        'id: "salao"': '"pedido.visualizar"',
        'id: "kds"': '"producao.visualizar"',
        'id: "catalogo"': '"admin.acessar"',
        'id: "saude-sistema"': '"admin.acessar"',
    }
    for module_id, permission in required_contracts.items():
        assert module_id in registry
        assert permission in registry

    assert '"mesa.abrir"' in registry
    assert '"comanda.alterar"' in registry
    assert "WP-" not in registry


def test_wp003_shell_does_not_expose_tenant_technical_id() -> None:
    shell = _read("web/src/features/shell/components/UnifiedAppShell.tsx")
    assert "auth.tenantId" not in shell
    assert "KORDENA" in shell
    assert "UnitSelectorModal" in shell
    assert "endAuthSession" in shell


def test_wp004_dashboard_only_uses_rbac_filtered_modules() -> None:
    dashboard = _read("web/src/features/shell/components/DashboardHome.tsx")
    assert "availableShellModules(auth.permissions)" in dashboard
    assert "Frontend foundation status" not in dashboard
    assert "WP-" not in dashboard


def test_wp004_technical_health_is_preserved_behind_admin() -> None:
    health = _read("web/src/app/admin/system-health/page.tsx")
    admin_layout = _read("web/src/app/admin/layout.tsx")
    assert "checkBackendHealth" in health
    assert "Saúde do sistema" in health
    assert "AdminStepUpGuard" in admin_layout
