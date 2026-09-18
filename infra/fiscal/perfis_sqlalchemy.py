"""Durable fiscal issuer/product profile stores for Kordena WP-031D."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from infra.fiscal.modelos_orm import FiscalIssuerProfileORM, FiscalProductBindingORM
from kordena_fiscal.domain import (
    BrazilianJurisdiction,
    CestCode,
    CnaeCode,
    Cnpj,
    ExecutionScope,
    FiscalAddress,
    FiscalEnvironment,
    FiscalProductProfile,
    FiscalProfile,
    FiscalUnitCode,
    Gtin,
    MunicipalRegistration,
    NcmCode,
    ProductOrigin,
    StateRegistration,
    TaxClassificationHints,
    TaxRegimeCode,
)

from .repositorios_sqlalchemy import SessionFactory


class FiscalProfileStoreError(RuntimeError):
    """Base error for host-side fiscal profile persistence."""


class FiscalProfileConflictError(FiscalProfileStoreError):
    """Raised when one immutable version is reused with different content."""


class FiscalProfileOverlapError(FiscalProfileStoreError):
    """Raised when effective periods overlap within the same fiscal authority."""


class FiscalProfileNotFoundError(FiscalProfileStoreError):
    """Raised when no effective profile exists for the requested instant."""


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _instant(value: datetime) -> str:
    normalized = _utc(value)
    assert normalized is not None
    return normalized.isoformat().replace("+00:00", "Z")


def _parse_instant(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return _utc(parsed)


def _scope_payload(scope: ExecutionScope) -> dict[str, str]:
    return {
        "tenant_id": scope.tenant_id,
        "unit_id": scope.unit_id,
        "environment": scope.environment.value,
        "correlation_id": scope.correlation_id,
    }


def _scope_from_payload(payload: dict[str, Any]) -> ExecutionScope:
    return ExecutionScope(
        tenant_id=str(payload["tenant_id"]),
        unit_id=str(payload["unit_id"]),
        environment=FiscalEnvironment(str(payload["environment"])),
        correlation_id=str(payload["correlation_id"]),
    )


def _issuer_payload(profile: FiscalProfile) -> dict[str, Any]:
    address = profile.address
    return {
        "profile_id": profile.profile_id,
        "scope": _scope_payload(profile.scope),
        "cnpj": profile.cnpj.value,
        "legal_name": profile.legal_name,
        "trade_name": profile.trade_name,
        "tax_regime": int(profile.tax_regime),
        "state_registration": {
            "state_code": profile.state_registration.state_code,
            "number": profile.state_registration.number,
            "exempt": profile.state_registration.exempt,
        },
        "municipal_registration": (
            profile.municipal_registration.number
            if profile.municipal_registration is not None
            else None
        ),
        "primary_cnae": profile.primary_cnae.value,
        "address": {
            "street": address.street,
            "number": address.number,
            "district": address.district,
            "municipality_name": address.municipality_name,
            "municipality_ibge_code": address.jurisdiction.municipality_ibge_code,
            "state_code": address.jurisdiction.state_code,
            "country_code": address.jurisdiction.country_code,
            "postal_code": address.postal_code,
            "complement": address.complement,
        },
        "effective_from": _instant(profile.effective_from),
        "effective_to": (
            _instant(profile.effective_to)
            if profile.effective_to is not None
            else None
        ),
        "version": profile.version,
    }


def _issuer_from_payload(payload: dict[str, Any]) -> FiscalProfile:
    scope = _scope_from_payload(dict(payload["scope"]))
    registration = dict(payload["state_registration"])
    address = dict(payload["address"])
    municipality = payload.get("municipal_registration")
    return FiscalProfile(
        profile_id=str(payload["profile_id"]),
        scope=scope,
        cnpj=Cnpj(str(payload["cnpj"])),
        legal_name=str(payload["legal_name"]),
        trade_name=(
            str(payload["trade_name"])
            if payload.get("trade_name") is not None
            else None
        ),
        tax_regime=TaxRegimeCode(int(payload["tax_regime"])),
        state_registration=StateRegistration(
            state_code=str(registration["state_code"]),
            number=(
                str(registration["number"])
                if registration.get("number") is not None
                else None
            ),
            exempt=bool(registration["exempt"]),
        ),
        municipal_registration=(
            MunicipalRegistration(str(municipality))
            if municipality is not None
            else None
        ),
        primary_cnae=CnaeCode(str(payload["primary_cnae"])),
        address=FiscalAddress(
            street=str(address["street"]),
            number=str(address["number"]),
            district=str(address["district"]),
            municipality_name=str(address["municipality_name"]),
            jurisdiction=BrazilianJurisdiction(
                str(address["state_code"]),
                (
                    str(address["municipality_ibge_code"])
                    if address.get("municipality_ibge_code") is not None
                    else None
                ),
                str(address["country_code"]),
            ),
            postal_code=str(address["postal_code"]),
            complement=(
                str(address["complement"])
                if address.get("complement") is not None
                else None
            ),
        ),
        effective_from=_required_instant(payload, "effective_from"),
        effective_to=_optional_instant(payload, "effective_to"),
        version=int(payload["version"]),
    )


def _product_payload(profile: FiscalProductProfile) -> dict[str, Any]:
    return {
        "profile_id": profile.profile_id,
        "product_id": profile.product_id,
        "scope": _scope_payload(profile.scope),
        "commercial_code": profile.commercial_code,
        "description": profile.description,
        "ncm": profile.ncm.value,
        "cest": profile.cest.value if profile.cest is not None else None,
        "commercial_unit": profile.commercial_unit.value,
        "taxable_unit": profile.taxable_unit.value,
        "origin": int(profile.origin),
        "gtin": profile.gtin.value if profile.gtin is not None else None,
        "hints": {
            "fiscal_benefit_code": profile.hints.fiscal_benefit_code,
            "ibs_cbs_classification_code": profile.hints.ibs_cbs_classification_code,
        },
        "effective_from": _instant(profile.effective_from),
        "effective_to": (
            _instant(profile.effective_to)
            if profile.effective_to is not None
            else None
        ),
        "version": profile.version,
    }


def _product_from_payload(payload: dict[str, Any]) -> FiscalProductProfile:
    hints = dict(payload.get("hints") or {})
    cest = payload.get("cest")
    gtin = payload.get("gtin")
    return FiscalProductProfile(
        profile_id=str(payload["profile_id"]),
        product_id=str(payload["product_id"]),
        scope=_scope_from_payload(dict(payload["scope"])),
        commercial_code=str(payload["commercial_code"]),
        description=str(payload["description"]),
        ncm=NcmCode(str(payload["ncm"])),
        cest=CestCode(str(cest)) if cest is not None else None,
        commercial_unit=FiscalUnitCode(str(payload["commercial_unit"])),
        taxable_unit=FiscalUnitCode(str(payload["taxable_unit"])),
        origin=ProductOrigin(int(payload["origin"])),
        gtin=Gtin(str(gtin)) if gtin is not None else None,
        hints=TaxClassificationHints(
            fiscal_benefit_code=(
                str(hints["fiscal_benefit_code"])
                if hints.get("fiscal_benefit_code") is not None
                else None
            ),
            ibs_cbs_classification_code=(
                str(hints["ibs_cbs_classification_code"])
                if hints.get("ibs_cbs_classification_code") is not None
                else None
            ),
        ),
        effective_from=_required_instant(payload, "effective_from"),
        effective_to=_optional_instant(payload, "effective_to"),
        version=int(payload["version"]),
    )


def _required_instant(payload: dict[str, Any], key: str) -> datetime:
    parsed = _parse_instant(str(payload[key]))
    if parsed is None:
        raise FiscalProfileStoreError(f"{key} missing from persisted fiscal profile")
    return parsed


def _optional_instant(payload: dict[str, Any], key: str) -> datetime | None:
    value = payload.get(key)
    return _parse_instant(str(value)) if value is not None else None


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _overlaps(
    left_from: datetime,
    left_to: datetime | None,
    right_from: datetime,
    right_to: datetime | None,
) -> bool:
    left_end = left_to or datetime.max.replace(tzinfo=timezone.utc)
    right_end = right_to or datetime.max.replace(tzinfo=timezone.utc)
    return left_from < right_end and right_from < left_end


class FiscalIssuerProfileStoreSQLAlchemy:
    """Immutable, effective-dated issuer profiles scoped by tenant/unit/environment."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def save(
        self,
        profile: FiscalProfile,
        *,
        certificate_reference: str | None = None,
        provider_config_id: str | None = None,
    ) -> FiscalProfile:
        payload_json = _canonical_json(_issuer_payload(profile))
        with self._session_factory() as session, session.begin():
            existing = session.get(
                FiscalIssuerProfileORM,
                (profile.scope.tenant_id, profile.scope.unit_id, profile.version),
            )
            if existing is not None:
                if (
                    existing.environment != profile.scope.environment.value
                    or existing.payload_json != payload_json
                    or existing.certificate_reference != certificate_reference
                    or existing.provider_config_id != provider_config_id
                ):
                    raise FiscalProfileConflictError(
                        "issuer fiscal profile version reused with different content"
                    )
                return _issuer_from_payload(json.loads(existing.payload_json))

            self._assert_no_issuer_overlap(session, profile)
            session.add(
                FiscalIssuerProfileORM(
                    tenant_id=profile.scope.tenant_id,
                    unit_id=profile.scope.unit_id,
                    profile_version=profile.version,
                    environment=profile.scope.environment.value,
                    payload_json=payload_json,
                    certificate_reference=certificate_reference,
                    provider_config_id=provider_config_id,
                    valid_from=_utc(profile.effective_from),
                    valid_until=_utc(profile.effective_to),
                )
            )
            session.flush()
        return profile

    def resolve(
        self,
        *,
        scope: ExecutionScope,
        issued_at: datetime,
    ) -> FiscalProfile:
        instant = _utc(issued_at)
        assert instant is not None
        with self._session_factory() as session:
            rows = session.execute(
                select(FiscalIssuerProfileORM)
                .where(
                    FiscalIssuerProfileORM.tenant_id == scope.tenant_id,
                    FiscalIssuerProfileORM.unit_id == scope.unit_id,
                    FiscalIssuerProfileORM.environment == scope.environment.value,
                    FiscalIssuerProfileORM.valid_from <= instant,
                )
                .order_by(FiscalIssuerProfileORM.profile_version.desc())
            ).scalars()
            candidates = [
                row
                for row in rows
                if _utc(row.valid_until) is None or instant < _utc(row.valid_until)
            ]
            if len(candidates) != 1:
                if not candidates:
                    raise FiscalProfileNotFoundError(
                        "effective issuer fiscal profile not found"
                    )
                raise FiscalProfileOverlapError(
                    "multiple effective issuer fiscal profiles found"
                )
            profile = _issuer_from_payload(json.loads(candidates[0].payload_json))
            return _with_scope_correlation(profile, scope.correlation_id)

    def references(
        self,
        *,
        scope: ExecutionScope,
        version: int,
    ) -> tuple[str | None, str | None]:
        with self._session_factory() as session:
            row = session.get(
                FiscalIssuerProfileORM,
                (scope.tenant_id, scope.unit_id, version),
            )
            if row is None or row.environment != scope.environment.value:
                raise FiscalProfileNotFoundError("issuer fiscal profile not found")
            return row.certificate_reference, row.provider_config_id

    def _assert_no_issuer_overlap(
        self,
        session: Session,
        profile: FiscalProfile,
    ) -> None:
        rows = session.execute(
            select(FiscalIssuerProfileORM).where(
                FiscalIssuerProfileORM.tenant_id == profile.scope.tenant_id,
                FiscalIssuerProfileORM.unit_id == profile.scope.unit_id,
                FiscalIssuerProfileORM.environment == profile.scope.environment.value,
            )
        ).scalars()
        for row in rows:
            if _overlaps(
                profile.effective_from,
                profile.effective_to,
                _utc(row.valid_from) or profile.effective_from,
                _utc(row.valid_until),
            ):
                raise FiscalProfileOverlapError(
                    "issuer fiscal profile effective period overlaps existing version"
                )


class FiscalProductProfileStoreSQLAlchemy:
    """Fiscal classifications linked to the canonical Kordena product id."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def save(self, profile: FiscalProductProfile) -> FiscalProductProfile:
        payload_json = _canonical_json(_product_payload(profile))
        with self._session_factory() as session, session.begin():
            existing = session.get(
                FiscalProductBindingORM,
                (
                    profile.scope.tenant_id,
                    profile.scope.unit_id,
                    profile.product_id,
                    profile.version,
                ),
            )
            if existing is not None:
                if existing.payload_json != payload_json:
                    raise FiscalProfileConflictError(
                        "product fiscal profile version reused with different content"
                    )
                return _product_from_payload(json.loads(existing.payload_json))

            self._assert_no_product_overlap(session, profile)
            session.add(
                FiscalProductBindingORM(
                    tenant_id=profile.scope.tenant_id,
                    unit_id=profile.scope.unit_id,
                    product_id=profile.product_id,
                    profile_version=profile.version,
                    payload_json=payload_json,
                    valid_from=_utc(profile.effective_from),
                    valid_until=_utc(profile.effective_to),
                )
            )
            session.flush()
        return profile

    def resolve(
        self,
        *,
        scope: ExecutionScope,
        product_id: str,
        issued_at: datetime,
    ) -> FiscalProductProfile:
        instant = _utc(issued_at)
        assert instant is not None
        with self._session_factory() as session:
            rows = session.execute(
                select(FiscalProductBindingORM)
                .where(
                    FiscalProductBindingORM.tenant_id == scope.tenant_id,
                    FiscalProductBindingORM.unit_id == scope.unit_id,
                    FiscalProductBindingORM.product_id == product_id,
                    FiscalProductBindingORM.valid_from <= instant,
                )
                .order_by(FiscalProductBindingORM.profile_version.desc())
            ).scalars()
            candidates: list[FiscalProductProfile] = []
            for row in rows:
                if _utc(row.valid_until) is not None and instant >= _utc(row.valid_until):
                    continue
                decoded = _product_from_payload(json.loads(row.payload_json))
                if decoded.scope.environment is scope.environment:
                    candidates.append(decoded)
            if len(candidates) != 1:
                if not candidates:
                    raise FiscalProfileNotFoundError(
                        "effective product fiscal profile not found"
                    )
                raise FiscalProfileOverlapError(
                    "multiple effective product fiscal profiles found"
                )
            return _with_product_scope_correlation(candidates[0], scope.correlation_id)

    def _assert_no_product_overlap(
        self,
        session: Session,
        profile: FiscalProductProfile,
    ) -> None:
        rows = session.execute(
            select(FiscalProductBindingORM).where(
                FiscalProductBindingORM.tenant_id == profile.scope.tenant_id,
                FiscalProductBindingORM.unit_id == profile.scope.unit_id,
                FiscalProductBindingORM.product_id == profile.product_id,
            )
        ).scalars()
        for row in rows:
            decoded = _product_from_payload(json.loads(row.payload_json))
            if decoded.scope.environment is not profile.scope.environment:
                continue
            if _overlaps(
                profile.effective_from,
                profile.effective_to,
                _utc(row.valid_from) or profile.effective_from,
                _utc(row.valid_until),
            ):
                raise FiscalProfileOverlapError(
                    "product fiscal profile effective period overlaps existing version"
                )


def _with_scope_correlation(profile: FiscalProfile, correlation_id: str) -> FiscalProfile:
    return FiscalProfile(
        profile_id=profile.profile_id,
        scope=ExecutionScope(
            tenant_id=profile.scope.tenant_id,
            unit_id=profile.scope.unit_id,
            environment=profile.scope.environment,
            correlation_id=correlation_id,
        ),
        cnpj=profile.cnpj,
        legal_name=profile.legal_name,
        tax_regime=profile.tax_regime,
        state_registration=profile.state_registration,
        primary_cnae=profile.primary_cnae,
        address=profile.address,
        effective_from=profile.effective_from,
        version=profile.version,
        trade_name=profile.trade_name,
        municipal_registration=profile.municipal_registration,
        effective_to=profile.effective_to,
    )


def _with_product_scope_correlation(
    profile: FiscalProductProfile,
    correlation_id: str,
) -> FiscalProductProfile:
    return FiscalProductProfile(
        profile_id=profile.profile_id,
        product_id=profile.product_id,
        scope=ExecutionScope(
            tenant_id=profile.scope.tenant_id,
            unit_id=profile.scope.unit_id,
            environment=profile.scope.environment,
            correlation_id=correlation_id,
        ),
        commercial_code=profile.commercial_code,
        description=profile.description,
        ncm=profile.ncm,
        commercial_unit=profile.commercial_unit,
        taxable_unit=profile.taxable_unit,
        origin=profile.origin,
        effective_from=profile.effective_from,
        version=profile.version,
        cest=profile.cest,
        gtin=profile.gtin,
        hints=profile.hints,
        effective_to=profile.effective_to,
    )
