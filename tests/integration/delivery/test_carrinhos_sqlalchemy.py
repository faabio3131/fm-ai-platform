from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session, sessionmaker

from core.delivery.carrinho_orm import DeliveryChannelBase
from core.delivery.erros import ErroDelivery
from core.delivery.modelos import (
    CarrinhoDelivery,
    CotacaoEntrega,
    EnderecoDelivery,
    ItemCarrinhoDelivery,
    StatusCarrinhoDelivery,
)
from infra.delivery.carrinhos_sqlalchemy import RepositorioCarrinhosDeliverySQLAlchemy
from migrations.delivery_channel_state_v1 import (
    revert_delivery_channel_state_v1,
    upgrade_delivery_channel_state_v1,
)


def _carrinho(
    *,
    tenant_id: str = "tenant-a",
    unidade_id: str = "unidade-a",
    cliente_ref: str = "cliente-a",
    carrinho_id: str = "carrinho-a",
) -> CarrinhoDelivery:
    return CarrinhoDelivery(
        carrinho_id=carrinho_id,
        tenant_id=tenant_id,
        unidade_id=unidade_id,
        cliente_ref=cliente_ref,
        versao=1,
        status=StatusCarrinhoDelivery.ABERTO,
        itens=(
            ItemCarrinhoDelivery(
                produto_id="produto-1",
                nome="Produto 1",
                quantidade=2,
                preco_unitario=Decimal("12.50"),
                custo_estimado_unitario=Decimal("5.00"),
                produto_versao=3,
            ),
        ),
        endereco=EnderecoDelivery(
            endereco_id="endereco-1",
            cliente_ref=cliente_ref,
            cep="01001-000",
            logradouro="Praca da Se",
            numero="100",
            bairro="Se",
            cidade="Sao Paulo",
            uf="SP",
        ),
        cotacao=CotacaoEntrega(
            area_id="centro",
            nome_area="Centro",
            taxa=Decimal("7.90"),
            sla_minutos=25,
            sla_maxutos=45,
            versao_area=2,
        ),
    )


def test_migration_cria_e_reverte_tabela_do_canal() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        upgrade_delivery_channel_state_v1(connection)
    assert "delivery_carrinhos_v1" in inspect(engine).get_table_names()

    with engine.begin() as connection:
        revert_delivery_channel_state_v1(connection)
    assert "delivery_carrinhos_v1" not in inspect(engine).get_table_names()


def test_roundtrip_preserva_snapshot_e_escopo_cliente() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    DeliveryChannelBase.metadata.create_all(engine)
    with Session(engine) as session:
        repo = RepositorioCarrinhosDeliverySQLAlchemy(session)
        original = _carrinho()
        repo.criar(original)
        session.commit()

        obtido = repo.obter(
            tenant_id="tenant-a",
            unidade_id="unidade-a",
            carrinho_id="carrinho-a",
        )
        assert obtido == original
        assert repo.obter_do_cliente(
            tenant_id="tenant-a",
            unidade_id="unidade-a",
            cliente_ref="cliente-a",
            carrinho_id="carrinho-a",
        ) == original
        assert repo.obter_do_cliente(
            tenant_id="tenant-a",
            unidade_id="unidade-a",
            cliente_ref="cliente-b",
            carrinho_id="carrinho-a",
        ) is None
        assert repo.obter(
            tenant_id="tenant-b",
            unidade_id="unidade-a",
            carrinho_id="carrinho-a",
        ) is None


def test_cas_rejeita_writer_com_versao_obsoleta(tmp_path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'delivery.db'}")
    DeliveryChannelBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    with factory() as seed:
        RepositorioCarrinhosDeliverySQLAlchemy(seed).criar(_carrinho())
        seed.commit()

    with factory() as session_a, factory() as session_b:
        repo_a = RepositorioCarrinhosDeliverySQLAlchemy(session_a)
        repo_b = RepositorioCarrinhosDeliverySQLAlchemy(session_b)
        base_a = repo_a.obter(
            tenant_id="tenant-a",
            unidade_id="unidade-a",
            carrinho_id="carrinho-a",
        )
        base_b = repo_b.obter(
            tenant_id="tenant-a",
            unidade_id="unidade-a",
            carrinho_id="carrinho-a",
        )
        assert base_a is not None
        assert base_b is not None

        repo_a.salvar_cas(
            replace(base_a, versao=2),
            expected_version=1,
        )
        session_a.commit()

        with pytest.raises(ErroDelivery) as exc_info:
            repo_b.salvar_cas(
                replace(base_b, versao=2),
                expected_version=1,
            )
        assert exc_info.value.codigo == "conflito_concorrencia"
        session_b.rollback()


def test_mesmo_id_pode_existir_em_outro_tenant_sem_vazamento() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    DeliveryChannelBase.metadata.create_all(engine)
    with Session(engine) as session:
        repo = RepositorioCarrinhosDeliverySQLAlchemy(session)
        repo.criar(_carrinho())
        repo.criar(_carrinho(tenant_id="tenant-b"))
        session.commit()

        tenant_a = repo.obter(
            tenant_id="tenant-a",
            unidade_id="unidade-a",
            carrinho_id="carrinho-a",
        )
        tenant_b = repo.obter(
            tenant_id="tenant-b",
            unidade_id="unidade-a",
            carrinho_id="carrinho-a",
        )
        assert tenant_a is not None
        assert tenant_b is not None
        assert tenant_a.tenant_id == "tenant-a"
        assert tenant_b.tenant_id == "tenant-b"
