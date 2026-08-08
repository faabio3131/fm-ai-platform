from core.pagamentos.flags import FlagsPagamentosV1
from core.pdv.adaptadores_sqlalchemy import (
    LegacyPDVSQLAlchemyAdapter,
    RegistroFalhaShadowSQLAlchemy,
    RepositorioPDVSQLAlchemy,
    SQLAlchemyPDVUnitOfWork,
)
from core.pdv.executores import (
    ExecutorAutoritativoSQLAlchemy,
    EscritorShadowSQLAlchemy,
    id_deterministico,
)
from core.pdv.roteamento import ModoPDV, PDVFlags, PDVRolloutConfig
from core.pdv.servicos import finalizar_venda_pdv
from core.pedidos.flags import OrdersFeatureFlags

from .conftest import ClienteTeste, FichaTeste, InsumoTeste, VendaTeste


def executar(factory, contexto, entrada, modo: ModoPDV, fault=None):
    config = PDVRolloutConfig(
        contexto.tenant_id,
        contexto.unidade_id,
        frozenset({entrada.terminal_id}),
        modo,
        PDVFlags(
            OrdersFeatureFlags(
                orders_shadow_write=modo is ModoPDV.SHADOW,
                orders_authoritative=modo is ModoPDV.AUTHORITATIVE_CANARY,
            ),
            FlagsPagamentosV1(
                payments_v1_enabled=modo is ModoPDV.AUTHORITATIVE_CANARY,
                sales_from_orders_enabled=modo is ModoPDV.AUTHORITATIVE_CANARY,
                legacy_sale_adapter_enabled=modo is ModoPDV.AUTHORITATIVE_CANARY,
            ),
        ),
        True,
    )
    session = factory()
    pedido_id = id_deterministico(
        f"{contexto.tenant_id}:{contexto.unidade_id}:{entrada.idempotency_key}:pedido"
    )
    repo = RepositorioPDVSQLAlchemy(session)
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
            session=session, contexto=contexto, legado=legado, fault=fault
        )
        if modo is ModoPDV.AUTHORITATIVE_CANARY
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
