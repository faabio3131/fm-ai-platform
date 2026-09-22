"""Application boundary da Entitlement Authority KCA-04."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.comercial.catalogo import normalizar_plan_code
from core.comercial.entitlement import (
    DecisaoEntitlement,
    EntitlementNegado,
    EstadoComercial,
    ModoAcessoComercial,
    SnapshotEntitlement,
    capabilities_do_plano,
    capability_por_chave,
    desserializar_capabilities,
    modo_para_estado,
    normalizar_estado_comercial,
    serializar_capabilities,
    utc,
)
from core.comercial.erros import (
    ConflitoIdempotenciaComercial,
    DadoComercialInvalido,
    RegistroComercialDuplicado,
    RegistroComercialNaoEncontrado,
)
from core.comercial.modelos import StatusContaProduto
from core.seguranca.contexto import ContextoExecucao
from infra.comercial.catalogo_sqlalchemy import RepositorioCatalogoComercialSQLAlchemy
from infra.comercial.entitlement_orm import FMCommercialEntitlementSnapshotORM
from infra.comercial.entitlement_sqlalchemy import RepositorioEntitlementSQLAlchemy
from infra.comercial.modelos_orm import CommercialAuditORM, CommercialOutboxORM
from infra.comercial.repositorio_sqlalchemy import RepositorioComercialSQLAlchemy

SessionFactory = Callable[[], Session]


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _hash_payload(payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _key(valor: str) -> str:
    result = valor.strip()
    if not result or len(result) > 192:
        raise DadoComercialInvalido("idempotency_key_invalida")
    return result


class AplicacaoEntitlementComercialV1:
    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        stale_grace_seconds: int = 300,
        stale_fail_mode: ModoAcessoComercial = ModoAcessoComercial.BLOCKED,
    ) -> None:
        if stale_grace_seconds < 0:
            raise ValueError("stale_grace_seconds deve ser >= 0")
        if stale_fail_mode == ModoAcessoComercial.FULL:
            raise ValueError("stale_fail_mode nao pode ser FULL")
        self._session_factory = session_factory
        self._stale_grace = timedelta(seconds=stale_grace_seconds)
        self._stale_fail_mode = stale_fail_mode

    @staticmethod
    def _validar_idempotencia(*, registro, request_sha256: str) -> str:
        if registro.request_sha256 != request_sha256:
            raise ConflitoIdempotenciaComercial("idempotency_payload_conflict")
        if registro.aggregate_type != "entitlement_snapshot":
            raise ConflitoIdempotenciaComercial("idempotency_scope_conflict")
        return str(registro.aggregate_id)

    def recalcular(
        self,
        *,
        contexto: ContextoExecucao,
        idempotency_key: str,
        product_account_id: str,
        tenant_id: str,
        commercial_state: EstadoComercial | str,
        plan_code: str | None,
        valid_until: datetime,
        change_reason: str,
    ) -> SnapshotEntitlement:
        key = _key(idempotency_key)
        account_id = product_account_id.strip()
        tenant = tenant_id.strip()
        reason = change_reason.strip()
        if not account_id or not tenant or not reason:
            raise DadoComercialInvalido("entitlement_campos_obrigatorios")
        estado = normalizar_estado_comercial(commercial_state)
        until = utc(valid_until)
        instante = _agora()
        if until <= instante:
            raise DadoComercialInvalido("entitlement_valid_until_invalido")
        plan = normalizar_plan_code(plan_code) if plan_code is not None else None
        payload = {
            "product_account_id": account_id,
            "tenant_id": tenant,
            "commercial_state": estado.value,
            "plan_code": plan,
            "valid_until": until.isoformat(),
            "change_reason": reason,
        }
        request_sha256 = _hash_payload(payload)
        scope = f"entitlement.recalculate:{account_id}"

        try:
            with self._session_factory() as session, session.begin():
                shared = RepositorioComercialSQLAlchemy(session)
                entitlement = RepositorioEntitlementSQLAlchemy(session)
                catalog = RepositorioCatalogoComercialSQLAlchemy(session)
                existing = shared.obter_idempotencia(
                    scope=scope, idempotency_key=key
                )
                if existing is not None:
                    snapshot_id = self._validar_idempotencia(
                        registro=existing, request_sha256=request_sha256
                    )
                    result = entitlement.obter_snapshot(
                        entitlement_snapshot_id=snapshot_id
                    )
                    if result is None:
                        raise ConflitoIdempotenciaComercial(
                            "idempotency_result_missing"
                        )
                    return result

                account = shared.obter_conta_produto(account_id)
                if account is None:
                    raise RegistroComercialNaoEncontrado(
                        "product_account_not_found"
                    )
                if account.product_code != "KORDENA":
                    raise DadoComercialInvalido("product_code_nao_suportado")
                if account.product_tenant_id != tenant:
                    raise EntitlementNegado("tenant_product_account_mismatch")

                plan_version = None
                capabilities = ()
                if plan is not None:
                    plan_record = catalog.obter_plano_por_codigo(plan_code=plan)
                    if plan_record is None:
                        raise RegistroComercialNaoEncontrado("plan_not_found")
                    plan_version = catalog.versao_efetiva_plano(
                        plan_id=plan_record.plan_id, instante=instante
                    )
                    if plan_version is None:
                        raise RegistroComercialNaoEncontrado(
                            "effective_plan_version_not_found"
                        )
                    capabilities = capabilities_do_plano(plan_version.entitlements)

                access_mode = modo_para_estado(estado)
                if (
                    access_mode
                    in {
                        ModoAcessoComercial.FULL,
                        ModoAcessoComercial.LIMITED,
                    }
                    and account.status != StatusContaProduto.ACTIVE
                ):
                    raise EntitlementNegado("product_account_not_active")
                if (
                    access_mode
                    in {
                        ModoAcessoComercial.FULL,
                        ModoAcessoComercial.LIMITED,
                    }
                    and plan is None
                    and estado != EstadoComercial.INTERNAL_TEST
                ):
                    raise DadoComercialInvalido(
                        "plan_obrigatorio_para_acesso_comercial"
                    )

                revision = entitlement.proxima_revisao(
                    product_account_id=account_id
                )
                snapshot_id = str(uuid4())
                result = entitlement.adicionar_snapshot(
                    FMCommercialEntitlementSnapshotORM(
                        entitlement_snapshot_id=snapshot_id,
                        product_account_id=account_id,
                        tenant_id=tenant,
                        revision=revision,
                        commercial_state=estado.value,
                        plan_code=plan,
                        plan_version_id=(
                            plan_version.plan_version_id
                            if plan_version is not None
                            else None
                        ),
                        access_mode=access_mode.value,
                        capabilities_json=serializar_capabilities(capabilities),
                        effective_from=instante,
                        valid_until=until,
                        generated_at=instante,
                        correlation_id=contexto.correlation_id,
                        causation_id=contexto.causation_id,
                    )
                )
                shared.adicionar_idempotencia(
                    scope=scope,
                    idempotency_key=key,
                    request_sha256=request_sha256,
                    aggregate_type="entitlement_snapshot",
                    aggregate_id=snapshot_id,
                    created_at=instante,
                )
                actor = contexto.identity_user_id or contexto.usuario_id
                shared.adicionar_auditoria(
                    CommercialAuditORM(
                        audit_id=str(uuid4()),
                        actor_user_id=actor,
                        action="commercial.entitlement.recalculate",
                        aggregate_type="entitlement_snapshot",
                        aggregate_id=snapshot_id,
                        result="success",
                        reason=reason[:255],
                        correlation_id=contexto.correlation_id,
                        causation_id=contexto.causation_id,
                        metadata_safe={
                            "product_account_id": account_id,
                            "tenant_id": tenant,
                            "revision": revision,
                            "commercial_state": estado.value,
                            "plan_code": plan,
                            "access_mode": access_mode.value,
                        },
                        timestamp=instante,
                    )
                )
                shared.adicionar_outbox(
                    CommercialOutboxORM(
                        event_id=str(uuid4()),
                        event_type="entitlement.changed",
                        aggregate_type="entitlement_snapshot",
                        aggregate_id=snapshot_id,
                        fm_customer_id=account.fm_customer_id,
                        product_account_id=account_id,
                        product_code=account.product_code,
                        product_tenant_id=tenant,
                        correlation_id=contexto.correlation_id,
                        causation_id=contexto.causation_id,
                        idempotency_key=f"{scope}:{key}",
                        occurred_at=instante,
                        payload={
                            "entitlement_snapshot_id": snapshot_id,
                            "product_account_id": account_id,
                            "tenant_id": tenant,
                            "revision": revision,
                            "commercial_state": estado.value,
                            "plan_code": plan,
                            "plan_version_id": result.plan_version_id,
                            "access_mode": access_mode.value,
                            "capabilities": serializar_capabilities(capabilities),
                            "effective_from": instante.isoformat(),
                            "valid_until": until.isoformat(),
                        },
                        version=1,
                        status="pending",
                    )
                )
                return result
        except IntegrityError as exc:
            raise RegistroComercialDuplicado(
                "entitlement_snapshot_duplicate"
            ) from exc

    def aplicar_evento_local(
        self,
        *,
        event_id: str,
        payload: dict[str, object],
        received_at: datetime | None = None,
    ) -> bool:
        identifier = event_id.strip()
        if not identifier or len(identifier) > 64:
            raise DadoComercialInvalido("event_id_invalido")
        try:
            account_id = str(payload["product_account_id"]).strip()
            tenant_id = str(payload["tenant_id"]).strip()
            revision = int(payload["revision"])
            state = normalizar_estado_comercial(str(payload["commercial_state"]))
            access_mode = ModoAcessoComercial(str(payload["access_mode"]))
            capabilities_payload = payload["capabilities"]
            effective_from = datetime.fromisoformat(str(payload["effective_from"]))
            valid_until = datetime.fromisoformat(str(payload["valid_until"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise DadoComercialInvalido(
                "entitlement_event_payload_invalido"
            ) from exc
        if revision < 1 or not account_id or not tenant_id:
            raise DadoComercialInvalido("entitlement_event_payload_invalido")
        if not isinstance(capabilities_payload, dict):
            raise DadoComercialInvalido(
                "entitlement_event_capabilities_invalidas"
            )
        capabilities = desserializar_capabilities(capabilities_payload)
        effective = utc(effective_from)
        until = utc(valid_until)
        plan_code_raw = payload.get("plan_code")
        plan_version_raw = payload.get("plan_version_id")
        plan_code = (
            normalizar_plan_code(str(plan_code_raw))
            if plan_code_raw is not None
            else None
        )
        plan_version_id = (
            str(plan_version_raw) if plan_version_raw is not None else None
        )
        received = utc(received_at or _agora())

        with self._session_factory() as session, session.begin():
            repo = RepositorioEntitlementSQLAlchemy(session)
            if repo.evento_recebido(event_id=identifier):
                return False
            return repo.aplicar_evento(
                event_id=identifier,
                product_account_id=account_id,
                tenant_id=tenant_id,
                revision=revision,
                commercial_state=state,
                plan_code=plan_code,
                plan_version_id=plan_version_id,
                access_mode=access_mode,
                capabilities_json=serializar_capabilities(capabilities),
                effective_from=effective,
                valid_until=until,
                received_at=received,
            )

    def avaliar_local(
        self,
        *,
        tenant_id: str,
        product_account_id: str,
        capability_key: str | None = None,
        agora: datetime | None = None,
    ) -> DecisaoEntitlement:
        instante = utc(agora or _agora())
        with self._session_factory() as session:
            repo = RepositorioEntitlementSQLAlchemy(session)
            row = repo.obter_projecao(
                tenant_id=tenant_id.strip(),
                product_account_id=product_account_id.strip(),
            )
            if row is None:
                return DecisaoEntitlement(
                    allowed=False,
                    access_mode=ModoAcessoComercial.BLOCKED,
                    reason="entitlement_missing",
                    revision=None,
                    stale=False,
                )

            valid_until = utc(row.valid_until)
            stale = instante > valid_until
            if stale and instante > valid_until + self._stale_grace:
                return DecisaoEntitlement(
                    allowed=False,
                    access_mode=self._stale_fail_mode,
                    reason="entitlement_stale_limit_exceeded",
                    revision=row.revision,
                    stale=True,
                )

            mode = ModoAcessoComercial(row.access_mode)
            allowed = mode in {
                ModoAcessoComercial.FULL,
                ModoAcessoComercial.LIMITED,
            }
            capability = None
            reason = "entitlement_active"
            if capability_key is not None:
                capability = capability_por_chave(
                    repo.capabilities_projecao(row), capability_key
                )
                if capability is None or not capability.enabled:
                    return DecisaoEntitlement(
                        allowed=False,
                        access_mode=ModoAcessoComercial.BLOCKED,
                        reason="capability_not_entitled",
                        revision=row.revision,
                        stale=stale,
                        capability=capability,
                    )
                reason = "capability_entitled"

            return DecisaoEntitlement(
                allowed=allowed,
                access_mode=mode,
                reason=reason if allowed else "commercial_access_restricted",
                revision=row.revision,
                stale=stale,
                capability=capability,
            )

    def exigir_capacidade(
        self,
        *,
        tenant_id: str,
        product_account_id: str,
        capability_key: str,
        agora: datetime | None = None,
    ) -> DecisaoEntitlement:
        decisao = self.avaliar_local(
            tenant_id=tenant_id,
            product_account_id=product_account_id,
            capability_key=capability_key,
            agora=agora,
        )
        if not decisao.allowed:
            raise EntitlementNegado(decisao.reason)
        return decisao
