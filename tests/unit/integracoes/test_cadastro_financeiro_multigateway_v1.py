"""Cadastro financeiro não é autorização de movimentação.

Provedores novos guardam referências no Vault, sem liberar transações
inexistentes, mantendo as operações já certificadas para PagBank/MP.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from core.integracoes import (
    AmbienteIntegracao,
    ErroConfiguracaoServico,
    ServicoConfiguracoesExternas,
)
from core.integracoes.catalogo import CATALOGO_V1, EscopoGestaoIntegracao
from core.seguranca.auditoria import RepositorioAuditoriaEmMemoria
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Papel, Permissao
from core.seguranca.segredos import ReferenceSecretStore
from infra.integracoes.modelos_orm import IntegrationConfigBase
from infra.integracoes.repositorio_sqlalchemy import (
    ProntidaoCredenciaisSQLAlchemy,
    RepositorioConfiguracoesExternasSQLAlchemy,
)
from infra.seguranca.modelos_orm import SecurityBase


@pytest.mark.parametrize(
    ("servico", "provedor", "roles"),
    [
        ("pagamentos.pix", "asaas", {"api_key"}),
        ("pagamentos.pix", "picpay", {"client_id", "client_secret"}),
        ("pagamentos.pix", "pagarme", {"api_key"}),
        ("pagamentos.pix", "efi", {"client_id", "client_secret"}),
        ("pagamentos.cartao", "mercado_pago", {"access_token"}),
        ("pagamentos.cartao", "picpay", {"client_id", "client_secret"}),
        ("pagamentos.cartao", "stone", {"api_key"}),
        ("pagamentos.cartao", "cielo", {"merchant_id", "merchant_key"}),
        ("pagamentos.cartao", "rede", {"pv", "integration_key"}),
        ("pagamentos.cartao", "getnet", {"client_id", "client_secret"}),
        ("pagamentos.cartao", "sumup", {"access_token"}),
        ("financeiro.conta_bancaria", "nubank", {"agencia", "numero_conta"}),
        ("financeiro.conta_bancaria", "itau", {"agencia", "numero_conta"}),
        ("financeiro.conta_bancaria", "sicoob", {"agencia", "numero_conta"}),
        ("financeiro.conta_bancaria", "banco_do_brasil", {"agencia", "numero_conta"}),
    ],
)
def test_novos_provedores_apenas_cadastraveis(servico, provedor, roles):
    spec = CATALOGO_V1.obter(servico, provedor)
    assert spec.escopo_gestao is EscopoGestaoIntegracao.TENANT_MANAGED
    assert spec.credenciais_obrigatorias == roles
    assert spec.runtime_operacional is False
    if servico == "financeiro.conta_bancaria":
        assert spec.credenciais_opcionais == {"chave_pix", "digito_conta"}
        assert "numero_conta" not in spec.parametros_obrigatorios


def test_mercado_pago_e_pagbank_pix_conservam_runtime_existente():
    assert CATALOGO_V1.obter("pagamentos.pix", "mercado_pago").runtime_operacional
    assert CATALOGO_V1.obter("pagamentos.pix", "pagbank").runtime_operacional


def test_sem_adapter_operacional_nao_e_possivel_homologar_cadastro_bancario():
    engine = create_engine("sqlite:///:memory:")
    IntegrationConfigBase.metadata.create_all(engine)
    SecurityBase.metadata.create_all(engine)
    contexto = ContextoExecucao(
        tenant_id="tenant-fi",
        unidade_id="unidade-fi",
        usuario_id="owner-fi",
        papeis=frozenset({Papel.ADMINISTRADOR}),
        permissoes=frozenset(Permissao),
        correlation_id="corr-fi",
        solicitado_em=datetime.now(timezone.utc),
        origem="testes",
        unidades_permitidas=frozenset({"unidade-fi"}),
    )
    with Session(engine) as session:
        store = ReferenceSecretStore()
        service = ServicoConfiguracoesExternas(
            repositorio=RepositorioConfiguracoesExternasSQLAlchemy(session),
            prontidao_credenciais=ProntidaoCredenciaisSQLAlchemy(session, store),
            auditoria=RepositorioAuditoriaEmMemoria(),
        )
        config = service.configurar(
            contexto=contexto,
            configuracao_id="financeiro.conta_bancaria--inter",
            servico="financeiro.conta_bancaria",
            provedor="inter",
            conta_externa="recebimentos",
            ambiente=AmbienteIntegracao.PRODUCAO,
            parametros_publicos={"tipo_conta": "corrente"},
            finalidades_credenciais={},
            habilitada=True,
            versao_esperada=0,
        )
        assert config.homologada is False
        with pytest.raises(
            ErroConfiguracaoServico,
            match="homologacao_indisponivel_sem_adapter_transacional",
        ):
            service.registrar_homologacao(
                contexto=contexto,
                configuracao_id=config.configuracao_id,
                evidencia_ref="manual://operacao-nao-validada",
                versao_esperada=config.versao,
            )
