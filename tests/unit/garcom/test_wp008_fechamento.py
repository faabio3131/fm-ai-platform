from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from application.garcom_fechamento import (
    AplicacaoFechamentoGarcomV1,
    DestinoRecebimento,
    ModoRecebimentoGarcom,
)
from core.salao import ErroSalao
from core.salao.modelos_orm import ComandaORM, MesaORM, SalaoBase
from core.seguranca import MATRIZ_PADRAO, ContextoExecucao, Papel
from infra.administracao.modelos_orm import (
    AdminBase,
    ConfiguracaoEstabelecimentoORM,
    EmpresaAdminORM,
    UnidadeAdminORM,
)

AGORA = datetime(2026, 9, 18, 3, 0, tzinfo=UTC)
TENANT = "tenant-wp008"
UNIDADE = "unidade-wp008"
OUTRA = "unidade-wp008-b"


def _contexto(
    papel: Papel,
    *,
    unidade_id: str = UNIDADE,
    usuario_id: str | None = None,
) -> ContextoExecucao:
    return ContextoExecucao(
        TENANT,
        unidade_id,
        usuario_id or f"ator-{papel.value}",
        frozenset({papel}),
        MATRIZ_PADRAO[papel],
        f"corr-{papel.value}",
        AGORA,
        "tests.wp008",
        unidades_permitidas=frozenset({UNIDADE, OUTRA}),
    )


def _infra():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    AdminBase.metadata.create_all(engine)
    SalaoBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    with factory() as session:
        session.add(
            EmpresaAdminORM(
                tenant_id=TENANT,
                nome_exibicao="WP008",
                moeda="BRL",
                timezone="America/Sao_Paulo",
                ativa=True,
                versao=1,
                criado_em=AGORA,
                atualizado_em=AGORA,
            )
        )
        for unidade, taxa, params in (
            (
                UNIDADE,
                Decimal("10.00"),
                {
                    "recebimento_garcom": "hibrido",
                    "couvert_artistico": {"ativado": True, "valor": "15.00"},
                },
            ),
            (
                OUTRA,
                Decimal("5.00"),
                {
                    "recebimento_garcom": "no_caixa",
                    "couvert_artistico": {"ativado": False, "valor": "99.00"},
                },
            ),
        ):
            session.add(
                UnidadeAdminORM(
                    tenant_id=TENANT,
                    unidade_id=unidade,
                    codigo=unidade,
                    nome_fantasia=unidade,
                    tipo="unidade",
                    endereco={},
                    horarios={},
                    ativa=True,
                    versao=1,
                    criado_em=AGORA,
                    atualizado_em=AGORA,
                )
            )
            session.add(
                ConfiguracaoEstabelecimentoORM(
                    tenant_id=TENANT,
                    unidade_id=unidade,
                    formas_pagamento=["dinheiro", "cartao_credito"],
                    taxa_servico_percentual=taxa,
                    parametros_operacionais=params,
                    politica_financeira={},
                    versao=1,
                    atualizado_em=AGORA,
                )
            )

        for unidade, suffix in ((UNIDADE, "a"), (OUTRA, "b")):
            session.add(
                MesaORM(
                    id=f"mesa-{suffix}",
                    tenant_id=TENANT,
                    unidade_id=unidade,
                    codigo=suffix.upper(),
                    nome=None,
                    capacidade=4,
                    status="ocupada",
                    ativo=True,
                    versao=1,
                    criado_em=AGORA,
                    atualizado_em=AGORA,
                )
            )
            session.add(
                ComandaORM(
                    id=f"comanda-{suffix}",
                    tenant_id=TENANT,
                    unidade_id=unidade,
                    mesa_id=f"mesa-{suffix}",
                    numero=f"C-{suffix.upper()}",
                    status="conta_solicitada",
                    responsavel_id="garcom-1",
                    aberta_em=AGORA,
                    fechada_em=None,
                    total=Decimal("180.00"),
                    saldo=Decimal("180.00"),
                    recebimento_posterior_autorizado=False,
                    versao=2,
                )
            )
        session.commit()
    return factory


def test_demonstrativo_separa_consumo_couvert_taxa_e_desconto() -> None:
    factory = _infra()
    app = AplicacaoFechamentoGarcomV1(factory, agora=lambda: AGORA)

    demonstrativo = app.demonstrativo(
        _contexto(Papel.GARCOM, usuario_id="garcom-1"),
        comanda_id="comanda-a",
        incluir_taxa_servico=True,
    )

    assert demonstrativo.consumo == Decimal("180.00")
    assert demonstrativo.couvert_artistico == Decimal("15.00")
    assert demonstrativo.taxa_servico_percentual == Decimal("10.00")
    assert demonstrativo.taxa_servico_valor == Decimal("18.00")
    assert demonstrativo.desconto == Decimal("0.00")
    assert demonstrativo.total == Decimal("213.00")
    assert demonstrativo.consolidado is False


def test_recusa_taxa_nao_vira_desconto_e_snapshot_preserva_historico() -> None:
    factory = _infra()
    app = AplicacaoFechamentoGarcomV1(factory, agora=lambda: AGORA)
    garcom = _contexto(Papel.GARCOM, usuario_id="garcom-1")

    consolidado = app.consolidar_componentes(
        garcom,
        comanda_id="comanda-a",
        incluir_taxa_servico=False,
        expected_version=2,
        idempotency_key="wp008-componentes",
    )
    assert consolidado.taxa_servico_valor == Decimal("0.00")
    assert consolidado.desconto == Decimal("0.00")
    assert consolidado.couvert_artistico == Decimal("15.00")
    assert consolidado.total == Decimal("195.00")

    app.salvar_configuracao(
        _contexto(Papel.ADMINISTRADOR),
        modo_recebimento=ModoRecebimentoGarcom.HIBRIDO,
        couvert_ativado=True,
        couvert_valor=Decimal("20.00"),
        expected_version=1,
    )

    historico = app.demonstrativo(
        garcom,
        comanda_id="comanda-a",
        incluir_taxa_servico=True,
    )
    assert historico.consolidado is True
    assert historico.couvert_artistico == Decimal("15.00")
    assert historico.taxa_servico_valor == Decimal("0.00")
    assert historico.total == Decimal("195.00")
    assert historico.configuracao_versao == 1


def test_modo_hibrido_aceita_mesa_e_no_caixa_rejeita_mesa() -> None:
    factory = _infra()
    app = AplicacaoFechamentoGarcomV1(factory, agora=lambda: AGORA)

    destino = app.definir_destino(
        _contexto(Papel.GARCOM, usuario_id="garcom-1"),
        comanda_id="comanda-a",
        destino=DestinoRecebimento.MESA,
        expected_version=2,
        idempotency_key="wp008-destino-a",
    )
    assert destino is DestinoRecebimento.MESA

    with pytest.raises(ErroSalao) as exc_info:
        app.definir_destino(
            _contexto(Papel.GARCOM, unidade_id=OUTRA, usuario_id="garcom-1"),
            comanda_id="comanda-b",
            destino=DestinoRecebimento.MESA,
            expected_version=2,
            idempotency_key="wp008-destino-b",
        )
    assert exc_info.value.codigo == "destino_recebimento_nao_permitido"


def test_isolamento_unidade_e_concorrencia_permanecem_fail_closed() -> None:
    factory = _infra()
    app = AplicacaoFechamentoGarcomV1(factory, agora=lambda: AGORA)

    outra = app.demonstrativo(
        _contexto(Papel.GARCOM, unidade_id=OUTRA, usuario_id="garcom-1"),
        comanda_id="comanda-b",
    )
    assert outra.couvert_artistico == Decimal("0.00")
    assert outra.taxa_servico_percentual == Decimal("5.00")

    with pytest.raises(ErroSalao) as exc_info:
        app.consolidar_componentes(
            _contexto(Papel.GARCOM, usuario_id="garcom-1"),
            comanda_id="comanda-a",
            incluir_taxa_servico=True,
            expected_version=1,
            idempotency_key="wp008-stale",
        )
    assert exc_info.value.codigo == "comanda_concorrente"
