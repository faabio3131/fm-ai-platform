from __future__ import annotations

from http_api.admin_fiscal_operations import (
    FinancialAdjustmentIn,
    FinancialObligationIn,
    IntakeReconcileIn,
    ManifestationIn,
    PreliminaryIntakeIn,
    ProductBindingIn,
    PurchaseOrderApproveIn,
    PurchaseOrderIn,
    ReceiptIn,
    ReturnReceiptIn,
    SupplierIn,
    TaxCreditDecisionIn,
    XmlUploadIn,
    build_admin_fiscal_operations_router,
)


def test_browser_payloads_cannot_choose_tenant_unit_or_user_scope() -> None:
    forbidden = {"tenant_id", "unidade_id", "usuario_id", "identity_user_id"}
    models = (
        XmlUploadIn,
        ManifestationIn,
        PreliminaryIntakeIn,
        IntakeReconcileIn,
        SupplierIn,
        ProductBindingIn,
        PurchaseOrderIn,
        PurchaseOrderApproveIn,
        ReceiptIn,
        ReturnReceiptIn,
        FinancialObligationIn,
        FinancialAdjustmentIn,
        TaxCreditDecisionIn,
    )
    for model in models:
        assert forbidden.isdisjoint(model.model_fields), model.__name__


def test_fiscal_operations_router_exposes_only_canonical_admin_boundary() -> None:
    router = build_admin_fiscal_operations_router(
        session_factory=lambda: None,  # type: ignore[arg-type]
        auth_runtime=object(),  # type: ignore[arg-type]
    )
    routes = {
        (method, route.path)
        for route in router.routes
        for method in (route.methods or set())
    }

    expected = {
        ("POST", "/v1/admin/fiscal/inbound/xml"),
        ("POST", "/v1/admin/fiscal/inbound/{access_key}/manifest"),
        ("POST", "/v1/admin/fiscal/intake/preliminary"),
        ("POST", "/v1/admin/fiscal/intake/{capture_id}/reconcile"),
        ("GET", "/v1/admin/fiscal/procurement"),
        ("POST", "/v1/admin/fiscal/procurement/suppliers"),
        ("POST", "/v1/admin/fiscal/procurement/bindings"),
        ("POST", "/v1/admin/fiscal/procurement/orders"),
        ("POST", "/v1/admin/fiscal/procurement/orders/{pedido_id}/approve"),
        ("POST", "/v1/admin/fiscal/procurement/receipts"),
        ("POST", "/v1/admin/fiscal/procurement/receipts/{recebimento_id}/return"),
        ("POST", "/v1/admin/fiscal/financial/obligations"),
        ("POST", "/v1/admin/fiscal/financial/adjustments"),
        ("POST", "/v1/admin/fiscal/financial/tax-credit-decisions"),
        ("POST", "/v1/admin/fiscal/documents/{access_key}/query"),
    }

    assert expected.issubset(routes)


def test_financial_mutation_models_do_not_accept_environment_override() -> None:
    assert "environment" not in FinancialObligationIn.model_fields
    assert "environment" not in FinancialAdjustmentIn.model_fields
    assert "environment" not in TaxCreditDecisionIn.model_fields
