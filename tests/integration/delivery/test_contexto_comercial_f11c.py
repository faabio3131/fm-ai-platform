from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from application.delivery_contexto_comercial import resolver_contexto_delivery_comercial
from core.delivery.erros import ErroDelivery
from core.delivery.modelos import AreaEntrega
from core.delivery.modelos_orm import DeliveryPolicyBase
from core.seguranca.autenticacao import IdentidadeUsuario
from core.seguranca.permissoes import Papel
from infra.crm.enderecos_schema import crm_enderecos_seguros_v1
from infra.crm.enderecos_sqlalchemy import EncryptedSQLAlchemyAddressStore
from infra.delivery.politica_sqlalchemy import RepositorioPoliticaEntregaSQLAlchemy

_TENANT = "tenant-f11c"
_UNIDADE = "unidade-f11c"
_KEY = Fernet.generate_key().decode("ascii")


def _identidade(
    *, tenant_id: str = _TENANT, unidade_id: str = _UNIDADE
) -> IdentidadeUsuario:
    return IdentidadeUsuario(
        usuario_id="admin-f11c",
        email="admin-f11c@example.invalid",
        senha_hash="hash-test-f11c",
        tenant_id=tenant_id,
        unidade_id=unidade_id,
        papeis=frozenset({Papel.ADMINISTRADOR}),
        unidades_permitidas=frozenset({unidade_id}),
        ativo=True,
    )


def _criar_schema(session: Session) -> None:
    ddl = (
        """
        CREATE TABLE fm_unidade_loja_legacy_v1 (
            tenant_id VARCHAR(64) NOT NULL,
            unidade_id VARCHAR(64) NOT NULL,
            loja_id INTEGER NOT NULL,
            ativo BOOLEAN NOT NULL,
            PRIMARY KEY (tenant_id, unidade_id)
        )
        """,
        """
        CREATE TABLE produtos (
            id INTEGER PRIMARY KEY,
            nome VARCHAR(160) NOT NULL,
            preco_venda NUMERIC NOT NULL,
            custo_total_cmv NUMERIC,
            loja_id INTEGER NOT NULL
        )
        """,
        """
        CREATE TABLE insumos (
            id INTEGER PRIMARY KEY,
            nome VARCHAR(160) NOT NULL,
            unidade_medida VARCHAR(32) NOT NULL,
            saldo_atual NUMERIC NOT NULL,
            loja_id INTEGER NOT NULL
        )
        """,
        """
        CREATE TABLE fichas_tecnicas (
            id INTEGER PRIMARY KEY,
            produto_id INTEGER NOT NULL,
            insumo_id INTEGER NOT NULL,
            quantidade_utilizada NUMERIC NOT NULL
        )
        """,
        """
        CREATE TABLE crm_clientes_v1 (
            tenant_id VARCHAR(64) NOT NULL,
            unidade_id VARCHAR(64) NOT NULL,
            cliente_id VARCHAR(64) NOT NULL,
            origem VARCHAR(32) NOT NULL,
            marketplace_origem VARCHAR(32),
            criado_em TIMESTAMP NOT NULL,
            versao INTEGER NOT NULL,
            PRIMARY KEY (tenant_id, unidade_id, cliente_id)
        )
        """,
        """
        CREATE TABLE crm_cliente_contatos_v1 (
            tenant_id VARCHAR(64) NOT NULL,
            unidade_id VARCHAR(64) NOT NULL,
            cliente_id VARCHAR(64) NOT NULL,
            canal VARCHAR(32) NOT NULL,
            referencia VARCHAR(512) NOT NULL,
            PRIMARY KEY (tenant_id, unidade_id, cliente_id, canal)
        )
        """,
    )
    for statement in ddl:
        session.execute(text(statement))

    DeliveryPolicyBase.metadata.create_all(bind=session.connection(), checkfirst=True)
    crm_enderecos_seguros_v1.create(bind=session.connection(), checkfirst=True)


def _seed(session: Session) -> dict[str, str]:
    _criar_schema(session)
    agora = datetime(2026, 9, 5, 4, 0, tzinfo=timezone.utc)

    session.execute(
        text(
            "INSERT INTO fm_unidade_loja_legacy_v1 "
            "(tenant_id, unidade_id, loja_id, ativo) VALUES "
            "(:tenant, :unidade, 1, TRUE), "
            "('tenant-outro', 'unidade-outra', 2, TRUE)"
        ),
        {"tenant": _TENANT, "unidade": _UNIDADE},
    )
    session.execute(
        text(
            "INSERT INTO produtos (id, nome, preco_venda, custo_total_cmv, loja_id) "
            "VALUES (1, 'Pizza canônica', 50, 20, 1), "
            "(2, 'Produto de outra unidade', 99, 30, 2)"
        )
    )
    session.execute(
        text(
            "INSERT INTO insumos (id, nome, unidade_medida, saldo_atual, loja_id) "
            "VALUES (1, 'Massa', 'un', 10, 1), "
            "(2, 'Queijo', 'kg', 3, 1), "
            "(3, 'Insumo externo', 'un', 500, 2)"
        )
    )
    session.execute(
        text(
            "INSERT INTO fichas_tecnicas "
            "(id, produto_id, insumo_id, quantidade_utilizada) VALUES "
            "(1, 1, 1, 2), (2, 1, 2, 0.5), (3, 2, 3, 1)"
        )
    )

    for cliente_id, tenant_id, unidade_id in (
        ("cliente-f11c", _TENANT, _UNIDADE),
        ("cliente-f11c-2", _TENANT, _UNIDADE),
        ("cliente-externo", "tenant-outro", "unidade-outra"),
    ):
        session.execute(
            text(
                "INSERT INTO crm_clientes_v1 "
                "(tenant_id, unidade_id, cliente_id, origem, marketplace_origem, "
                "criado_em, versao) VALUES "
                "(:tenant, :unidade, :cliente, 'delivery_proprio', NULL, :agora, 1)"
            ),
            {
                "tenant": tenant_id,
                "unidade": unidade_id,
                "cliente": cliente_id,
                "agora": agora,
            },
        )
        session.execute(
            text(
                "INSERT INTO crm_cliente_contatos_v1 "
                "(tenant_id, unidade_id, cliente_id, canal, referencia) VALUES "
                "(:tenant, :unidade, :cliente, 'whatsapp', :ref)"
            ),
            {
                "tenant": tenant_id,
                "unidade": unidade_id,
                "cliente": cliente_id,
                "ref": f"contact://{cliente_id}",
            },
        )

    politica = RepositorioPoliticaEntregaSQLAlchemy(session)
    politica.configurar_origem(
        tenant_id=_TENANT,
        unidade_id=_UNIDADE,
        endereco_texto="Rua da Unidade, 100 - São Paulo/SP",
    )
    politica.configurar_area(
        area=AreaEntrega(
            area_id="centro-f11c",
            tenant_id=_TENANT,
            unidade_id=_UNIDADE,
            nome="Centro",
            prefixos_cep=("010",),
            taxa=Decimal("7.50"),
            sla_minutos=30,
            sla_maxutos=50,
            versao=1,
        )
    )

    contexto = _identidade().contexto(
        origem="seed-f11c",
        solicitado_em=agora,
        correlation_id="corr-seed-f11c",
    )
    enderecos = EncryptedSQLAlchemyAddressStore(session, master_key=_KEY)
    principal = enderecos.armazenar_validado(
        contexto=contexto,
        cliente_id="cliente-f11c",
        endereco_formatado="Rua Cliente, 10 - Centro - São Paulo/SP",
        cep="01001-000",
        place_id="place-f11c-principal",
        latitude=Decimal("-23.5505"),
        longitude=Decimal("-46.6333"),
        agora=agora,
    )
    outro = enderecos.armazenar_validado(
        contexto=contexto,
        cliente_id="cliente-f11c-2",
        endereco_formatado="Rua Outro Cliente, 20 - Centro - São Paulo/SP",
        cep="01002-000",
        place_id="place-f11c-outro",
        latitude=Decimal("-23.5510"),
        longitude=Decimal("-46.6340"),
        agora=agora,
    )
    session.commit()
    return {"principal": principal, "outro": outro}


@pytest.fixture
def sessao() -> tuple[Session, dict[str, str]]:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    session = Session(engine)
    refs = _seed(session)
    try:
        yield session, refs
    finally:
        session.close()
        engine.dispose()


def test_contexto_comercial_deriva_escopo_e_fontes_canonicas(
    sessao: tuple[Session, dict[str, str]],
) -> None:
    session, _ = sessao

    resolvido = resolver_contexto_delivery_comercial(
        session=session,
        identidade=_identidade(),
        cliente_id="cliente-f11c",
        master_key=_KEY,
    )

    assert resolvido.contexto.tenant_id == _TENANT
    assert resolvido.contexto.unidade_id == _UNIDADE
    assert resolvido.contexto.usuario_id == "admin-f11c"
    assert resolvido.cliente.cliente_id == "cliente-f11c"
    assert resolvido.endereco.referencia.startswith("address://")
    assert resolvido.endereco.place_id == "place-f11c-principal"
    assert resolvido.endereco.cep == "01001000"
    assert resolvido.origem_entrega.tenant_id == _TENANT
    assert [area.area_id for area in resolvido.areas_entrega] == ["centro-f11c"]
    assert [produto.produto_id for produto in resolvido.catalogo] == [
        "legacy:produto:1"
    ]
    # Massa permite 5 unidades; queijo permite 6. O catálogo anuncia o menor teto.
    assert resolvido.catalogo[0].estoque_disponivel == Decimal("5")
    assert resolvido.catalogo[0].preco == Decimal("50.00")


def test_cliente_de_outro_escopo_falha_fechado(
    sessao: tuple[Session, dict[str, str]],
) -> None:
    session, _ = sessao

    with pytest.raises(ErroDelivery, match="cliente_delivery_indisponivel"):
        resolver_contexto_delivery_comercial(
            session=session,
            identidade=_identidade(),
            cliente_id="cliente-externo",
            master_key=_KEY,
        )


def test_endereco_de_outro_cliente_nao_vaza_dados(
    sessao: tuple[Session, dict[str, str]],
) -> None:
    session, refs = sessao

    with pytest.raises(ErroDelivery, match="endereco_delivery_indisponivel"):
        resolver_contexto_delivery_comercial(
            session=session,
            identidade=_identidade(),
            cliente_id="cliente-f11c",
            endereco_ref=refs["outro"],
            master_key=_KEY,
        )


def test_politica_ausente_falha_fechado(
    sessao: tuple[Session, dict[str, str]],
) -> None:
    session, _ = sessao
    session.execute(
        text(
            "UPDATE delivery_origem_unidade_v1 SET ativa = FALSE "
            "WHERE tenant_id = :tenant AND unidade_id = :unidade"
        ),
        {"tenant": _TENANT, "unidade": _UNIDADE},
    )
    session.commit()

    with pytest.raises(ErroDelivery, match="origem_delivery_indisponivel"):
        resolver_contexto_delivery_comercial(
            session=session,
            identidade=_identidade(),
            cliente_id="cliente-f11c",
            master_key=_KEY,
        )
