from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, insert, inspect, select
from sqlalchemy.orm import Session, sessionmaker

from application.assistente_atendimento_runtime import _raw_historico_autorizado
from core.assistente_atendimento.atendimento_modelos import ProdutoCatalogoAtendimento
from core.crm.modelos import CanalMarketing, ClienteCRM, ContatoCRM, OrigemClienteCRM
from core.pedidos.modelos_orm import ItemPedidoORM, PedidoORM
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Permissao
from infra.assistente_atendimento.contexto_cliente_sqlalchemy import (
    ContextoClienteAtendimentoSQLAlchemy,
)
from infra.assistente_atendimento.handoff_sqlalchemy import (
    HandoffAssistenteAuditSQLAlchemy,
)
from infra.crm.consentimentos_schema import crm_consentimentos_v1
from infra.crm.enderecos_schema import crm_enderecos_seguros_v1
from infra.crm.enderecos_sqlalchemy import EncryptedSQLAlchemyAddressStore
from infra.gerente_ia.persistencia_sqlalchemy import RepositorioClientesCRMSQLAlchemy
from migrations.manifest import assert_migration_manifest
from migrations.runner import DEFAULT_MIGRATIONS, run_migrations

AGORA = datetime(2026, 8, 31, 22, 30, tzinfo=timezone.utc)
TENANT = "tenant-a"
UNIDADE = "unidade-a"
CLIENTE = "cliente-a"


def _factory():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    run_migrations(engine)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)


def _contexto(
    *,
    tenant: str = TENANT,
    unidade: str = UNIDADE,
) -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id=tenant,
        unidade_id=unidade,
        usuario_id="assistente-atendimento-v1",
        papeis=frozenset(),
        permissoes=frozenset(
            {
                Permissao.CLIENTE_VISUALIZAR,
                Permissao.CLIENTE_EDITAR,
            }
        ),
        correlation_id=f"corr:{tenant}:{unidade}",
        solicitado_em=AGORA,
        origem="test.f4c",
        unidades_permitidas=frozenset({unidade}),
    )


def _seed_cliente(session: Session) -> None:
    RepositorioClientesCRMSQLAlchemy(session).registrar(
        ClienteCRM(
            cliente_id=CLIENTE,
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            origem=OrigemClienteCRM.MANUAL,
            contatos=(
                ContatoCRM(
                    canal=CanalMarketing.WHATSAPP,
                    referencia="contact://cliente-a",
                ),
            ),
            criado_em=AGORA - timedelta(days=30),
        )
    )


def _seed_pedido(session: Session) -> None:
    pedido = PedidoORM(
        id="pedido-historico-1",
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        origem="whatsapp",
        canal="whatsapp",
        status="concluido",
        cliente_id=CLIENTE,
        criado_em=AGORA - timedelta(days=1),
        atualizado_em=AGORA - timedelta(days=1),
        versao=3,
        correlation_id="corr:pedido",
        idempotency_key="idem:pedido",
        request_hash="a" * 64,
        subtotal=Decimal("50.00"),
        descontos=Decimal("0.00"),
        taxas=Decimal("0.00"),
        total=Decimal("50.00"),
    )
    pedido.itens = [
        ItemPedidoORM(
            id="item-historico-1",
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            pedido_id=pedido.id,
            ordem=1,
            produto_id="101",
            nome_produto="X-Bacon Antigo",
            quantidade=2,
            preco_unitario=Decimal("25.00"),
            subtotal=Decimal("50.00"),
            observacao=None,
            ficha_versao="ficha-v1",
        )
    ]
    session.add(pedido)


def _seed_consentimento(session: Session) -> None:
    session.execute(
        insert(crm_consentimentos_v1).values(
            consentimento_id="cons-1",
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            cliente_id=CLIENTE,
            canal="whatsapp",
            finalidade="promocoes",
            status="concedido",
            base_legal="consentimento",
            texto_versao="marketing-v1",
            origem="self_service",
            prova_hash="b" * 64,
            ocorrido_em=AGORA - timedelta(days=2),
            idempotency_key="consent-1",
            correlation_id="corr:consent-1",
            concedido_em=AGORA - timedelta(days=2),
            revogado_em=None,
        )
    )
    session.execute(
        insert(crm_consentimentos_v1).values(
            consentimento_id="cons-2",
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            cliente_id=CLIENTE,
            canal="whatsapp",
            finalidade="promocoes",
            status="revogado",
            base_legal="consentimento",
            texto_versao="marketing-v1",
            origem="self_service",
            prova_hash="c" * 64,
            ocorrido_em=AGORA - timedelta(days=1),
            idempotency_key="consent-2",
            correlation_id="corr:consent-2",
            concedido_em=None,
            revogado_em=AGORA - timedelta(days=1),
        )
    )


def test_0034_customer_context_esta_no_manifest_e_cria_vault() -> None:
    assert DEFAULT_MIGRATIONS[-1].version == "0034_crm_customer_context_v1"
    assert_migration_manifest(DEFAULT_MIGRATIONS)
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    aplicadas = run_migrations(engine)
    assert aplicadas[-1] == "0034_crm_customer_context_v1"
    assert "crm_enderecos_seguros_v1" in set(inspect(engine).get_table_names())


def test_contexto_combina_historico_consentimento_e_endereco_sem_vazar_escopo() -> None:
    engine, factory = _factory()
    chave = Fernet.generate_key().decode("ascii")
    with factory() as session:
        _seed_cliente(session)
        _seed_pedido(session)
        _seed_consentimento(session)
        endereco_ref = EncryptedSQLAlchemyAddressStore(
            session,
            master_key=chave,
        ).armazenar_validado(
            contexto=_contexto(),
            cliente_id=CLIENTE,
            endereco_formatado="Rua A, 10 - Centro, Cidade - SP, 01000-000",
            cep="01000-000",
            place_id="place-1",
            latitude=Decimal("-23.5"),
            longitude=Decimal("-46.6"),
            agora=AGORA,
        )
        session.commit()

    with factory() as session:
        contexto = ContextoClienteAtendimentoSQLAlchemy(
            session,
            master_key=chave,
        ).resolver(
            contexto=_contexto(),
            cliente_ref=CLIENTE,
        )

        assert contexto.cliente_ref == CLIENTE
        assert contexto.ultimo_endereco_ref == endereco_ref
        assert len(contexto.historico) == 1
        assert contexto.historico[0].pedido_id == "pedido-historico-1"
        assert contexto.historico[0].itens[0].produto_id == "101"
        assert len(contexto.consentimentos) == 1
        assert contexto.consentimentos[0].status == "revogado"

        with pytest.raises(LookupError, match="cliente_contexto_indisponivel"):
            ContextoClienteAtendimentoSQLAlchemy(
                session,
                master_key=chave,
            ).resolver(
                contexto=_contexto(tenant="tenant-b", unidade="unidade-b"),
                cliente_ref=CLIENTE,
            )

    with Session(engine) as session:
        row = session.execute(select(crm_enderecos_seguros_v1)).mappings().one()
        serializado = repr(dict(row))
        assert "Rua A" not in serializado
        assert "01000-000" not in serializado


def test_o_de_sempre_reusa_ids_historicos_mas_nome_atual_do_catalogo() -> None:
    _engine, factory = _factory()
    chave = Fernet.generate_key().decode("ascii")
    with factory() as session:
        _seed_cliente(session)
        _seed_pedido(session)
        session.commit()
    with factory() as session:
        contexto = ContextoClienteAtendimentoSQLAlchemy(
            session,
            master_key=chave,
        ).resolver(
            contexto=_contexto(),
            cliente_ref=CLIENTE,
        )

    catalogo = (
        ProdutoCatalogoAtendimento(
            produto_id="101",
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            nome="X-Bacon Atual",
            preco=Decimal("29.90"),
            ativo=True,
        ),
    )
    raw = _raw_historico_autorizado(
        mensagem="Quero o de sempre",
        contexto_cliente=contexto,
        catalogo=catalogo,
    )
    assert raw is not None
    payload = json.loads(raw)
    assert payload["itens"] == [
        {
            "nome_produto": "X-Bacon Atual",
            "quantidade": 2,
        }
    ]
    assert payload["modalidade"] == "indefinida"
    assert payload["endereco_texto"] is None


def test_endereco_salvo_exige_mesmo_cliente_tenant_e_unidade() -> None:
    _engine, factory = _factory()
    chave = Fernet.generate_key().decode("ascii")
    with factory() as session:
        _seed_cliente(session)
        store = EncryptedSQLAlchemyAddressStore(session, master_key=chave)
        referencia = store.armazenar_validado(
            contexto=_contexto(),
            cliente_id=CLIENTE,
            endereco_formatado="Rua A, 10 - Centro, Cidade - SP, 01000-000",
            cep="01000-000",
            place_id="place-1",
            latitude=Decimal("-23.5"),
            longitude=Decimal("-46.6"),
            agora=AGORA,
        )
        session.commit()

    with factory() as session:
        store = EncryptedSQLAlchemyAddressStore(session, master_key=chave)
        endereco = store.resolver(
            contexto=_contexto(),
            cliente_id=CLIENTE,
            referencia=referencia,
        )
        assert endereco.cep == "01000000"
        assert endereco.place_id == "place-1"
        with pytest.raises(LookupError, match="endereco_salvo_indisponivel"):
            store.resolver(
                contexto=_contexto(tenant="tenant-b", unidade="unidade-b"),
                cliente_id=CLIENTE,
                referencia=referencia,
            )


def test_handoff_persistido_recupera_so_contexto_allowlisted_no_mesmo_escopo() -> None:
    _engine, factory = _factory()
    handoff = HandoffAssistenteAuditSQLAlchemy(factory)
    contexto = _contexto()

    handoff.registrar(
        contexto=contexto,
        conversa_id="conv-handoff-1",
        motivo="produto_nao_resolvido_exatamente",
        metadata_segura={
            "cliente_ref": CLIENTE,
            "cliente_tipo": "conhecido",
            "historico_count": 2,
            "itens_solicitados": 1,
            "itens_resolvidos": 0,
            "telefone": "+5511999999999",
            "endereco_texto": "Rua secreta, 10",
        },
    )

    recuperado = handoff.ultimo_contexto(
        contexto=contexto,
        conversa_id="conv-handoff-1",
    )
    assert recuperado is not None
    assert recuperado["cliente_ref"] == CLIENTE
    assert recuperado["historico_count"] == 2
    assert recuperado["itens_solicitados"] == 1
    assert "telefone" not in recuperado
    assert "endereco_texto" not in recuperado
    assert "+5511999999999" not in repr(recuperado)
    assert "Rua secreta" not in repr(recuperado)

    assert (
        handoff.ultimo_contexto(
            contexto=_contexto(tenant="tenant-b", unidade="unidade-b"),
            conversa_id="conv-handoff-1",
        )
        is None
    )
