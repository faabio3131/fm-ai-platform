from core.pagamentos.flags import FlagsPagamentosV1
from core.pdv.adaptadores_sqlalchemy import (
    LegacyPDVSQLAlchemyAdapter,
    PonteProjecaoCompatLegadaPDVSQLAlchemy,
    RegistroFalhaShadowSQLAlchemy,
    RepositorioPDVSQLAlchemy,
    SQLAlchemyPDVUnitOfWork,
)
from core.pdv.executores import (
    EscritorShadowSQLAlchemy,
    ExecutorAutoritativoSQLAlchemy,
    id_deterministico,
)
from core.pdv.roteamento import ModoPDV, PDVFlags, PDVRolloutConfig
from core.pdv.servicos import finalizar_venda_pdv
from core.pedidos.flags import OrdersFeatureFlags
from infra.legacy_product_scope import obter_insumo_por_id_legado

from .conftest import ClienteTeste, FichaTeste, InsumoTeste, VendaTeste


def executar(factory, contexto, entrada, modo: ModoPDV, fault=None):
    canary = modo is ModoPDV.AUTHORITATIVE_CANARY
    config = PDVRolloutConfig(
        contexto.tenant_id,
        contexto.unidade_id,
        frozenset({entrada.terminal_id}),
        modo,
        PDVFlags(
            orders=OrdersFeatureFlags(
                orders_shadow_write=modo is ModoPDV.SHADOW,
                orders_authoritative=canary,
            ),
            payments=FlagsPagamentosV1(
                payments_v1_enabled=canary,
                sales_from_orders_enabled=canary,
                legacy_sale_adapter_enabled=canary,
            ),
            stock_ledger_authoritative=canary,
        ),
        True,
    )
    session = factory()
    pedido_id = id_deterministico(
        f"{contexto.tenant_id}:{contexto.unidade_id}:{entrada.idempotency_key}:pedido"
    )
    repo = RepositorioPDVSQLAlchemy(session)

    def resolver_insumo(legacy_insumo_id: int):
        comprovado = obter_insumo_por_id_legado(
            session,
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
            insumo_id=legacy_insumo_id,
            for_update=True,
        )
        if comprovado is None:
            return None
        return session.get(InsumoTeste, legacy_insumo_id)

    legado = LegacyPDVSQLAlchemyAdapter(
        session=session,
        venda_cls=VendaTeste,
        cliente_cls=ClienteTeste,
        insumo_cls=InsumoTeste,
        ficha_tecnica_cls=FichaTeste,
        tenant_id=contexto.tenant_id,
        unidade_id=contexto.unidade_id,
        pedido_id=pedido_id,
        rastrear_efeitos=modo is not ModoPDV.LEGACY,
        repositorio_pdv=repo,
        resolver_insumo=resolver_insumo,
    )
    uow = SQLAlchemyPDVUnitOfWork(factory, fechar=True, session=session, fault=fault)
    shadow_session = factory() if modo is ModoPDV.SHADOW else None
    shadow = (
        EscritorShadowSQLAlchemy(shadow_session, contexto) if shadow_session else None
    )
    shadow_uow = (
        SQLAlchemyPDVUnitOfWork(factory, fechar=True, session=shadow_session)
        if shadow_session
        else None
    )
    autoritativo = (
        ExecutorAutoritativoSQLAlchemy(
            session=session,
            contexto=contexto,
            legado=PonteProjecaoCompatLegadaPDVSQLAlchemy(legado),
            fault=fault,
        )
        if canary
        else None
    )
    return finalizar_venda_pdv(
        entrada=entrada,
        contexto=contexto,
        config=config,
        legado=legado,
        uow_legado=uow,
        shadow=shadow,
        uow_shadow=shadow_uow,
        reconciliacao=RegistroFalhaShadowSQLAlchemy(
            factory, contexto.tenant_id, contexto.unidade_id, contexto.correlation_id
        ),
        autoritativo=autoritativo,
        uow_autoritativo=uow if autoritativo else None,
    )
