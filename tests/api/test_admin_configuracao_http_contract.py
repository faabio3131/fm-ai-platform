from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from application.administracao_proprietario import AplicacaoAdministracaoProprietarioV1
from core.administracao import ConfiguracaoEstabelecimento
from core.runtime.config import RuntimeEnvironment, RuntimeSettings
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Papel
from http_api.frontend_app import build_frontend_http_app
from infra.administracao.repositorio_sqlalchemy import (
    RepositorioAdministracaoSQLAlchemy,
)
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy
from migrations.runner import run_migrations

SESSION_SECRET = "admin-config-session-secret-0123456789"
SENHA = "Senha-Segura-Config-123"
TENANT = "tenant-config-http"
UNIDADE_A = "unidade-config-a"
UNIDADE_B = "unidade-config-b"
ADMIN_EMAIL = "admin-config@example.com"


def _infra(monkeypatch) -> tuple[TestClient, sessionmaker]:
    monkeypatch.setenv("FM_AI_SESSION_SECRET", SESSION_SECRET)
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    run_migrations(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        repo_identidades = RepositorioIdentidadesSQLAlchemy(session)
        repo_identidades.criar_usuario(
            usuario_id="admin-config-user",
            email=ADMIN_EMAIL,
            password=SENHA,
            tenant_id=TENANT,
            unidade_padrao_id=UNIDADE_A,
            papeis=(Papel.ADMINISTRADOR,),
            unidades_permitidas=(UNIDADE_A, UNIDADE_B),
            acesso_admin_sensivel=True,
        )
        repo_admin = RepositorioAdministracaoSQLAlchemy(session)
        repo_admin.garantir_escopo(
            tenant_id=TENANT,
            unidade_id=UNIDADE_A,
            nome_empresa="Empresa Config",
            nome_unidade="Matriz Config",
        )
        repo_admin.garantir_escopo(
            tenant_id=TENANT,
            unidade_id=UNIDADE_B,
            nome_empresa="Empresa Config",
            nome_unidade="Filial Config",
        )
        session.commit()
    app = build_frontend_http_app(
        settings=RuntimeSettings(
            environment=RuntimeEnvironment.TEST,
            database_url="sqlite://",
            tenant_id=TENANT,
            unidade_id=UNIDADE_A,
        ),
        engine=engine,
        session_factory=factory,
    )
    return TestClient(app), factory


def _login(client: TestClient, *, elevar: bool = True) -> None:
    response = client.post("/v1/auth/login", json={"email": ADMIN_EMAIL, "senha": SENHA})
    assert response.status_code == 200
    if elevar:
        response = client.post("/v1/auth/admin-step-up", json={"senha": SENHA})
        assert response.status_code == 200


def _contexto_admin(factory) -> ContextoExecucao:
    with factory() as session:
        repo = RepositorioIdentidadesSQLAlchemy(session)
        identidade = repo.obter_por_email(ADMIN_EMAIL)
        assert identidade is not None
        return identidade.contexto(origem="test.setup")


def _configuracao_padrao(versao: int) -> ConfiguracaoEstabelecimento:
    return ConfiguracaoEstabelecimento(
        tenant_id=TENANT,
        unidade_id=UNIDADE_A,
        formas_pagamento=("dinheiro", "pix"),
        taxa_servico_percentual=Decimal(5),
        parametros_operacionais={},
        politica_financeira={},
        versao=versao,
    )


def _configuracao_completa(versao: int) -> ConfiguracaoEstabelecimento:
    return ConfiguracaoEstabelecimento(
        tenant_id=TENANT,
        unidade_id=UNIDADE_A,
        formas_pagamento=("pix", "dinheiro", "cartao_credito"),
        taxa_servico_percentual=Decimal(10),
        parametros_operacionais={"aceita_pagamento_na_entrega": True},
        politica_financeira={"taxa_embalagem": "3.00"},
        versao=versao,
    )


def _payload_configuracao_completa(versao: int) -> dict:
    return {
        "formas_pagamento": ["pix", "dinheiro", "cartao_credito"],
        "taxa_servico_percentual": "10.0",
        "parametros_operacionais": {"aceita_pagamento_na_entrega": True},
        "politica_financeira": {"taxa_embalagem": "3.00"},
        "versao": versao,
    }


def test_configuracao_exige_sessao_e_stepup(monkeypatch) -> None:
    client, _ = _infra(monkeypatch)

    sem_sessao = client.get(f"/v1/admin/configuracao/{UNIDADE_A}")
    assert sem_sessao.status_code == 401

    _login(client, elevar=False)

    sem_stepup = client.get(f"/v1/admin/configuracao/{UNIDADE_A}")
    assert sem_stepup.status_code == 403
    assert sem_stepup.json() == {"erro": "seguranca.admin_step_up_exigido"}


def test_consultar_configuracao_retorna_padrao_apos_garantir_escopo(monkeypatch) -> None:
    client, _ = _infra(monkeypatch)
    _login(client)

    response = client.get(f"/v1/admin/configuracao/{UNIDADE_A}")
    assert response.status_code == 200
    data = response.json()
    assert data["tenant_id"] == TENANT
    assert data["unidade_id"] == UNIDADE_A
    assert data["formas_pagamento"] == []
    assert data["taxa_servico_percentual"] == "0"
    assert data["parametros_operacionais"] == {}
    assert data["politica_financeira"] == {}
    assert data["versao"] == 1


def test_consultar_e_atualizar_configuracao(monkeypatch) -> None:
    client, factory = _infra(monkeypatch)
    _login(client)

    app = AplicacaoAdministracaoProprietarioV1(factory)
    contexto = _contexto_admin(factory)

    # Get default config (created by garantir_escopo)
    config = app.obter_configuracao(contexto=contexto, unidade_id=UNIDADE_A)
    assert config.versao == 1

    # Update to a known state
    app.salvar_configuracao(contexto=contexto, configuracao=_configuracao_padrao(config.versao), versao_esperada=config.versao)

    get_resp = client.get(f"/v1/admin/configuracao/{UNIDADE_A}")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["tenant_id"] == TENANT
    assert data["unidade_id"] == UNIDADE_A
    assert set(data["formas_pagamento"]) == {"dinheiro", "pix"}
    assert data["taxa_servico_percentual"] == "5"
    assert data["versao"] == 2

    # Update via HTTP
    put_resp = client.put(
        f"/v1/admin/configuracao/{UNIDADE_A}",
        json=_payload_configuracao_completa(versao=2),
    )
    assert put_resp.status_code == 200
    updated = put_resp.json()
    assert updated["versao"] == 3
    assert set(updated["formas_pagamento"]) == {"pix", "dinheiro", "cartao_credito"}
    assert updated["taxa_servico_percentual"] == "10"
    assert updated["parametros_operacionais"]["aceita_pagamento_na_entrega"] is True
    assert updated["politica_financeira"]["taxa_embalagem"] == "3.00"

    get_resp2 = client.get(f"/v1/admin/configuracao/{UNIDADE_A}")
    assert get_resp2.status_code == 200
    assert get_resp2.json()["versao"] == 3


def test_atualizar_configuracao_concorrencia_falha(monkeypatch) -> None:
    client, factory = _infra(monkeypatch)
    _login(client)

    app = AplicacaoAdministracaoProprietarioV1(factory)
    contexto = _contexto_admin(factory)

    config = app.obter_configuracao(contexto=contexto, unidade_id=UNIDADE_A)
    app.salvar_configuracao(contexto=contexto, configuracao=_configuracao_padrao(config.versao), versao_esperada=config.versao)

    # First update succeeds
    client.put(f"/v1/admin/configuracao/{UNIDADE_A}", json=_payload_configuracao_completa(versao=2))

    # Second update with same version fails
    conflito = client.put(f"/v1/admin/configuracao/{UNIDADE_A}", json=_payload_configuracao_completa(versao=2))
    assert conflito.status_code == 409
    assert "concorrente" in conflito.json()["erro"].casefold()


def test_atualizar_configuracao_rejeita_forma_pagamento_invalida(monkeypatch) -> None:
    client, factory = _infra(monkeypatch)
    _login(client)

    app = AplicacaoAdministracaoProprietarioV1(factory)
    contexto = _contexto_admin(factory)

    config = app.obter_configuracao(contexto=contexto, unidade_id=UNIDADE_A)
    app.salvar_configuracao(contexto=contexto, configuracao=_configuracao_padrao(config.versao), versao_esperada=config.versao)

    payload = _payload_configuracao_completa(versao=2)
    payload["formas_pagamento"] = ["pix", "forma_inexistente"]

    response = client.put(f"/v1/admin/configuracao/{UNIDADE_A}", json=payload)
    assert response.status_code == 400
    assert "forma_pagamento_invalida" in response.json()["erro"]


def test_atualizar_configuracao_rejeita_taxa_servico_fora_limite(monkeypatch) -> None:
    client, factory = _infra(monkeypatch)
    _login(client)

    app = AplicacaoAdministracaoProprietarioV1(factory)
    contexto = _contexto_admin(factory)

    config = app.obter_configuracao(contexto=contexto, unidade_id=UNIDADE_A)
    app.salvar_configuracao(contexto=contexto, configuracao=_configuracao_padrao(config.versao), versao_esperada=config.versao)

    payload = _payload_configuracao_completa(versao=2)
    payload["taxa_servico_percentual"] = "150"

    response = client.put(f"/v1/admin/configuracao/{UNIDADE_A}", json=payload)
    # Pydantic validation rejects before router logic (le=100)
    assert response.status_code == 422


def test_atualizar_configuracao_rejeita_chaves_secretas(monkeypatch) -> None:
    client, factory = _infra(monkeypatch)
    _login(client)

    app = AplicacaoAdministracaoProprietarioV1(factory)
    contexto = _contexto_admin(factory)

    config = app.obter_configuracao(contexto=contexto, unidade_id=UNIDADE_A)
    app.salvar_configuracao(contexto=contexto, configuracao=_configuracao_padrao(config.versao), versao_esperada=config.versao)

    payload = _payload_configuracao_completa(versao=2)
    payload["parametros_operacionais"]["api_key"] = "segredo"

    response = client.put(f"/v1/admin/configuracao/{UNIDADE_A}", json=payload)
    assert response.status_code == 400
    assert "chave_secreta_proibida" in response.json()["erro"]


def test_consultar_configuracao_outra_unidade_mesmo_tenant(monkeypatch) -> None:
    client, factory = _infra(monkeypatch)
    _login(client)

    app = AplicacaoAdministracaoProprietarioV1(factory)
    contexto = _contexto_admin(factory)

    config = app.obter_configuracao(contexto=contexto, unidade_id=UNIDADE_B)
    app.salvar_configuracao(
        contexto=contexto,
        configuracao=ConfiguracaoEstabelecimento(
            tenant_id=TENANT,
            unidade_id=UNIDADE_B,
            formas_pagamento=("pix",),
            taxa_servico_percentual=Decimal(0),
            parametros_operacionais={},
            politica_financeira={},
            versao=config.versao,
        ),
        versao_esperada=config.versao,
    )

    response = client.get(f"/v1/admin/configuracao/{UNIDADE_B}")
    assert response.status_code == 200
    assert response.json()["unidade_id"] == UNIDADE_B


def test_consultar_configuracao_unidade_inexistente_retorna_403(monkeypatch) -> None:
    client, _ = _infra(monkeypatch)
    _login(client)

    response = client.get("/v1/admin/configuracao/unidade-inexistente")
    # Unidade fora do escopo administrativo retorna 403 (não vaza existência)
    assert response.status_code == 403
    assert "unidade_fora_do_escopo" in response.json()["erro"]