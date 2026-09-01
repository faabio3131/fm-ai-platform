from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from application.administracao_proprietario import (
    AplicacaoAdministracaoProprietarioV1,
)
from core.administracao import (
    ConfiguracaoEstabelecimento,
    UnidadeAdministrativa,
)
from core.entrega.modelos_orm import EntregaORM
from core.estoque.modelos_orm import SaldoEstoqueORM
from core.pagamentos.modelos_orm import (
    ObrigacaoPagamentoORM,
    PagamentoORM,
    VendaFinanceiraORM,
)
from core.pedidos.modelos_orm import PedidoORM
from core.seguranca.permissoes import Papel
from infra.administracao.repositorio_sqlalchemy import (
    RepositorioAdministracaoSQLAlchemy,
)
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy
from infra.seguranca.modelos_orm import EventoAuditoriaORM
from migrations.runner import run_migrations

AGORA = datetime(2026, 9, 1, 3, 0, tzinfo=timezone.utc)


def _engine() -> Engine:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, _record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    run_migrations(engine)
    return engine


def _bootstrap_admin(factory):
    with factory() as session:
        identidade = RepositorioIdentidadesSQLAlchemy(session).criar_usuario(
            email="owner-f5@example.test",
            password="senha-owner-fase5-segura",
            admin_pin="472839",
            tenant_id="tenant-f5",
            unidade_padrao_id="matriz-f5",
            papeis=(Papel.ADMINISTRADOR,),
            unidades_permitidas=("matriz-f5",),
            acesso_admin_sensivel=True,
        )
        session.commit()
    return identidade


def test_acesso_materializa_escopo_e_audita_sem_env_ou_segredos() -> None:
    engine = _engine()
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    identidade = _bootstrap_admin(factory)
    app = AplicacaoAdministracaoProprietarioV1(factory)
    contexto = identidade.contexto(origem="tests.f5.acesso", solicitado_em=AGORA)

    app.registrar_acesso(contexto=contexto)
    empresa = app.obter_empresa(contexto=contexto)
    unidades = app.listar_unidades(contexto=contexto)
    config = app.obter_configuracao(contexto=contexto, unidade_id="matriz-f5")

    assert empresa.tenant_id == "tenant-f5"
    assert [item.unidade_id for item in unidades] == ["matriz-f5"]
    assert config.formas_pagamento == ()

    with Session(engine) as session:
        eventos = session.scalars(
            select(EventoAuditoriaORM).where(
                EventoAuditoriaORM.tenant_id == "tenant-f5",
                EventoAuditoriaORM.acao == "administracao.acessar",
            )
        ).all()
        assert len(eventos) == 1
        assert "pin" not in str(eventos[0].metadata_segura).casefold()
        assert "token" not in str(eventos[0].metadata_segura).casefold()


def test_crud_unidade_configuracao_concorrencia_e_isolamento_de_gerente() -> None:
    engine = _engine()
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    owner = _bootstrap_admin(factory)
    app = AplicacaoAdministracaoProprietarioV1(factory)
    owner_ctx = owner.contexto(origem="tests.f5.owner", solicitado_em=AGORA)
    app.registrar_acesso(contexto=owner_ctx)

    filial = app.criar_unidade(
        contexto=owner_ctx,
        unidade=UnidadeAdministrativa(
            tenant_id="tenant-f5",
            unidade_id="filial-f5",
            codigo="FILIAL",
            nome_fantasia="Filial F5",
            tipo="filial",
        ),
    )
    atualizada = app.atualizar_unidade(
        contexto=owner_ctx,
        unidade=UnidadeAdministrativa(
            tenant_id=filial.tenant_id,
            unidade_id=filial.unidade_id,
            codigo=filial.codigo,
            nome_fantasia="Filial F5 Atualizada",
            tipo="filial",
            ativa=True,
            versao=filial.versao,
        ),
        versao_esperada=filial.versao,
    )
    assert atualizada.versao == 2

    with pytest.raises(RuntimeError, match="unidade_admin_concorrente"):
        app.atualizar_unidade(
            contexto=owner_ctx,
            unidade=filial,
            versao_esperada=1,
        )

    config = app.obter_configuracao(
        contexto=owner_ctx,
        unidade_id="filial-f5",
    )
    salva = app.salvar_configuracao(
        contexto=owner_ctx,
        configuracao=ConfiguracaoEstabelecimento(
            tenant_id="tenant-f5",
            unidade_id="filial-f5",
            formas_pagamento=("pix", "dinheiro"),
            taxa_servico_percentual=Decimal("8"),
            parametros_operacionais={"aceita_pagamento_na_entrega": True},
            politica_financeira={"taxa_embalagem": "3.00"},
            versao=config.versao,
        ),
        versao_esperada=config.versao,
    )
    assert salva.formas_pagamento == ("pix", "dinheiro")

    with factory() as session:
        manager = RepositorioIdentidadesSQLAlchemy(session).criar_usuario(
            email="manager-f5@example.test",
            password="senha-manager-fase5-segura",
            admin_pin="583927",
            tenant_id="tenant-f5",
            unidade_padrao_id="matriz-f5",
            papeis=(Papel.GERENTE,),
            unidades_permitidas=("matriz-f5",),
            acesso_admin_sensivel=True,
        )
        session.commit()

    manager_ctx = manager.contexto(origem="tests.f5.manager", solicitado_em=AGORA)
    assert [u.unidade_id for u in app.listar_unidades(contexto=manager_ctx)] == [
        "matriz-f5"
    ]
    with pytest.raises(PermissionError, match="unidade_fora_do_escopo"):
        app.obter_configuracao(
            contexto=manager_ctx,
            unidade_id="filial-f5",
        )


def test_usuarios_reusam_rbac_canonico_e_nao_podem_receber_unidade_de_outro_tenant() -> None:
    engine = _engine()
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    owner = _bootstrap_admin(factory)
    app = AplicacaoAdministracaoProprietarioV1(factory)
    ctx = owner.contexto(origem="tests.f5.users", solicitado_em=AGORA)
    app.registrar_acesso(contexto=ctx)

    with factory() as session:
        RepositorioAdministracaoSQLAlchemy(session).garantir_escopo(
            tenant_id="tenant-outro",
            unidade_id="loja-outro",
        )
        session.commit()

    caixa = app.criar_usuario(
        contexto=ctx,
        email="caixa-f5@example.test",
        password="senha-caixa-fase5-segura",
        unidade_padrao_id="matriz-f5",
        papeis=(Papel.CAIXA,),
        unidades_permitidas=("matriz-f5",),
    )
    assert caixa.tenant_id == "tenant-f5"
    assert Papel.CAIXA in caixa.papeis

    with pytest.raises(PermissionError, match="usuario_unidades_fora_do_tenant"):
        app.criar_usuario(
            contexto=ctx,
            email="invasor-f5@example.test",
            password="senha-invasor-fase5-segura",
            unidade_padrao_id="loja-outro",
            papeis=(Papel.CAIXA,),
            unidades_permitidas=("loja-outro",),
        )

    with pytest.raises(ValueError, match="desativar_a_si_mesmo"):
        app.atualizar_usuario(
            contexto=ctx,
            usuario_id=owner.usuario_id,
            papeis=(Papel.ADMINISTRADOR,),
            unidades_permitidas=("matriz-f5",),
            unidade_padrao_id="matriz-f5",
            ativo=False,
            acesso_admin_sensivel=True,
        )


def test_dashboard_consolida_apenas_fontes_canonicas_do_tenant() -> None:
    engine = _engine()
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    owner = _bootstrap_admin(factory)
    app = AplicacaoAdministracaoProprietarioV1(factory)
    ctx = owner.contexto(origem="tests.f5.dashboard", solicitado_em=AGORA)
    app.registrar_acesso(contexto=ctx)

    with factory() as session:
        session.add(
            PedidoORM(
                id="pedido-f5",
                tenant_id="tenant-f5",
                unidade_id="matriz-f5",
                origem="pdv",
                canal="pdv",
                status="confirmado",
                cliente_id=None,
                criado_em=AGORA,
                atualizado_em=AGORA,
                versao=1,
                correlation_id="corr-f5",
                idempotency_key="pedido-f5",
                request_hash="hash-pedido-f5",
                subtotal=Decimal("50"),
                descontos=Decimal("0"),
                taxas=Decimal("0"),
                total=Decimal("50"),
            )
        )
        session.add(
            ObrigacaoPagamentoORM(
                id="pagamento-f5",
                tenant_id="tenant-f5",
                unidade_id="matriz-f5",
                pedido_id="pedido-f5",
                comanda_id=None,
                valor_previsto=Decimal("50"),
                moeda="BRL",
                criado_em=AGORA,
                versao=1,
                correlation_id="corr-f5",
                idempotency_key="obrigacao-f5",
                request_hash="hash-obrigacao-f5",
            )
        )
        session.flush()
        session.add(
            PagamentoORM(
                id="pagamento-f5",
                tenant_id="tenant-f5",
                unidade_id="matriz-f5",
                pedido_id="pedido-f5",
                comanda_id=None,
                status="pago",
                metodo="dinheiro",
                valor_previsto=Decimal("50"),
                valor_pago=Decimal("50"),
                valor_estornado=Decimal("0"),
                saldo=Decimal("0"),
                moeda="BRL",
                recebimento_posterior=False,
                provedor=None,
                criado_em=AGORA,
                atualizado_em=AGORA,
                versao=1,
                correlation_id="corr-f5",
                idempotency_key="pagamento-f5",
                request_hash="hash-pagamento-f5",
            )
        )
        session.add(
            VendaFinanceiraORM(
                id="venda-f5",
                tenant_id="tenant-f5",
                unidade_id="matriz-f5",
                pedido_id="pedido-f5",
                pagamento_id="pagamento-f5",
                comanda_id=None,
                criterio_codigo="pagamento_liquidado",
                criterio_versao=1,
                valor=Decimal("50"),
                moeda="BRL",
                metodo="dinheiro",
                reconhecida_em=AGORA,
                correlation_id="corr-f5",
                idempotency_key="venda-f5",
                request_hash="hash-venda-f5",
            )
        )
        session.add(
            SaldoEstoqueORM(
                tenant_id="tenant-f5",
                unidade_id="matriz-f5",
                insumo_id="insumo-f5",
                saldo_fisico=Decimal("20"),
                saldo_reservado=Decimal("3"),
                versao=1,
            )
        )
        session.add(
            EntregaORM(
                id="entrega-f5",
                tenant_id="tenant-f5",
                unidade_id="matriz-f5",
                pedido_id="pedido-f5",
                endereco_id="address://f5",
                modalidade="propria",
                status="aguardando_producao",
                versao=1,
                tentativa=1,
                entregador_id=None,
                producao_pronta_em=None,
                checklist_concluido_em=None,
                atribuida_em=None,
                coletada_em=None,
                saiu_em=None,
                entregue_em=None,
                prova_entrega_ref=None,
                atualizado_em=AGORA,
            )
        )
        session.commit()

    painel = app.painel_executivo(
        contexto=ctx,
        unidades=("matriz-f5",),
    )
    assert painel.financeiro.vendas_reconhecidas == Decimal("50")
    assert painel.financeiro.quantidade_vendas == 1
    assert painel.financeiro.ticket_medio == Decimal("50")
    assert painel.financeiro.pagamentos_pagos == Decimal("50")
    assert painel.financeiro.recebido_dinheiro == Decimal("50")
    assert painel.operacional.pedidos == 1
    assert painel.operacional.estoque_fisico_total == Decimal("20")
    assert painel.operacional.estoque_reservado_total == Decimal("3")
    assert painel.operacional.entregas_por_status == (("aguardando_producao", 1),)
