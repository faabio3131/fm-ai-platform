"""Repositório SQLAlchemy do catálogo comercial KCA-03."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select, update
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
)
from core.comercial.erros import ConflitoConcorrenciaComercial

from .catalogo_orm import (
    FMCommercialPlanEntitlementORM,
    FMCommercialPlanORM,
    FMCommercialPlanVersionORM,
    FMCommercialPriceORM,
    FMCommercialPromotionORM,
    FMCommercialPromotionPlanORM,
    FMCommercialPromotionVersionORM,
)


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _plano(row: FMCommercialPlanORM) -> PlanoComercial:
    return PlanoComercial(
        plan_id=row.plan_id,
        product_code=row.product_code,
        plan_code=row.plan_code,
        rank=row.rank,
        status=StatusRegistroCatalogo(row.status),
        version=row.version,
        created_at=_utc(row.created_at),  # type: ignore[arg-type]
        updated_at=_utc(row.updated_at),  # type: ignore[arg-type]
    )


def _entitlement(row: FMCommercialPlanEntitlementORM) -> EntitlementPlano:
    return EntitlementPlano(
        capability_key=row.capability_key,
        enabled=row.enabled,
        limit_value=Decimal(row.limit_value) if row.limit_value is not None else None,
        limit_unit=row.limit_unit,
        config=dict(row.config_json or {}),
    )


def _versao_plano(
    row: FMCommercialPlanVersionORM,
    entitlements: tuple[EntitlementPlano, ...],
) -> VersaoPlanoComercial:
    return VersaoPlanoComercial(
        plan_version_id=row.plan_version_id,
        plan_id=row.plan_id,
        version_number=row.version_number,
        display_name=row.display_name,
        description=row.description,
        trial_eligible=row.trial_eligible,
        marketing_badge=row.marketing_badge,
        metadata=dict(row.metadata_json or {}),
        status=StatusConfiguracaoCatalogo(row.status),
        valid_from=_utc(row.valid_from),
        valid_until=_utc(row.valid_until),
        change_reason=row.change_reason,
        created_at=_utc(row.created_at),  # type: ignore[arg-type]
        validated_at=_utc(row.validated_at),
        published_at=_utc(row.published_at),
        entitlements=entitlements,
    )


def _preco(row: FMCommercialPriceORM) -> PrecoComercial:
    return PrecoComercial(
        price_id=row.price_id,
        plan_version_id=row.plan_version_id,
        revision=row.revision,
        currency=row.currency,
        billing_period=row.billing_period,
        amount=Decimal(row.amount),
        change_policy=PoliticaMudancaPreco(row.change_policy),
        status=StatusConfiguracaoCatalogo(row.status),
        valid_from=_utc(row.valid_from),
        valid_until=_utc(row.valid_until),
        change_reason=row.change_reason,
        created_at=_utc(row.created_at),  # type: ignore[arg-type]
        validated_at=_utc(row.validated_at),
        published_at=_utc(row.published_at),
    )


def _promocao(row: FMCommercialPromotionORM) -> PromocaoComercial:
    return PromocaoComercial(
        promotion_id=row.promotion_id,
        promotion_code=row.promotion_code,
        product_code=row.product_code,
        status=StatusRegistroCatalogo(row.status),
        version=row.version,
        created_at=_utc(row.created_at),  # type: ignore[arg-type]
        updated_at=_utc(row.updated_at),  # type: ignore[arg-type]
    )


class RepositorioCatalogoComercialSQLAlchemy:
    def __init__(self, session: Session) -> None:
        self._session = session

    def listar_planos(self, *, product_code: str) -> tuple[PlanoComercial, ...]:
        rows = self._session.scalars(
            select(FMCommercialPlanORM)
            .where(FMCommercialPlanORM.product_code == product_code)
            .order_by(FMCommercialPlanORM.rank)
        ).all()
        return tuple(_plano(row) for row in rows)

    def obter_plano_por_codigo(self, *, plan_code: str) -> PlanoComercial | None:
        row = self._session.scalar(
            select(FMCommercialPlanORM).where(
                FMCommercialPlanORM.plan_code == plan_code
            )
        )
        return _plano(row) if row is not None else None

    def obter_plano(self, *, plan_id: str) -> PlanoComercial | None:
        row = self._session.get(FMCommercialPlanORM, plan_id)
        return _plano(row) if row is not None else None

    def proximo_numero_versao_plano(self, *, plan_id: str) -> int:
        atual = self._session.scalar(
            select(func.max(FMCommercialPlanVersionORM.version_number)).where(
                FMCommercialPlanVersionORM.plan_id == plan_id
            )
        )
        return int(atual or 0) + 1

    def adicionar_versao_plano(
        self,
        row: FMCommercialPlanVersionORM,
        entitlements: tuple[FMCommercialPlanEntitlementORM, ...],
    ) -> VersaoPlanoComercial:
        self._session.add(row)
        self._session.flush()
        for entitlement in entitlements:
            self._session.add(entitlement)
        self._session.flush()
        return self.obter_versao_plano(plan_version_id=row.plan_version_id)  # type: ignore[return-value]

    def obter_versao_plano(
        self, *, plan_version_id: str
    ) -> VersaoPlanoComercial | None:
        row = self._session.get(FMCommercialPlanVersionORM, plan_version_id)
        if row is None:
            return None
        entitlements = tuple(
            _entitlement(item)
            for item in self._session.scalars(
                select(FMCommercialPlanEntitlementORM)
                .where(
                    FMCommercialPlanEntitlementORM.plan_version_id
                    == plan_version_id
                )
                .order_by(FMCommercialPlanEntitlementORM.capability_key)
            ).all()
        )
        return _versao_plano(row, entitlements)

    def atualizar_status_versao_plano(
        self,
        *,
        plan_version_id: str,
        expected_status: StatusConfiguracaoCatalogo,
        values: dict[str, object],
    ) -> VersaoPlanoComercial:
        statement = (
            update(FMCommercialPlanVersionORM)
            .where(
                FMCommercialPlanVersionORM.plan_version_id == plan_version_id,
                FMCommercialPlanVersionORM.status == expected_status.value,
            )
            .values(**values)
        )
        if self._session.execute(statement).rowcount != 1:
            raise ConflitoConcorrenciaComercial("plan_version_status_conflict")
        self._session.flush()
        result = self.obter_versao_plano(plan_version_id=plan_version_id)
        if result is None:
            raise ConflitoConcorrenciaComercial("plan_version_missing_after_update")
        return result

    def ultima_versao_publicada_plano(
        self, *, plan_id: str
    ) -> VersaoPlanoComercial | None:
        row = self._session.scalar(
            select(FMCommercialPlanVersionORM)
            .where(
                FMCommercialPlanVersionORM.plan_id == plan_id,
                FMCommercialPlanVersionORM.status
                == StatusConfiguracaoCatalogo.PUBLISHED.value,
            )
            .order_by(
                FMCommercialPlanVersionORM.valid_from.desc(),
                FMCommercialPlanVersionORM.version_number.desc(),
            )
            .limit(1)
        )
        if row is None:
            return None
        return self.obter_versao_plano(plan_version_id=row.plan_version_id)

    def versao_efetiva_plano(
        self, *, plan_id: str, instante: datetime
    ) -> VersaoPlanoComercial | None:
        row = self._session.scalar(
            select(FMCommercialPlanVersionORM)
            .where(
                FMCommercialPlanVersionORM.plan_id == plan_id,
                FMCommercialPlanVersionORM.status
                == StatusConfiguracaoCatalogo.PUBLISHED.value,
                FMCommercialPlanVersionORM.valid_from <= instante,
                (
                    (FMCommercialPlanVersionORM.valid_until.is_(None))
                    | (FMCommercialPlanVersionORM.valid_until > instante)
                ),
            )
            .order_by(FMCommercialPlanVersionORM.valid_from.desc())
            .limit(1)
        )
        if row is None:
            return None
        return self.obter_versao_plano(plan_version_id=row.plan_version_id)

    def fechar_validade_versao_plano(
        self, *, plan_version_id: str, valid_until: datetime
    ) -> None:
        self._session.execute(
            update(FMCommercialPlanVersionORM)
            .where(
                FMCommercialPlanVersionORM.plan_version_id == plan_version_id,
                FMCommercialPlanVersionORM.status
                == StatusConfiguracaoCatalogo.PUBLISHED.value,
            )
            .values(valid_until=valid_until)
        )
        self._session.flush()

    def marcar_plano_configurado(
        self,
        *,
        plan_id: str,
        expected_version: int,
        actor: str,
        instante: datetime,
    ) -> PlanoComercial:
        statement = (
            update(FMCommercialPlanORM)
            .where(
                FMCommercialPlanORM.plan_id == plan_id,
                FMCommercialPlanORM.version == expected_version,
            )
            .values(
                status=StatusRegistroCatalogo.CONFIGURED.value,
                updated_by=actor,
                updated_at=instante,
                version=expected_version + 1,
            )
        )
        if self._session.execute(statement).rowcount != 1:
            raise ConflitoConcorrenciaComercial("plan_version_conflict")
        self._session.flush()
        result = self.obter_plano(plan_id=plan_id)
        if result is None:
            raise ConflitoConcorrenciaComercial("plan_missing_after_update")
        return result

    def proxima_revisao_preco(
        self, *, plan_version_id: str, currency: str, billing_period: str
    ) -> int:
        atual = self._session.scalar(
            select(func.max(FMCommercialPriceORM.revision)).where(
                FMCommercialPriceORM.plan_version_id == plan_version_id,
                FMCommercialPriceORM.currency == currency,
                FMCommercialPriceORM.billing_period == billing_period,
            )
        )
        return int(atual or 0) + 1

    def adicionar_preco(self, row: FMCommercialPriceORM) -> PrecoComercial:
        self._session.add(row)
        self._session.flush()
        return _preco(row)

    def obter_preco(self, *, price_id: str) -> PrecoComercial | None:
        row = self._session.get(FMCommercialPriceORM, price_id)
        return _preco(row) if row is not None else None

    def atualizar_status_preco(
        self,
        *,
        price_id: str,
        expected_status: StatusConfiguracaoCatalogo,
        values: dict[str, object],
    ) -> PrecoComercial:
        statement = (
            update(FMCommercialPriceORM)
            .where(
                FMCommercialPriceORM.price_id == price_id,
                FMCommercialPriceORM.status == expected_status.value,
            )
            .values(**values)
        )
        if self._session.execute(statement).rowcount != 1:
            raise ConflitoConcorrenciaComercial("price_status_conflict")
        self._session.flush()
        result = self.obter_preco(price_id=price_id)
        if result is None:
            raise ConflitoConcorrenciaComercial("price_missing_after_update")
        return result

    def ultimo_preco_publicado(
        self,
        *,
        plan_version_id: str,
        currency: str,
        billing_period: str,
    ) -> PrecoComercial | None:
        row = self._session.scalar(
            select(FMCommercialPriceORM)
            .where(
                FMCommercialPriceORM.plan_version_id == plan_version_id,
                FMCommercialPriceORM.currency == currency,
                FMCommercialPriceORM.billing_period == billing_period,
                FMCommercialPriceORM.status
                == StatusConfiguracaoCatalogo.PUBLISHED.value,
            )
            .order_by(
                FMCommercialPriceORM.valid_from.desc(),
                FMCommercialPriceORM.revision.desc(),
            )
            .limit(1)
        )
        return _preco(row) if row is not None else None

    def fechar_validade_preco(self, *, price_id: str, valid_until: datetime) -> None:
        self._session.execute(
            update(FMCommercialPriceORM)
            .where(
                FMCommercialPriceORM.price_id == price_id,
                FMCommercialPriceORM.status
                == StatusConfiguracaoCatalogo.PUBLISHED.value,
            )
            .values(valid_until=valid_until)
        )
        self._session.flush()

    def listar_precos_versao(
        self, *, plan_version_id: str
    ) -> tuple[PrecoComercial, ...]:
        rows = self._session.scalars(
            select(FMCommercialPriceORM)
            .where(FMCommercialPriceORM.plan_version_id == plan_version_id)
            .order_by(
                FMCommercialPriceORM.currency,
                FMCommercialPriceORM.billing_period,
                FMCommercialPriceORM.revision,
            )
        ).all()
        return tuple(_preco(row) for row in rows)

    def adicionar_promocao(
        self, row: FMCommercialPromotionORM
    ) -> PromocaoComercial:
        self._session.add(row)
        self._session.flush()
        return _promocao(row)

    def obter_promocao(self, *, promotion_id: str) -> PromocaoComercial | None:
        row = self._session.get(FMCommercialPromotionORM, promotion_id)
        return _promocao(row) if row is not None else None

    def proximo_numero_versao_promocao(self, *, promotion_id: str) -> int:
        atual = self._session.scalar(
            select(func.max(FMCommercialPromotionVersionORM.version_number)).where(
                FMCommercialPromotionVersionORM.promotion_id == promotion_id
            )
        )
        return int(atual or 0) + 1

    def adicionar_versao_promocao(
        self,
        row: FMCommercialPromotionVersionORM,
        eligible_plan_ids: tuple[str, ...],
    ) -> VersaoPromocaoComercial:
        self._session.add(row)
        self._session.flush()
        for plan_id in eligible_plan_ids:
            self._session.add(
                FMCommercialPromotionPlanORM(
                    promotion_version_id=row.promotion_version_id,
                    plan_id=plan_id,
                )
            )
        self._session.flush()
        result = self.obter_versao_promocao(
            promotion_version_id=row.promotion_version_id
        )
        if result is None:
            raise ConflitoConcorrenciaComercial(
                "promotion_version_missing_after_create"
            )
        return result

    def obter_versao_promocao(
        self, *, promotion_version_id: str
    ) -> VersaoPromocaoComercial | None:
        row = self._session.get(
            FMCommercialPromotionVersionORM,
            promotion_version_id,
        )
        if row is None:
            return None
        codes = tuple(
            self._session.scalars(
                select(FMCommercialPlanORM.plan_code)
                .join(
                    FMCommercialPromotionPlanORM,
                    FMCommercialPromotionPlanORM.plan_id
                    == FMCommercialPlanORM.plan_id,
                )
                .where(
                    FMCommercialPromotionPlanORM.promotion_version_id
                    == promotion_version_id
                )
                .order_by(FMCommercialPlanORM.rank)
            ).all()
        )
        return VersaoPromocaoComercial(
            promotion_version_id=row.promotion_version_id,
            promotion_id=row.promotion_id,
            version_number=row.version_number,
            name=row.name,
            discount_type=TipoDescontoPromocao(row.discount_type),
            discount_value=Decimal(row.discount_value),
            currency=row.currency,
            starts_at=_utc(row.starts_at),  # type: ignore[arg-type]
            ends_at=_utc(row.ends_at),
            max_redemptions=row.max_redemptions,
            per_customer_limit=row.per_customer_limit,
            rules=dict(row.rules_json or {}),
            eligible_plan_codes=codes,
            status=StatusConfiguracaoCatalogo(row.status),
            change_reason=row.change_reason,
            created_at=_utc(row.created_at),  # type: ignore[arg-type]
            validated_at=_utc(row.validated_at),
            published_at=_utc(row.published_at),
        )

    def atualizar_status_versao_promocao(
        self,
        *,
        promotion_version_id: str,
        expected_status: StatusConfiguracaoCatalogo,
        values: dict[str, object],
    ) -> VersaoPromocaoComercial:
        statement = (
            update(FMCommercialPromotionVersionORM)
            .where(
                FMCommercialPromotionVersionORM.promotion_version_id
                == promotion_version_id,
                FMCommercialPromotionVersionORM.status == expected_status.value,
            )
            .values(**values)
        )
        if self._session.execute(statement).rowcount != 1:
            raise ConflitoConcorrenciaComercial("promotion_version_status_conflict")
        self._session.flush()
        result = self.obter_versao_promocao(
            promotion_version_id=promotion_version_id
        )
        if result is None:
            raise ConflitoConcorrenciaComercial(
                "promotion_version_missing_after_update"
            )
        return result

    def ultima_versao_publicada_promocao(
        self, *, promotion_id: str
    ) -> VersaoPromocaoComercial | None:
        row = self._session.scalar(
            select(FMCommercialPromotionVersionORM)
            .where(
                FMCommercialPromotionVersionORM.promotion_id == promotion_id,
                FMCommercialPromotionVersionORM.status
                == StatusConfiguracaoCatalogo.PUBLISHED.value,
            )
            .order_by(
                FMCommercialPromotionVersionORM.starts_at.desc(),
                FMCommercialPromotionVersionORM.version_number.desc(),
            )
            .limit(1)
        )
        if row is None:
            return None
        return self.obter_versao_promocao(
            promotion_version_id=row.promotion_version_id
        )

    def fechar_validade_promocao(
        self, *, promotion_version_id: str, ends_at: datetime
    ) -> None:
        self._session.execute(
            update(FMCommercialPromotionVersionORM)
            .where(
                FMCommercialPromotionVersionORM.promotion_version_id
                == promotion_version_id,
                FMCommercialPromotionVersionORM.status
                == StatusConfiguracaoCatalogo.PUBLISHED.value,
            )
            .values(ends_at=ends_at)
        )
        self._session.flush()

    def marcar_promocao_configurada(
        self,
        *,
        promotion_id: str,
        expected_version: int,
        actor: str,
        instante: datetime,
    ) -> PromocaoComercial:
        statement = (
            update(FMCommercialPromotionORM)
            .where(
                FMCommercialPromotionORM.promotion_id == promotion_id,
                FMCommercialPromotionORM.version == expected_version,
            )
            .values(
                status=StatusRegistroCatalogo.CONFIGURED.value,
                updated_by=actor,
                updated_at=instante,
                version=expected_version + 1,
            )
        )
        if self._session.execute(statement).rowcount != 1:
            raise ConflitoConcorrenciaComercial("promotion_version_conflict")
        self._session.flush()
        result = self.obter_promocao(promotion_id=promotion_id)
        if result is None:
            raise ConflitoConcorrenciaComercial("promotion_missing_after_update")
        return result

    def listar_promocoes(
        self, *, product_code: str
    ) -> tuple[PromocaoComercial, ...]:
        rows = self._session.scalars(
            select(FMCommercialPromotionORM)
            .where(FMCommercialPromotionORM.product_code == product_code)
            .order_by(FMCommercialPromotionORM.created_at)
        ).all()
        return tuple(_promocao(row) for row in rows)
