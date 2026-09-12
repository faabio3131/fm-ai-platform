from __future__ import annotations

import pytest

from application.administracao_proprietario import AplicacaoAdministracaoProprietarioV1
from core.seguranca.permissoes import Papel
from infra.administracao.repositorio_sqlalchemy import (
    RepositorioAdministracaoSQLAlchemy,
)
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy
from infra.seguranca.auditoria_sqlalchemy import RepositorioAuditoriaSQLAlchemy
from tests.api.test_admin_backoffice_http_contract import (
    SENHA,
    TENANT,
    UNIDADE_A,
    UNIDADE_B,
    _infra,
    _login,
)


@pytest.fixture
def cadastro(monkeypatch):
    client, factory = _infra(monkeypatch)
    with factory() as session:
        repo = RepositorioAdministracaoSQLAlchemy(session)
        for tenant, uid, nome in (
            (TENANT, UNIDADE_A, "Matriz A"),
            (TENANT, UNIDADE_B, "Filial A"),
            ("tenant-outro", UNIDADE_A, "Empresa B privada"),
            ("tenant-outro", "unidade-externa", "Filial B privada"),
        ):
            repo.garantir_escopo(
                tenant_id=tenant, unidade_id=uid, nome_empresa=nome, nome_unidade=nome
            )
        session.commit()
    return client, factory


def test_sessao_adulterada_falha_fechada(cadastro):
    client, _ = cadastro
    _login(client)
    client.cookies.clear()
    client.cookies.set("fm_ai_session", "sessao.assinatura-adulterada")
    assert client.get("/v1/admin/empresa").status_code == 401


def test_admin_sem_configuracao_nao_consulta_nem_altera(cadastro):
    client, factory = cadastro
    with factory() as session:
        repo = RepositorioIdentidadesSQLAlchemy(session)
        repo.definir_papeis(usuario_id="backoffice-user", papeis=(Papel.COZINHA,))
        repo.definir_acesso_admin_sensivel(usuario_id="backoffice-user", autorizado=True)
        session.commit()
    _login(client)
    assert client.get("/v1/admin/empresa").status_code == 403
    assert client.put("/v1/admin/empresa", json=_empresa()).status_code == 403
    assert client.post("/v1/admin/unidades", json=_nova()).status_code == 403
    assert client.put(f"/v1/admin/unidades/{UNIDADE_A}", json=_unidade()).status_code == 403


def _empresa():
    return {
        "nome_exibicao": "Empresa editada",
        "moeda": "brl",
        "timezone": "America/Sao_Paulo",
        "ativa": True,
        "versao": 1,
    }


def _unidade():
    return {
        "codigo": "CENTRO",
        "nome_fantasia": "Unidade editada",
        "tipo": "matriz",
        "documento_fiscal": "Documento cadastral",
        "telefone": "12345678",
        "email": "loja@example.com",
        "endereco": " Rua Central ",
        "horarios": " 08h às 18h ",
        "ativa": False,
        "versao": 1,
    }


def _nova():
    return {
        "unidade_id": "nova-filial",
        "codigo": "NOVA",
        "nome_fantasia": "Nova filial",
        "tipo": "filial",
        "endereco": " Rua Nova ",
        "horarios": " 10h às 20h ",
    }


@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("GET", "/v1/admin/empresa", None),
        ("PUT", "/v1/admin/empresa", _empresa()),
        ("POST", "/v1/admin/unidades", _nova()),
        ("PUT", f"/v1/admin/unidades/{UNIDADE_A}", _unidade()),
    ],
)
def test_todas_operacoes_exigem_sessao_e_stepup(cadastro, method, path, payload):
    client, _ = cadastro
    assert client.request(method, path, json=payload).status_code == 401
    _login(client, elevar=False)
    sem_elevacao = client.request(method, path, json=payload)
    assert sem_elevacao.status_code == 403
    assert sem_elevacao.json()["erro"] == "seguranca.admin_step_up_exigido"


def test_leitura_preserva_autoridade_tenant_e_sessao_apesar_de_spoofing(cadastro):
    client, factory = cadastro
    _login(client)
    response = client.get(
        "/v1/admin/empresa?tenant_id=tenant-outro&unidade_id=unidade-externa",
        headers={
            "X-Tenant-ID": "tenant-outro",
            "X-Unit-ID": "unidade-externa",
        },
    )
    assert response.status_code == 200
    dados = response.json()
    assert dados["empresa"]["tenant_id"] == TENANT
    assert {u["unidade_id"] for u in dados["unidades"]} == {UNIDADE_A, UNIDADE_B}
    assert "privada" not in response.text
    with factory() as session:
        identidade = RepositorioIdentidadesSQLAlchemy(session).obter_por_id(
            usuario_id="backoffice-user"
        )
    app = AplicacaoAdministracaoProprietarioV1(factory)
    ctx = identidade.contexto(origem="teste.wp022")
    assert (
        dados["empresa"]["nome_exibicao"]
        == app.obter_empresa(contexto=ctx).nome_exibicao
    )
    assert [u["nome_fantasia"] for u in dados["unidades"]] == [
        u.nome_fantasia for u in app.listar_unidades(contexto=ctx)
    ]


def test_edicoes_reusam_validacao_versao_auditoria_e_nao_alteram_outro_tenant(cadastro):
    client, factory = cadastro
    _login(client)
    headers = {
        "X-Tenant-ID": "tenant-outro",
        "X-Unit-ID": UNIDADE_B,
        "X-Correlation-ID": "wp022-edicao",
    }
    empresa = client.put("/v1/admin/empresa", json=_empresa(), headers=headers)
    assert empresa.status_code == 200
    assert empresa.json()["moeda"] == "BRL"
    assert empresa.json()["versao"] == 2
    assert client.put("/v1/admin/empresa", json=_empresa()).status_code == 409
    unidade = client.put(
        f"/v1/admin/unidades/{UNIDADE_A}", json=_unidade(), headers=headers
    )
    assert unidade.status_code == 200
    assert unidade.json()["versao"] == 2
    assert unidade.json()["endereco"] == "Rua Central"
    assert unidade.json()["ativa"] is False
    assert (
        client.put(f"/v1/admin/unidades/{UNIDADE_A}", json=_unidade()).status_code
        == 409
    )
    assert (
        client.put("/v1/admin/unidades/unidade-externa", json=_unidade()).status_code
        == 403
    )
    with factory() as session:
        repo = RepositorioAdministracaoSQLAlchemy(session)
        assert repo.obter_empresa(tenant_id="tenant-outro").versao == 1
        assert (
            repo.obter_unidade(
                tenant_id="tenant-outro", unidade_id=UNIDADE_A
            ).nome_fantasia
            == "Empresa B privada"
        )
        eventos = RepositorioAuditoriaSQLAlchemy(session).listar(
            tenant_id=TENANT, unidade_id=UNIDADE_A, limite=100
        )
    alteracoes = [
        e
        for e in eventos
        if e.acao
        in {"administracao.empresa_atualizar", "administracao.unidade_atualizar"}
    ]
    assert len(alteracoes) == 2
    assert all(
        e.usuario_id == "backoffice-user" and e.correlation_id == "wp022-edicao"
        for e in alteracoes
    )


@pytest.mark.parametrize(
    "method,path,payload,extra",
    [
        ("PUT", "/v1/admin/empresa", _empresa(), {"tenant_id": "tenant-outro"}),
        (
            "PUT",
            f"/v1/admin/unidades/{UNIDADE_A}",
            _unidade(),
            {"unidade_id": UNIDADE_B},
        ),
        ("POST", "/v1/admin/unidades", _nova(), {"tenant_id": "tenant-outro"}),
    ],
)
def test_payload_nao_pode_substituir_escopo(cadastro, method, path, payload, extra):
    client, _ = cadastro
    _login(client)
    assert client.request(method, path, json={**payload, **extra}).status_code == 422


def test_criacao_original_preserva_membership_sem_trocar_unidade_e_recusa_duplicata(
    cadastro,
):
    client, factory = cadastro
    _login(client)
    criada = client.post("/v1/admin/unidades", json=_nova())
    assert criada.status_code == 201
    assert criada.json()["tipo"] == "filial"
    assert criada.json()["ativa"] is True
    assert client.post("/v1/admin/unidades", json=_nova()).status_code == 400
    assert client.get("/v1/auth/me").json()["unidade_ativa_id"] == UNIDADE_A
    with factory() as session:
        identidade = RepositorioIdentidadesSQLAlchemy(session).obter_por_id(
            usuario_id="backoffice-user"
        )
        assert "nova-filial" in identidade.unidades_permitidas
        eventos = RepositorioAuditoriaSQLAlchemy(session).listar(
            tenant_id=TENANT, unidade_id=UNIDADE_A, limite=100
        )
        assert len([e for e in eventos if e.acao == "administracao.unidade_criar"]) == 1
    assert (
        client.post(
            "/v1/auth/select-unit", json={"unidade_id": "nova-filial"}
        ).status_code
        == 200
    )
    assert client.get("/v1/admin/empresa").status_code == 403
    assert (
        client.post("/v1/auth/admin-step-up", json={"senha": SENHA}).status_code == 200
    )
    assert client.get("/v1/admin/empresa").status_code == 200


def test_gerente_padrao_negado_e_gerente_autorizado_limitado_a_sua_unidade(cadastro):
    client, factory = cadastro
    with factory() as session:
        repo = RepositorioIdentidadesSQLAlchemy(session)
        repo.definir_papeis(usuario_id="backoffice-user", papeis=(Papel.GERENTE,))
        repo.definir_unidades(
            usuario_id="backoffice-user",
            unidades_permitidas=(UNIDADE_A,),
            unidade_padrao_id=UNIDADE_A,
        )
        session.commit()
    _login(client, elevar=False)
    assert client.get("/v1/admin/empresa").status_code == 403
    assert (
        client.post("/v1/auth/admin-step-up", json={"senha": SENHA}).status_code == 403
    )
    with factory() as session:
        RepositorioIdentidadesSQLAlchemy(session).definir_acesso_admin_sensivel(
            usuario_id="backoffice-user", autorizado=True
        )
        session.commit()
    assert (
        client.post("/v1/auth/admin-step-up", json={"senha": SENHA}).status_code == 200
    )
    dados = client.get("/v1/admin/empresa").json()
    assert [u["unidade_id"] for u in dados["unidades"]] == [UNIDADE_A]
    assert (
        client.put(f"/v1/admin/unidades/{UNIDADE_A}", json=_unidade()).status_code
        == 200
    )
    assert (
        client.put(f"/v1/admin/unidades/{UNIDADE_B}", json=_unidade()).status_code
        == 403
    )
    assert client.post("/v1/admin/unidades", json=_nova()).status_code == 403
    assert client.put("/v1/admin/empresa", json=_empresa()).status_code == 403
    assert (
        client.post("/v1/auth/select-unit", json={"unidade_id": UNIDADE_B}).status_code
        == 403
    )
