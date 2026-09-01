from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from core.delivery.modelos import AreaEntrega
from core.delivery.modelos_orm import DeliveryPolicyBase
from infra.delivery.politica_sqlalchemy import RepositorioPoliticaEntregaSQLAlchemy


def test_politica_entrega_isola_tenant_unidade_e_persiste_origem_area():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    DeliveryPolicyBase.metadata.create_all(engine)

    with Session(engine) as session:
        repo = RepositorioPoliticaEntregaSQLAlchemy(session)
        origem = repo.configurar_origem(
            tenant_id="tenant-a",
            unidade_id="unidade-a",
            endereco_texto="Rua da Loja, 100 - Centro, Cidade - SP, 01000-000",
        )
        area = repo.configurar_area(
            area=AreaEntrega(
                area_id="centro",
                tenant_id="tenant-a",
                unidade_id="unidade-a",
                nome="Centro",
                prefixos_cep=("010", "011"),
                taxa=Decimal("8.50"),
                sla_minutos=30,
                sla_maxutos=50,
                versao=1,
            )
        )
        session.commit()

        assert origem.endereco_texto.startswith("Rua da Loja")
        assert area.taxa == Decimal("8.50")
        assert repo.obter_origem(
            tenant_id="tenant-a", unidade_id="unidade-a"
        ) is not None
        assert repo.obter_origem(
            tenant_id="tenant-b", unidade_id="unidade-a"
        ) is None
        assert repo.listar_areas(
            tenant_id="tenant-a", unidade_id="unidade-a"
        ) == (area,)
        assert repo.listar_areas(
            tenant_id="tenant-a", unidade_id="unidade-b"
        ) == ()


def test_reconfiguracao_incrementa_versao_sem_criar_duplicata():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    DeliveryPolicyBase.metadata.create_all(engine)

    with Session(engine) as session:
        repo = RepositorioPoliticaEntregaSQLAlchemy(session)
        primeira = repo.configurar_area(
            area=AreaEntrega(
                area_id="zona-1",
                tenant_id="tenant-a",
                unidade_id="unidade-a",
                nome="Zona 1",
                prefixos_cep=("012",),
                taxa=Decimal("5.00"),
                sla_minutos=25,
                sla_maxutos=45,
                versao=1,
            )
        )
        segunda = repo.configurar_area(
            area=AreaEntrega(
                area_id="zona-1",
                tenant_id="tenant-a",
                unidade_id="unidade-a",
                nome="Zona 1 atualizada",
                prefixos_cep=("012", "013"),
                taxa=Decimal("7.00"),
                sla_minutos=30,
                sla_maxutos=50,
                versao=1,
            )
        )
        session.commit()

        assert primeira.versao == 1
        assert segunda.versao == 2
        assert segunda.taxa == Decimal("7.00")
        assert len(
            repo.listar_areas(tenant_id="tenant-a", unidade_id="unidade-a")
        ) == 1
