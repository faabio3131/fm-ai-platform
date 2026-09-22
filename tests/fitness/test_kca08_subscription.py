from sqlalchemy import create_engine, inspect

from core.comercial.subscription import EstadoAssinatura, validar_transicao_assinatura
from core.comercial.erros import TransicaoComercialInvalida
from migrations.runner import DEFAULT_MIGRATIONS, run_migrations


def test_kca08_subscription_migration_is_canonical() -> None:
    versions = tuple(migration.version for migration in DEFAULT_MIGRATIONS)
    index = versions.index("0056_commercial_subscription_v1")
    assert versions[index + 1] == "0057_commercial_billing_config_v1"

    engine = create_engine("sqlite:///:memory:")
    run_migrations(engine)
    assert "fm_commercial_subscriptions_v1" in set(
        inspect(engine).get_table_names()
    )


def test_kca08_subscription_state_machine_is_explicit() -> None:
    validar_transicao_assinatura(
        EstadoAssinatura.PENDING,
        EstadoAssinatura.ACTIVE,
    )
    validar_transicao_assinatura(
        EstadoAssinatura.PAST_DUE,
        EstadoAssinatura.ACTIVE,
    )
    validar_transicao_assinatura(
        EstadoAssinatura.SUSPENDED,
        EstadoAssinatura.ACTIVE,
    )

    try:
        validar_transicao_assinatura(
            EstadoAssinatura.CANCELED,
            EstadoAssinatura.ACTIVE,
        )
    except TransicaoComercialInvalida:
        pass
    else:
        raise AssertionError("canceled subscription must remain terminal")
