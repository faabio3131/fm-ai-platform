"""Application boundary do catálogo, pricing e promoções KCA-03."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.comercial.catalogo import (
    EntitlementPlano,
    PlanoComercial,
    PoliticaMudancaPreco,
    PrecoComercial,
    PromocaoComercial,
    StatusConfiguracaoCatalogo,
    StatusRegistroCatalogo,
    TipoDescontoPromocao,
    VersaoPlanoComercial,
    VersaoPromocaoComercial,
    decimal_limite,
    decimal_monetario,
    normalizar_billing_period,
    normalizar_capability_key,
    normalizar_currency,
    normalizar_plan_code,
    normalizar_reason,
    texto_opcional,
    utc,
    validar_desconto,
    validar_intervalo,
    validar_transicao_configuracao,
)
from core.comercial.erros import (
    ConflitoIdempotenciaComercial,
    DadoComercialInvalido,
    RegistroComercialDuplicado,
    RegistroComercialNaoEncontrado,
)
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Permissao
from infra.comercial.catalogo_orm import (
    FMCommercialPlanEntitlementORM,
    FMCommercialPlanVersionORM,
    FMCommercialPriceORM,
    FMCommercialPromotionORM,
    FMCommercialPromotionVersionORM,
)
from infra.comercial.catalogo_sqlalchemy import (
    RepositorioCatalogoComercialSQLAlchemy,
)
from infra.comercial.modelos_orm import CommercialAuditORM, CommercialOutboxORM
from infra.comercial.repositorio_sqlalchemy import RepositorioComercialSQLAlchemy


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _hash_payload(payload: Mapping[str, object]) -> str:
    serializado = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(serializado).hexdigest()


def _idempotency_key(valor: str) -> str:
    key = valor.strip()
    if not key or len(key) > 192:
        raise DadoComercialInvalido("idempotency_key_invalida")
    return key


def _exigir_admin(contexto: ContextoExecucao) -> None:
    if Permissao.ADMIN_ACESSAR not in contexto.permissoes:
        raise PermissionError("seguranca.admin_acesso_exigido")


def _promotion_code(promotion_id: str) -> str:
    return f"FMP-{promotion_id.replace('-', '')[:12].upper()}"


class AplicacaoCatalogoComercialV1:
    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    @staticmethod
    def _auditoria(
        *,
        contexto: ContextoExecucao,
        action: str,
        aggregate_type: str,
        aggregate_id: str,
        reason: str,
        metadata_safe: dict[str, object],
        instante: datetime,
    ) -> CommercialAuditORM:
        return CommercialAuditORM(
            audit_id=str(uuid4()),
            actor_user_id=contexto.identity_user_id or contexto.usuario_id,
            action=action,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            result="success",
            reason=reason,
            correlation_id=contexto.correlation_id,
            causation_id=contexto.causation_id,
            metadata_safe=metadata_safe,
            timestamp=instante,
        )

    @staticmethod
    def _evento(
        *,
        contexto: ContextoExecucao,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        idempotency_key: str,
        instante: datetime,
        payload: dict[str, object],
    ) -> CommercialOutboxORM:
        return CommercialOutboxORM(
            event_id=str(uuid4()),
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            fm_customer_id=None,
            product_account_id=None,
            product_code="KORDENA",
            product_tenant_id=None,
            correlation_id=contexto.correlation_id,
            causation_id=contexto.causation_id,
            idempotency_key=idempotency_key,
            occurred_at=instante,
            payload=payload,
            version=1,
            status="pending",
        )

    @staticmethod
    def _validar_idempotencia(
        *,
        registro,
        request_sha256: str,
        aggregate_type: str,
    ) -> str:
        if registro.request_sha256 != request_sha256:
            raise ConflitoIdempotenciaComercial("idempotency_payload_conflict")
        if registro.aggregate_type != aggregate_type:
            raise ConflitoIdempotenciaComercial("idempotency_scope_conflict")
        return str(registro.aggregate_id)

    def listar_catalogo_kordena(
        self, *, contexto: ContextoExecucao, instante: datetime | None = None
    ) -> tuple[dict[str, object], ...]:
        _exigir_admin(contexto)
        agora = utc(instante) if instante is not None else _agora()
        with self._session_factory() as session:
            repo = RepositorioCatalogoComercialSQLAlchemy(session)
            resultado: list[dict[str, object]] = []
            for plan in repo.listar_planos(product_code="KORDENA"):
                efetiva = repo.versao_efetiva_plano(
                    plan_id=plan.plan_id,
                    instante=agora,
                )
                precos = (
                    repo.listar_precos_versao(
                        plan_version_id=efetiva.plan_version_id
                    )
                    if efetiva is not None
                    else ()
                )
                precos_efetivos = tuple(
                    price
                    for price in precos
                    if price.status == StatusConfiguracaoCatalogo.PUBLISHED
                    and price.valid_from is not None
                    and price.valid_from <= agora
                    and (price.valid_until is None or price.valid_until > agora)
                )
                resultado.append(
                    {
                        "plan": plan,
                        "effective_version": efetiva,
                        "effective_prices": precos_efetivos,
                    }
                )
            return tuple(resultado)

    def criar_versao_plano(
        self,
        *,
        contexto: ContextoExecucao,
        idempotency_key: str,
        plan_code: str,
        display_name: str,
        description: str | None,
        trial_eligible: bool,
        marketing_badge: str | None,
        metadata: dict[str, object],
        entitlements: tuple[EntitlementPlano, ...],
        change_reason: str,
    ) -> VersaoPlanoComercial:
        _exigir_admin(contexto)
        code = normalizar_plan_code(plan_code)
        nome = display_name.strip()
        if not nome or len(nome) > 128:
            raise DadoComercialInvalido("display_name_invalido")
        descricao = texto_opcional(description, "description", max_length=1000)
        badge = texto_opcional(marketing_badge, "marketing_badge", max_length=96)
        reason = normalizar_reason(change_reason)
        key = _idempotency_key(idempotency_key)

        normalized_entitlements: list[EntitlementPlano] = []
        keys: set[str] = set()
        for item in entitlements:
            capability = normalizar_capability_key(item.capability_key)
            if capability in keys:
                raise DadoComercialInvalido("capability_key_duplicada")
            keys.add(capability)
            limit_unit = texto_opcional(
                item.limit_unit,
                "limit_unit",
                max_length=32,
            )
            normalized_entitlements.append(
                EntitlementPlano(
                    capability_key=capability,
                    enabled=bool(item.enabled),
                    limit_value=decimal_limite(item.limit_value),
                    limit_unit=limit_unit,
                    config=dict(item.config),
                )
            )

        payload = {
            "plan_code": code,
            "display_name": nome,
            "description": descricao,
            "trial_eligible": bool(trial_eligible),
            "marketing_badge": badge,
            "metadata": metadata,
            "entitlements": [
                {
                    "capability_key": item.capability_key,
                    "enabled": item.enabled,
                    "limit_value": item.limit_value,
                    "limit_unit": item.limit_unit,
                    "config": item.config,
                }
                for item in normalized_entitlements
            ],
            "change_reason": reason,
        }
        request_sha256 = _hash_payload(payload)

        try:
            with self._session_factory() as session, session.begin():
                catalog = RepositorioCatalogoComercialSQLAlchemy(session)
                shared = RepositorioComercialSQLAlchemy(session)
                plan = catalog.obter_plano_por_codigo(plan_code=code)
                if plan is None:
                    raise RegistroComercialNaoEncontrado("plan_not_found")
                scope = f"catalog.plan_version.create:{plan.plan_id}"
                existente = shared.obter_idempotencia(
                    scope=scope,
                    idempotency_key=key,
                )
                if existente is not None:
                    aggregate_id = self._validar_idempotencia(
                        registro=existente,
                        request_sha256=request_sha256,
                        aggregate_type="plan_version",
                    )
                    result = catalog.obter_versao_plano(
                        plan_version_id=aggregate_id
                    )
                    if result is None:
                        raise ConflitoIdempotenciaComercial(
                            "idempotency_result_missing"
                        )
                    return result

                instante = _agora()
                plan_version_id = str(uuid4())
                version_number = catalog.proximo_numero_versao_plano(
                    plan_id=plan.plan_id
                )
                row = FMCommercialPlanVersionORM(
                    plan_version_id=plan_version_id,
                    plan_id=plan.plan_id,
                    version_number=version_number,
                    display_name=nome,
                    description=descricao,
                    trial_eligible=bool(trial_eligible),
                    marketing_badge=badge,
                    metadata_json=dict(metadata),
                    status=StatusConfiguracaoCatalogo.DRAFT.value,
                    valid_from=None,
                    valid_until=None,
                    change_reason=reason,
                    created_by=contexto.identity_user_id or contexto.usuario_id,
                    validated_by=None,
                    published_by=None,
                    created_at=instante,
                    validated_at=None,
                    published_at=None,
                )
                entitlement_rows = tuple(
                    FMCommercialPlanEntitlementORM(
                        plan_version_id=plan_version_id,
                        capability_key=item.capability_key,
                        enabled=item.enabled,
                        limit_value=item.limit_value,
                        limit_unit=item.limit_unit,
                        config_json=item.config,
                    )
                    for item in normalized_entitlements
                )
                result = catalog.adicionar_versao_plano(row, entitlement_rows)
                shared.adicionar_idempotencia(
                    scope=scope,
                    idempotency_key=key,
                    request_sha256=request_sha256,
                    aggregate_type="plan_version",
                    aggregate_id=plan_version_id,
                    created_at=instante,
                )
                shared.adicionar_auditoria(
                    self._auditoria(
                        contexto=contexto,
                        action="commercial.plan_version.create",
                        aggregate_type="plan_version",
                        aggregate_id=plan_version_id,
                        reason=reason,
                        metadata_safe={
                            "plan_code": code,
                            "version_number": version_number,
                            "entitlement_count": len(entitlement_rows),
                        },
                        instante=instante,
                    )
                )
                return result
        except IntegrityError as exc:
            raise RegistroComercialDuplicado("plan_version_duplicate") from exc

    def validar_versao_plano(
        self,
        *,
        contexto: ContextoExecucao,
        plan_version_id: str,
        change_reason: str,
    ) -> VersaoPlanoComercial:
        _exigir_admin(contexto)
        reason = normalizar_reason(change_reason)
        instante = _agora()
        with self._session_factory() as session, session.begin():
            catalog = RepositorioCatalogoComercialSQLAlchemy(session)
            shared = RepositorioComercialSQLAlchemy(session)
            atual = catalog.obter_versao_plano(
                plan_version_id=plan_version_id.strip()
            )
            if atual is None:
                raise RegistroComercialNaoEncontrado("plan_version_not_found")
            validar_transicao_configuracao(
                atual.status,
                StatusConfiguracaoCatalogo.VALIDATED,
            )
            result = catalog.atualizar_status_versao_plano(
                plan_version_id=atual.plan_version_id,
                expected_status=StatusConfiguracaoCatalogo.DRAFT,
                values={
                    "status": StatusConfiguracaoCatalogo.VALIDATED.value,
                    "validated_by": contexto.identity_user_id or contexto.usuario_id,
                    "validated_at": instante,
                },
            )
            shared.adicionar_auditoria(
                self._auditoria(
                    contexto=contexto,
                    action="commercial.plan_version.validate",
                    aggregate_type="plan_version",
                    aggregate_id=atual.plan_version_id,
                    reason=reason,
                    metadata_safe={"version_number": atual.version_number},
                    instante=instante,
                )
            )
            return result

    def publicar_versao_plano(
        self,
        *,
        contexto: ContextoExecucao,
        idempotency_key: str,
        plan_version_id: str,
        expected_plan_version: int,
        effective_from: datetime,
        change_reason: str,
    ) -> VersaoPlanoComercial:
        _exigir_admin(contexto)
        if expected_plan_version < 1:
            raise DadoComercialInvalido("expected_plan_version_invalida")
        inicio = utc(effective_from)
        reason = normalizar_reason(change_reason)
        key = _idempotency_key(idempotency_key)
        payload = {
            "plan_version_id": plan_version_id.strip(),
            "expected_plan_version": expected_plan_version,
            "effective_from": inicio.isoformat(),
            "change_reason": reason,
        }
        request_sha256 = _hash_payload(payload)
        scope = f"catalog.plan_version.publish:{plan_version_id.strip()}"

        with self._session_factory() as session, session.begin():
            catalog = RepositorioCatalogoComercialSQLAlchemy(session)
            shared = RepositorioComercialSQLAlchemy(session)
            existente = shared.obter_idempotencia(
                scope=scope,
                idempotency_key=key,
            )
            if existente is not None:
                aggregate_id = self._validar_idempotencia(
                    registro=existente,
                    request_sha256=request_sha256,
                    aggregate_type="plan_version",
                )
                result = catalog.obter_versao_plano(plan_version_id=aggregate_id)
                if result is None:
                    raise ConflitoIdempotenciaComercial(
                        "idempotency_result_missing"
                    )
                return result

            candidate = catalog.obter_versao_plano(
                plan_version_id=plan_version_id.strip()
            )
            if candidate is None:
                raise RegistroComercialNaoEncontrado("plan_version_not_found")
            validar_transicao_configuracao(
                candidate.status,
                StatusConfiguracaoCatalogo.PUBLISHED,
            )
            plan = catalog.obter_plano(plan_id=candidate.plan_id)
            if plan is None:
                raise RegistroComercialNaoEncontrado("plan_not_found")
            latest = catalog.ultima_versao_publicada_plano(plan_id=plan.plan_id)
            if latest is not None:
                if latest.valid_from is None or inicio <= latest.valid_from:
                    raise DadoComercialInvalido(
                        "effective_from_deve_ser_posterior_ultima_publicacao"
                    )
                catalog.fechar_validade_versao_plano(
                    plan_version_id=latest.plan_version_id,
                    valid_until=inicio,
                )

            instante = _agora()
            result = catalog.atualizar_status_versao_plano(
                plan_version_id=candidate.plan_version_id,
                expected_status=StatusConfiguracaoCatalogo.VALIDATED,
                values={
                    "status": StatusConfiguracaoCatalogo.PUBLISHED.value,
                    "valid_from": inicio,
                    "published_by": contexto.identity_user_id or contexto.usuario_id,
                    "published_at": instante,
                },
            )
            catalog.marcar_plano_configurado(
                plan_id=plan.plan_id,
                expected_version=expected_plan_version,
                actor=contexto.identity_user_id or contexto.usuario_id,
                instante=instante,
            )
            shared.adicionar_idempotencia(
                scope=scope,
                idempotency_key=key,
                request_sha256=request_sha256,
                aggregate_type="plan_version",
                aggregate_id=result.plan_version_id,
                created_at=instante,
            )
            shared.adicionar_auditoria(
                self._auditoria(
                    contexto=contexto,
                    action="commercial.plan_version.publish",
                    aggregate_type="plan_version",
                    aggregate_id=result.plan_version_id,
                    reason=reason,
                    metadata_safe={
                        "plan_code": plan.plan_code,
                        "version_number": result.version_number,
                        "effective_from": inicio.isoformat(),
                    },
                    instante=instante,
                )
            )
            shared.adicionar_outbox(
                self._evento(
                    contexto=contexto,
                    event_type="plan.version.published",
                    aggregate_type="plan_version",
                    aggregate_id=result.plan_version_id,
                    idempotency_key=f"{scope}:{key}",
                    instante=instante,
                    payload={
                        "plan_id": plan.plan_id,
                        "plan_code": plan.plan_code,
                        "plan_version_id": result.plan_version_id,
                        "version_number": result.version_number,
                        "effective_from": inicio.isoformat(),
                    },
                )
            )
            return result

    def preview_versao_plano(
        self,
        *,
        contexto: ContextoExecucao,
        plan_version_id: str,
        instante: datetime | None = None,
    ) -> dict[str, object]:
        _exigir_admin(contexto)
        agora = utc(instante) if instante is not None else _agora()
        with self._session_factory() as session:
            repo = RepositorioCatalogoComercialSQLAlchemy(session)
            candidate = repo.obter_versao_plano(
                plan_version_id=plan_version_id.strip()
            )
            if candidate is None:
                raise RegistroComercialNaoEncontrado("plan_version_not_found")
            current = repo.versao_efetiva_plano(
                plan_id=candidate.plan_id,
                instante=agora,
            )
            return {
                "current": current,
                "candidate": candidate,
                "changes": self._diff_plan_versions(current, candidate),
            }

    @staticmethod
    def _diff_plan_versions(
        current: VersaoPlanoComercial | None,
        candidate: VersaoPlanoComercial,
    ) -> dict[str, object]:
        if current is None:
            return {"initial_configuration": True}
        current_ent = {item.capability_key: item for item in current.entitlements}
        candidate_ent = {
            item.capability_key: item for item in candidate.entitlements
        }
        entitlement_changes = sorted(
            key
            for key in set(current_ent) | set(candidate_ent)
            if current_ent.get(key) != candidate_ent.get(key)
        )
        fields = {}
        for field in (
            "display_name",
            "description",
            "trial_eligible",
            "marketing_badge",
            "metadata",
        ):
            before = getattr(current, field)
            after = getattr(candidate, field)
            if before != after:
                fields[field] = {"before": before, "after": after}
        return {
            "initial_configuration": False,
            "fields": fields,
            "entitlement_keys_changed": entitlement_changes,
        }

    def criar_preco(
        self,
        *,
        contexto: ContextoExecucao,
        idempotency_key: str,
        plan_version_id: str,
        currency: str,
        billing_period: str,
        amount: Decimal | str | float,
        change_policy: PoliticaMudancaPreco,
        change_reason: str,
    ) -> PrecoComercial:
        _exigir_admin(contexto)
        currency_norm = normalizar_currency(currency)
        period = normalizar_billing_period(billing_period)
        value = decimal_monetario(amount)
        reason = normalizar_reason(change_reason)
        key = _idempotency_key(idempotency_key)
        payload = {
            "plan_version_id": plan_version_id.strip(),
            "currency": currency_norm,
            "billing_period": period,
            "amount": str(value),
            "change_policy": change_policy.value,
            "change_reason": reason,
        }
        request_sha256 = _hash_payload(payload)

        try:
            with self._session_factory() as session, session.begin():
                catalog = RepositorioCatalogoComercialSQLAlchemy(session)
                shared = RepositorioComercialSQLAlchemy(session)
                plan_version = catalog.obter_versao_plano(
                    plan_version_id=plan_version_id.strip()
                )
                if plan_version is None:
                    raise RegistroComercialNaoEncontrado("plan_version_not_found")
                if plan_version.status != StatusConfiguracaoCatalogo.PUBLISHED:
                    raise DadoComercialInvalido(
                        "price_requires_published_plan_version"
                    )
                scope = (
                    "catalog.price.create:"
                    f"{plan_version.plan_version_id}:{currency_norm}:{period}"
                )
                existente = shared.obter_idempotencia(
                    scope=scope,
                    idempotency_key=key,
                )
                if existente is not None:
                    aggregate_id = self._validar_idempotencia(
                        registro=existente,
                        request_sha256=request_sha256,
                        aggregate_type="price",
                    )
                    result = catalog.obter_preco(price_id=aggregate_id)
                    if result is None:
                        raise ConflitoIdempotenciaComercial(
                            "idempotency_result_missing"
                        )
                    return result

                instante = _agora()
                price_id = str(uuid4())
                revision = catalog.proxima_revisao_preco(
                    plan_version_id=plan_version.plan_version_id,
                    currency=currency_norm,
                    billing_period=period,
                )
                result = catalog.adicionar_preco(
                    FMCommercialPriceORM(
                        price_id=price_id,
                        plan_version_id=plan_version.plan_version_id,
                        revision=revision,
                        currency=currency_norm,
                        billing_period=period,
                        amount=value,
                        change_policy=change_policy.value,
                        status=StatusConfiguracaoCatalogo.DRAFT.value,
                        valid_from=None,
                        valid_until=None,
                        change_reason=reason,
                        created_by=contexto.identity_user_id or contexto.usuario_id,
                        validated_by=None,
                        published_by=None,
                        created_at=instante,
                        validated_at=None,
                        published_at=None,
                    )
                )
                shared.adicionar_idempotencia(
                    scope=scope,
                    idempotency_key=key,
                    request_sha256=request_sha256,
                    aggregate_type="price",
                    aggregate_id=price_id,
                    created_at=instante,
                )
                shared.adicionar_auditoria(
                    self._auditoria(
                        contexto=contexto,
                        action="commercial.price.create",
                        aggregate_type="price",
                        aggregate_id=price_id,
                        reason=reason,
                        metadata_safe={
                            "currency": currency_norm,
                            "billing_period": period,
                            "revision": revision,
                            "change_policy": change_policy.value,
                        },
                        instante=instante,
                    )
                )
                return result
        except IntegrityError as exc:
            raise RegistroComercialDuplicado("price_duplicate") from exc

    def validar_preco(
        self,
        *,
        contexto: ContextoExecucao,
        price_id: str,
        change_reason: str,
    ) -> PrecoComercial:
        _exigir_admin(contexto)
        reason = normalizar_reason(change_reason)
        instante = _agora()
        with self._session_factory() as session, session.begin():
            catalog = RepositorioCatalogoComercialSQLAlchemy(session)
            shared = RepositorioComercialSQLAlchemy(session)
            atual = catalog.obter_preco(price_id=price_id.strip())
            if atual is None:
                raise RegistroComercialNaoEncontrado("price_not_found")
            validar_transicao_configuracao(
                atual.status,
                StatusConfiguracaoCatalogo.VALIDATED,
            )
            result = catalog.atualizar_status_preco(
                price_id=atual.price_id,
                expected_status=StatusConfiguracaoCatalogo.DRAFT,
                values={
                    "status": StatusConfiguracaoCatalogo.VALIDATED.value,
                    "validated_by": contexto.identity_user_id or contexto.usuario_id,
                    "validated_at": instante,
                },
            )
            shared.adicionar_auditoria(
                self._auditoria(
                    contexto=contexto,
                    action="commercial.price.validate",
                    aggregate_type="price",
                    aggregate_id=atual.price_id,
                    reason=reason,
                    metadata_safe={"revision": atual.revision},
                    instante=instante,
                )
            )
            return result

    def publicar_preco(
        self,
        *,
        contexto: ContextoExecucao,
        idempotency_key: str,
        price_id: str,
        expected_plan_version: int,
        effective_from: datetime,
        change_reason: str,
    ) -> PrecoComercial:
        _exigir_admin(contexto)
        inicio = utc(effective_from)
        reason = normalizar_reason(change_reason)
        key = _idempotency_key(idempotency_key)
        payload = {
            "price_id": price_id.strip(),
            "expected_plan_version": expected_plan_version,
            "effective_from": inicio.isoformat(),
            "change_reason": reason,
        }
        request_sha256 = _hash_payload(payload)
        scope = f"catalog.price.publish:{price_id.strip()}"

        with self._session_factory() as session, session.begin():
            catalog = RepositorioCatalogoComercialSQLAlchemy(session)
            shared = RepositorioComercialSQLAlchemy(session)
            existente = shared.obter_idempotencia(
                scope=scope,
                idempotency_key=key,
            )
            if existente is not None:
                aggregate_id = self._validar_idempotencia(
                    registro=existente,
                    request_sha256=request_sha256,
                    aggregate_type="price",
                )
                result = catalog.obter_preco(price_id=aggregate_id)
                if result is None:
                    raise ConflitoIdempotenciaComercial(
                        "idempotency_result_missing"
                    )
                return result

            candidate = catalog.obter_preco(price_id=price_id.strip())
            if candidate is None:
                raise RegistroComercialNaoEncontrado("price_not_found")
            validar_transicao_configuracao(
                candidate.status,
                StatusConfiguracaoCatalogo.PUBLISHED,
            )
            plan_version = catalog.obter_versao_plano(
                plan_version_id=candidate.plan_version_id
            )
            if plan_version is None:
                raise RegistroComercialNaoEncontrado("plan_version_not_found")
            plan = catalog.obter_plano(plan_id=plan_version.plan_id)
            if plan is None:
                raise RegistroComercialNaoEncontrado("plan_not_found")
            latest = catalog.ultimo_preco_publicado(
                plan_version_id=candidate.plan_version_id,
                currency=candidate.currency,
                billing_period=candidate.billing_period,
            )
            if latest is not None:
                if latest.valid_from is None or inicio <= latest.valid_from:
                    raise DadoComercialInvalido(
                        "effective_from_deve_ser_posterior_ultimo_preco"
                    )
                catalog.fechar_validade_preco(
                    price_id=latest.price_id,
                    valid_until=inicio,
                )

            instante = _agora()
            result = catalog.atualizar_status_preco(
                price_id=candidate.price_id,
                expected_status=StatusConfiguracaoCatalogo.VALIDATED,
                values={
                    "status": StatusConfiguracaoCatalogo.PUBLISHED.value,
                    "valid_from": inicio,
                    "published_by": contexto.identity_user_id or contexto.usuario_id,
                    "published_at": instante,
                },
            )
            catalog.marcar_plano_configurado(
                plan_id=plan.plan_id,
                expected_version=expected_plan_version,
                actor=contexto.identity_user_id or contexto.usuario_id,
                instante=instante,
            )
            shared.adicionar_idempotencia(
                scope=scope,
                idempotency_key=key,
                request_sha256=request_sha256,
                aggregate_type="price",
                aggregate_id=result.price_id,
                created_at=instante,
            )
            shared.adicionar_auditoria(
                self._auditoria(
                    contexto=contexto,
                    action="commercial.price.publish",
                    aggregate_type="price",
                    aggregate_id=result.price_id,
                    reason=reason,
                    metadata_safe={
                        "plan_code": plan.plan_code,
                        "currency": result.currency,
                        "billing_period": result.billing_period,
                        "revision": result.revision,
                        "change_policy": result.change_policy.value,
                        "effective_from": inicio.isoformat(),
                    },
                    instante=instante,
                )
            )
            shared.adicionar_outbox(
                self._evento(
                    contexto=contexto,
                    event_type="price.published",
                    aggregate_type="price",
                    aggregate_id=result.price_id,
                    idempotency_key=f"{scope}:{key}",
                    instante=instante,
                    payload={
                        "plan_id": plan.plan_id,
                        "plan_code": plan.plan_code,
                        "plan_version_id": result.plan_version_id,
                        "price_id": result.price_id,
                        "currency": result.currency,
                        "billing_period": result.billing_period,
                        "amount": str(result.amount),
                        "revision": result.revision,
                        "change_policy": result.change_policy.value,
                        "effective_from": inicio.isoformat(),
                    },
                )
            )
            return result

    def preview_preco(
        self, *, contexto: ContextoExecucao, price_id: str
    ) -> dict[str, object]:
        _exigir_admin(contexto)
        with self._session_factory() as session:
            repo = RepositorioCatalogoComercialSQLAlchemy(session)
            candidate = repo.obter_preco(price_id=price_id.strip())
            if candidate is None:
                raise RegistroComercialNaoEncontrado("price_not_found")
            current = repo.ultimo_preco_publicado(
                plan_version_id=candidate.plan_version_id,
                currency=candidate.currency,
                billing_period=candidate.billing_period,
            )
            return {
                "current": current,
                "candidate": candidate,
                "amount_change": (
                    None
                    if current is None
                    else {
                        "before": current.amount,
                        "after": candidate.amount,
                    }
                ),
                "change_policy": candidate.change_policy,
            }

    def criar_promocao(
        self,
        *,
        contexto: ContextoExecucao,
        idempotency_key: str,
        name: str,
        discount_type: TipoDescontoPromocao,
        discount_value: Decimal | str | float,
        currency: str | None,
        starts_at: datetime,
        ends_at: datetime | None,
        eligible_plan_codes: tuple[str, ...],
        max_redemptions: int | None,
        per_customer_limit: int | None,
        rules: dict[str, object],
        change_reason: str,
    ) -> tuple[PromocaoComercial, VersaoPromocaoComercial]:
        _exigir_admin(contexto)
        key = _idempotency_key(idempotency_key)
        nome = name.strip()
        if not nome or len(nome) > 128:
            raise DadoComercialInvalido("promotion_name_invalido")
        desconto, currency_norm = validar_desconto(
            discount_type,
            discount_value,
            currency,
        )
        inicio, fim = validar_intervalo(starts_at, ends_at)
        plans = tuple(dict.fromkeys(normalizar_plan_code(code) for code in eligible_plan_codes))
        if not plans:
            raise DadoComercialInvalido("promotion_requires_plan")
        if max_redemptions is not None and max_redemptions < 1:
            raise DadoComercialInvalido("max_redemptions_invalido")
        if per_customer_limit is not None and per_customer_limit < 1:
            raise DadoComercialInvalido("per_customer_limit_invalido")
        reason = normalizar_reason(change_reason)
        payload = {
            "name": nome,
            "discount_type": discount_type.value,
            "discount_value": str(desconto),
            "currency": currency_norm,
            "starts_at": inicio.isoformat(),
            "ends_at": fim.isoformat() if fim else None,
            "eligible_plan_codes": plans,
            "max_redemptions": max_redemptions,
            "per_customer_limit": per_customer_limit,
            "rules": rules,
            "change_reason": reason,
        }
        request_sha256 = _hash_payload(payload)
        scope = "catalog.promotion.create:KORDENA"

        try:
            with self._session_factory() as session, session.begin():
                catalog = RepositorioCatalogoComercialSQLAlchemy(session)
                shared = RepositorioComercialSQLAlchemy(session)
                existente = shared.obter_idempotencia(
                    scope=scope,
                    idempotency_key=key,
                )
                if existente is not None:
                    aggregate_id = self._validar_idempotencia(
                        registro=existente,
                        request_sha256=request_sha256,
                        aggregate_type="promotion",
                    )
                    promotion = catalog.obter_promocao(
                        promotion_id=aggregate_id
                    )
                    if promotion is None:
                        raise ConflitoIdempotenciaComercial(
                            "idempotency_result_missing"
                        )
                    latest_version = catalog.proximo_numero_versao_promocao(
                        promotion_id=promotion.promotion_id
                    ) - 1
                    row = session.scalar(
                        select(FMCommercialPromotionVersionORM).where(
                            FMCommercialPromotionVersionORM.promotion_id
                            == promotion.promotion_id,
                            FMCommercialPromotionVersionORM.version_number
                            == latest_version,
                        )
                    )
                    if row is None:
                        raise ConflitoIdempotenciaComercial(
                            "idempotency_result_missing"
                        )
                    version = catalog.obter_versao_promocao(
                        promotion_version_id=row.promotion_version_id
                    )
                    if version is None:
                        raise ConflitoIdempotenciaComercial(
                            "idempotency_result_missing"
                        )
                    return promotion, version

                plan_rows: list[PlanoComercial] = []
                for code in plans:
                    plan = catalog.obter_plano_por_codigo(plan_code=code)
                    if plan is None:
                        raise RegistroComercialNaoEncontrado("plan_not_found")
                    plan_rows.append(plan)

                instante = _agora()
                promotion_id = str(uuid4())
                promotion = catalog.adicionar_promocao(
                    FMCommercialPromotionORM(
                        promotion_id=promotion_id,
                        promotion_code=_promotion_code(promotion_id),
                        product_code="KORDENA",
                        status=StatusRegistroCatalogo.CONFIGURATION_PENDING.value,
                        created_by=contexto.identity_user_id or contexto.usuario_id,
                        updated_by=contexto.identity_user_id or contexto.usuario_id,
                        version=1,
                        created_at=instante,
                        updated_at=instante,
                    )
                )
                version = catalog.adicionar_versao_promocao(
                    FMCommercialPromotionVersionORM(
                        promotion_version_id=str(uuid4()),
                        promotion_id=promotion_id,
                        version_number=1,
                        name=nome,
                        discount_type=discount_type.value,
                        discount_value=desconto,
                        currency=currency_norm,
                        starts_at=inicio,
                        ends_at=fim,
                        max_redemptions=max_redemptions,
                        per_customer_limit=per_customer_limit,
                        rules_json=dict(rules),
                        status=StatusConfiguracaoCatalogo.DRAFT.value,
                        change_reason=reason,
                        created_by=contexto.identity_user_id or contexto.usuario_id,
                        validated_by=None,
                        published_by=None,
                        created_at=instante,
                        validated_at=None,
                        published_at=None,
                    ),
                    tuple(plan.plan_id for plan in plan_rows),
                )
                shared.adicionar_idempotencia(
                    scope=scope,
                    idempotency_key=key,
                    request_sha256=request_sha256,
                    aggregate_type="promotion",
                    aggregate_id=promotion_id,
                    created_at=instante,
                )
                shared.adicionar_auditoria(
                    self._auditoria(
                        contexto=contexto,
                        action="commercial.promotion.create",
                        aggregate_type="promotion",
                        aggregate_id=promotion_id,
                        reason=reason,
                        metadata_safe={
                            "promotion_code": promotion.promotion_code,
                            "eligible_plan_codes": plans,
                        },
                        instante=instante,
                    )
                )
                return promotion, version
        except IntegrityError as exc:
            raise RegistroComercialDuplicado("promotion_duplicate") from exc

    def criar_versao_promocao(
        self,
        *,
        contexto: ContextoExecucao,
        idempotency_key: str,
        promotion_id: str,
        name: str,
        discount_type: TipoDescontoPromocao,
        discount_value: Decimal | str | float,
        currency: str | None,
        starts_at: datetime,
        ends_at: datetime | None,
        eligible_plan_codes: tuple[str, ...],
        max_redemptions: int | None,
        per_customer_limit: int | None,
        rules: dict[str, object],
        change_reason: str,
    ) -> VersaoPromocaoComercial:
        _exigir_admin(contexto)
        key = _idempotency_key(idempotency_key)
        nome = name.strip()
        if not nome or len(nome) > 128:
            raise DadoComercialInvalido("promotion_name_invalido")
        desconto, currency_norm = validar_desconto(
            discount_type,
            discount_value,
            currency,
        )
        inicio, fim = validar_intervalo(starts_at, ends_at)
        plans = tuple(dict.fromkeys(normalizar_plan_code(code) for code in eligible_plan_codes))
        if not plans:
            raise DadoComercialInvalido("promotion_requires_plan")
        if max_redemptions is not None and max_redemptions < 1:
            raise DadoComercialInvalido("max_redemptions_invalido")
        if per_customer_limit is not None and per_customer_limit < 1:
            raise DadoComercialInvalido("per_customer_limit_invalido")
        reason = normalizar_reason(change_reason)
        payload = {
            "promotion_id": promotion_id.strip(),
            "name": nome,
            "discount_type": discount_type.value,
            "discount_value": str(desconto),
            "currency": currency_norm,
            "starts_at": inicio.isoformat(),
            "ends_at": fim.isoformat() if fim else None,
            "eligible_plan_codes": plans,
            "max_redemptions": max_redemptions,
            "per_customer_limit": per_customer_limit,
            "rules": rules,
            "change_reason": reason,
        }
        request_sha256 = _hash_payload(payload)

        try:
            with self._session_factory() as session, session.begin():
                catalog = RepositorioCatalogoComercialSQLAlchemy(session)
                shared = RepositorioComercialSQLAlchemy(session)
                promotion = catalog.obter_promocao(
                    promotion_id=promotion_id.strip()
                )
                if promotion is None:
                    raise RegistroComercialNaoEncontrado("promotion_not_found")
                scope = f"catalog.promotion_version.create:{promotion.promotion_id}"
                existente = shared.obter_idempotencia(
                    scope=scope,
                    idempotency_key=key,
                )
                if existente is not None:
                    aggregate_id = self._validar_idempotencia(
                        registro=existente,
                        request_sha256=request_sha256,
                        aggregate_type="promotion_version",
                    )
                    result = catalog.obter_versao_promocao(
                        promotion_version_id=aggregate_id
                    )
                    if result is None:
                        raise ConflitoIdempotenciaComercial(
                            "idempotency_result_missing"
                        )
                    return result

                plan_rows = []
                for code in plans:
                    plan = catalog.obter_plano_por_codigo(plan_code=code)
                    if plan is None:
                        raise RegistroComercialNaoEncontrado("plan_not_found")
                    plan_rows.append(plan)

                instante = _agora()
                version_number = catalog.proximo_numero_versao_promocao(
                    promotion_id=promotion.promotion_id
                )
                result = catalog.adicionar_versao_promocao(
                    FMCommercialPromotionVersionORM(
                        promotion_version_id=str(uuid4()),
                        promotion_id=promotion.promotion_id,
                        version_number=version_number,
                        name=nome,
                        discount_type=discount_type.value,
                        discount_value=desconto,
                        currency=currency_norm,
                        starts_at=inicio,
                        ends_at=fim,
                        max_redemptions=max_redemptions,
                        per_customer_limit=per_customer_limit,
                        rules_json=dict(rules),
                        status=StatusConfiguracaoCatalogo.DRAFT.value,
                        change_reason=reason,
                        created_by=contexto.identity_user_id or contexto.usuario_id,
                        validated_by=None,
                        published_by=None,
                        created_at=instante,
                        validated_at=None,
                        published_at=None,
                    ),
                    tuple(plan.plan_id for plan in plan_rows),
                )
                shared.adicionar_idempotencia(
                    scope=scope,
                    idempotency_key=key,
                    request_sha256=request_sha256,
                    aggregate_type="promotion_version",
                    aggregate_id=result.promotion_version_id,
                    created_at=instante,
                )
                shared.adicionar_auditoria(
                    self._auditoria(
                        contexto=contexto,
                        action="commercial.promotion_version.create",
                        aggregate_type="promotion_version",
                        aggregate_id=result.promotion_version_id,
                        reason=reason,
                        metadata_safe={
                            "promotion_code": promotion.promotion_code,
                            "version_number": version_number,
                            "eligible_plan_codes": plans,
                        },
                        instante=instante,
                    )
                )
                return result
        except IntegrityError as exc:
            raise RegistroComercialDuplicado("promotion_version_duplicate") from exc

    def validar_versao_promocao(
        self,
        *,
        contexto: ContextoExecucao,
        promotion_version_id: str,
        change_reason: str,
    ) -> VersaoPromocaoComercial:
        _exigir_admin(contexto)
        reason = normalizar_reason(change_reason)
        instante = _agora()
        with self._session_factory() as session, session.begin():
            catalog = RepositorioCatalogoComercialSQLAlchemy(session)
            shared = RepositorioComercialSQLAlchemy(session)
            atual = catalog.obter_versao_promocao(
                promotion_version_id=promotion_version_id.strip()
            )
            if atual is None:
                raise RegistroComercialNaoEncontrado(
                    "promotion_version_not_found"
                )
            validar_transicao_configuracao(
                atual.status,
                StatusConfiguracaoCatalogo.VALIDATED,
            )
            result = catalog.atualizar_status_versao_promocao(
                promotion_version_id=atual.promotion_version_id,
                expected_status=StatusConfiguracaoCatalogo.DRAFT,
                values={
                    "status": StatusConfiguracaoCatalogo.VALIDATED.value,
                    "validated_by": contexto.identity_user_id or contexto.usuario_id,
                    "validated_at": instante,
                },
            )
            shared.adicionar_auditoria(
                self._auditoria(
                    contexto=contexto,
                    action="commercial.promotion_version.validate",
                    aggregate_type="promotion_version",
                    aggregate_id=atual.promotion_version_id,
                    reason=reason,
                    metadata_safe={"version_number": atual.version_number},
                    instante=instante,
                )
            )
            return result

    def publicar_versao_promocao(
        self,
        *,
        contexto: ContextoExecucao,
        idempotency_key: str,
        promotion_version_id: str,
        expected_promotion_version: int,
        change_reason: str,
    ) -> VersaoPromocaoComercial:
        _exigir_admin(contexto)
        if expected_promotion_version < 1:
            raise DadoComercialInvalido("expected_promotion_version_invalida")
        reason = normalizar_reason(change_reason)
        key = _idempotency_key(idempotency_key)
        payload = {
            "promotion_version_id": promotion_version_id.strip(),
            "expected_promotion_version": expected_promotion_version,
            "change_reason": reason,
        }
        request_sha256 = _hash_payload(payload)
        scope = f"catalog.promotion_version.publish:{promotion_version_id.strip()}"

        with self._session_factory() as session, session.begin():
            catalog = RepositorioCatalogoComercialSQLAlchemy(session)
            shared = RepositorioComercialSQLAlchemy(session)
            existente = shared.obter_idempotencia(
                scope=scope,
                idempotency_key=key,
            )
            if existente is not None:
                aggregate_id = self._validar_idempotencia(
                    registro=existente,
                    request_sha256=request_sha256,
                    aggregate_type="promotion_version",
                )
                result = catalog.obter_versao_promocao(
                    promotion_version_id=aggregate_id
                )
                if result is None:
                    raise ConflitoIdempotenciaComercial(
                        "idempotency_result_missing"
                    )
                return result

            candidate = catalog.obter_versao_promocao(
                promotion_version_id=promotion_version_id.strip()
            )
            if candidate is None:
                raise RegistroComercialNaoEncontrado(
                    "promotion_version_not_found"
                )
            validar_transicao_configuracao(
                candidate.status,
                StatusConfiguracaoCatalogo.PUBLISHED,
            )
            promotion = catalog.obter_promocao(
                promotion_id=candidate.promotion_id
            )
            if promotion is None:
                raise RegistroComercialNaoEncontrado("promotion_not_found")
            latest = catalog.ultima_versao_publicada_promocao(
                promotion_id=promotion.promotion_id
            )
            if latest is not None:
                if candidate.starts_at <= latest.starts_at:
                    raise DadoComercialInvalido(
                        "promotion_start_deve_ser_posterior_ultima_publicacao"
                    )
                if latest.ends_at is None or latest.ends_at > candidate.starts_at:
                    catalog.fechar_validade_promocao(
                        promotion_version_id=latest.promotion_version_id,
                        ends_at=candidate.starts_at,
                    )

            instante = _agora()
            result = catalog.atualizar_status_versao_promocao(
                promotion_version_id=candidate.promotion_version_id,
                expected_status=StatusConfiguracaoCatalogo.VALIDATED,
                values={
                    "status": StatusConfiguracaoCatalogo.PUBLISHED.value,
                    "published_by": contexto.identity_user_id or contexto.usuario_id,
                    "published_at": instante,
                },
            )
            catalog.marcar_promocao_configurada(
                promotion_id=promotion.promotion_id,
                expected_version=expected_promotion_version,
                actor=contexto.identity_user_id or contexto.usuario_id,
                instante=instante,
            )
            shared.adicionar_idempotencia(
                scope=scope,
                idempotency_key=key,
                request_sha256=request_sha256,
                aggregate_type="promotion_version",
                aggregate_id=result.promotion_version_id,
                created_at=instante,
            )
            shared.adicionar_auditoria(
                self._auditoria(
                    contexto=contexto,
                    action="commercial.promotion_version.publish",
                    aggregate_type="promotion_version",
                    aggregate_id=result.promotion_version_id,
                    reason=reason,
                    metadata_safe={
                        "promotion_code": promotion.promotion_code,
                        "version_number": result.version_number,
                        "eligible_plan_codes": result.eligible_plan_codes,
                        "starts_at": result.starts_at.isoformat(),
                        "ends_at": (
                            result.ends_at.isoformat() if result.ends_at else None
                        ),
                    },
                    instante=instante,
                )
            )
            shared.adicionar_outbox(
                self._evento(
                    contexto=contexto,
                    event_type="promotion.version.published",
                    aggregate_type="promotion_version",
                    aggregate_id=result.promotion_version_id,
                    idempotency_key=f"{scope}:{key}",
                    instante=instante,
                    payload={
                        "promotion_id": promotion.promotion_id,
                        "promotion_code": promotion.promotion_code,
                        "promotion_version_id": result.promotion_version_id,
                        "version_number": result.version_number,
                        "eligible_plan_codes": result.eligible_plan_codes,
                        "starts_at": result.starts_at.isoformat(),
                        "ends_at": (
                            result.ends_at.isoformat() if result.ends_at else None
                        ),
                    },
                )
            )
            return result

    def listar_promocoes(
        self, *, contexto: ContextoExecucao
    ) -> tuple[dict[str, object], ...]:
        _exigir_admin(contexto)
        with self._session_factory() as session:
            repo = RepositorioCatalogoComercialSQLAlchemy(session)
            return tuple(
                {
                    "promotion": promotion,
                    "latest_published_version": (
                        repo.ultima_versao_publicada_promocao(
                            promotion_id=promotion.promotion_id
                        )
                    ),
                }
                for promotion in repo.listar_promocoes(product_code="KORDENA")
            )

    def preview_promocao(
        self,
        *,
        contexto: ContextoExecucao,
        promotion_version_id: str,
    ) -> dict[str, object]:
        _exigir_admin(contexto)
        with self._session_factory() as session:
            repo = RepositorioCatalogoComercialSQLAlchemy(session)
            candidate = repo.obter_versao_promocao(
                promotion_version_id=promotion_version_id.strip()
            )
            if candidate is None:
                raise RegistroComercialNaoEncontrado(
                    "promotion_version_not_found"
                )
            current = repo.ultima_versao_publicada_promocao(
                promotion_id=candidate.promotion_id
            )
            return {
                "current": current,
                "candidate": candidate,
                "discount_change": (
                    None
                    if current is None
                    else {
                        "type_before": current.discount_type,
                        "value_before": current.discount_value,
                        "type_after": candidate.discount_type,
                        "value_after": candidate.discount_value,
                    }
                ),
            }
