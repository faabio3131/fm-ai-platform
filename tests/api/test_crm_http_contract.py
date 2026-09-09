from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.runtime.config import RuntimeEnvironment, RuntimeSettings
from core.seguranca.permissoes import Papel
from http_api.frontend_app import build_frontend_http_app
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy
from migrations.runner import run_migrations

SESSION_SECRET = "crm-http-session-secret-0123456789-abcdef"
SENHA = "Senha-Segura-CRM-123"
TENANT = "tenant-crm-http"
UNIDADE_A = "unidade-crm-a"
UNIDADE_B = "unidade-crm-b"
ADMIN_EMAIL = "admin-crm@example.com"
COZINHA_EMAIL = "cozinha-crm@example.com"


def _infra(monkeypatch) -> tuple[object, TestClient]:
    monkeypatch.setenv("FM_AI_SESSION_SECRET", SESSION_SECRET)
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    run_migrations(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    with factory() as session:
        repositorio = RepositorioIdentidadesSQLAlchemy(session)
        repositorio.criar_usuario(
            usuario_id="usuario-admin-crm",
            email=ADMIN_EMAIL,
            password=SENHA,
            tenant_id=TENANT,
            unidade_padrao_id=UNIDADE_A,
            papeis=(Papel.ADMINISTRADOR,),
            unidades_permitidas=(UNIDADE_A, UNIDADE_B),
        )
        repositorio.criar_usuario(
            usuario_id="usuario-cozinha-crm",
            email=COZINHA_EMAIL,
            password=SENHA,
            tenant_id=TENANT,
            unidade_padrao_id=UNIDADE_A,
            papeis=(Papel.COZINHA,),
            unidades_permitidas=(UNIDADE_A,),
        )
        session.commit()

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO clientes
                    (id, nome, whatsapp, ultima_compra, total_gasto,
                     saldo_cashback, status)
                VALUES
                    (1, 'Ana Cliente', '5511999000001', '2026-08-20', 120.00, 12.00, 'Ativo'),
                    (2, 'Bia Outra Unidade', '5511999000002', '2026-08-21', 80.00, 7.00, 'Ativo')
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO crm_clientes_v1
                    (tenant_id, unidade_id, cliente_id, origem, criado_em, versao)
                VALUES
                    (:tenant, :unidade_a, 'cliente-a', 'legado_regularizado', '2026-08-01', 1),
                    (:tenant, :unidade_a, 'cliente-sem-legado', 'manual', '2026-08-02', 1),
                    (:tenant, :unidade_b, 'cliente-b', 'legado_regularizado', '2026-08-03', 1)
                """
            ),
            {"tenant": TENANT, "unidade_a": UNIDADE_A, "unidade_b": UNIDADE_B},
        )
        connection.execute(
            text(
                """
                INSERT INTO crm_cliente_contatos_v1
                    (tenant_id, unidade_id, cliente_id, canal, referencia)
                VALUES
                    (:tenant, :unidade_a, 'cliente-a', 'whatsapp', 'contact://cliente-a-whatsapp'),
                    (:tenant, :unidade_a, 'cliente-sem-legado', 'email', 'contact://cliente-sem-legado-email'),
                    (:tenant, :unidade_b, 'cliente-b', 'whatsapp', 'contact://cliente-b-whatsapp')
                """
            ),
            {"tenant": TENANT, "unidade_a": UNIDADE_A, "unidade_b": UNIDADE_B},
        )
        connection.execute(
            text(
                """
                INSERT INTO crm_cliente_legado_v1
                    (tenant_id, unidade_id, legacy_cliente_id, cliente_id,
                     criado_por, correlation_id, criado_em)
                VALUES
                    (:tenant, :unidade_a, 1, 'cliente-a', 'seed', 'corr-seed-a', '2026-08-01'),
                    (:tenant, :unidade_b, 2, 'cliente-b', 'seed', 'corr-seed-b', '2026-08-03')
                """
            ),
            {"tenant": TENANT, "unidade_a": UNIDADE_A, "unidade_b": UNIDADE_B},
        )
        connection.execute(
            text(
                """
                INSERT INTO crm_cashback_saldos_v1
                    (tenant_id, unidade_id, cliente_id, saldo, versao)
                VALUES
                    (:tenant, :unidade_a, 'cliente-a', 12.00, 1),
                    (:tenant, :unidade_b, 'cliente-b', 7.00, 1)
                """
            ),
            {"tenant": TENANT, "unidade_a": UNIDADE_A, "unidade_b": UNIDADE_B},
        )
        connection.execute(
            text(
                """
                INSERT INTO crm_cashback_movimentos_v1
                    (tenant_id, unidade_id, movimento_id, cliente_id, tipo,
                     valor, origem, referencia, ocorrido_em, idempotency_key)
                VALUES
                    (:tenant, :unidade_a, 'mov-a-1', 'cliente-a', 'credito',
                     12.00, 'regularizacao', 'seed://cliente-a', '2026-08-10', 'seed-a-1'),
                    (:tenant, :unidade_b, 'mov-b-1', 'cliente-b', 'credito',
                     7.00, 'regularizacao', 'seed://cliente-b', '2026-08-11', 'seed-b-1')
                """
            ),
            {"tenant": TENANT, "unidade_a": UNIDADE_A, "unidade_b": UNIDADE_B},
        )

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
    return engine, TestClient(app)


def _login(client: TestClient, email: str = ADMIN_EMAIL) -> None:
    response = client.post("/v1/auth/login", json={"email": email, "senha": SENHA})
    assert response.status_code == 200


def test_crm_exige_sessao_e_permissao_cliente_visualizar(monkeypatch) -> None:
    _, client = _infra(monkeypatch)

    sem_sessao = client.get("/v1/crm/clientes")
    _login(client, COZINHA_EMAIL)
    sem_permissao = client.get("/v1/crm/clientes")

    assert sem_sessao.status_code == 401
    assert sem_sessao.json() == {"erro": "credenciais_invalidas"}
    assert sem_permissao.status_code == 403
    assert sem_permissao.json() == {"erro": "seguranca.permissao_insuficiente"}


def test_crm_lista_clientes_e_cashback_somente_da_unidade_ativa(monkeypatch) -> None:
    _, client = _infra(monkeypatch)
    _login(client)

    response = client.get(
        "/v1/crm/clientes",
        headers={"X-Tenant-ID": "tenant-spoof", "X-Unit-ID": UNIDADE_B},
    )

    assert response.status_code == 200
    assert [item["cliente_id"] for item in response.json()["itens"]] == [
        "cliente-a",
        "cliente-sem-legado",
    ]
    assert response.json()["saldo_total"] == "12.00"
    cliente = response.json()["itens"][0]
    assert cliente["nome"] == "Ana Cliente"
    assert cliente["whatsapp"] == "5511999000001"
    assert cliente["saldo_cashback"] == "12.00"
    assert cliente["legacy_cliente_id"] == 1
    assert response.json()["itens"][1]["legacy_cliente_id"] is None


def test_crm_expoe_historico_canonico_e_falha_fechado_cross_unit(monkeypatch) -> None:
    _, client = _infra(monkeypatch)
    _login(client)

    historico = client.get("/v1/crm/clientes/cliente-a/cashback")
    cross_unit = client.get("/v1/crm/clientes/cliente-b/cashback")

    assert historico.status_code == 200
    assert historico.json()["saldo"] == "12.00"
    assert historico.json()["movimentos"] == [
        {
            "movimento_id": "mov-a-1",
            "tipo": "credito",
            "valor": "12.00",
            "origem": "regularizacao",
            "referencia": "seed://cliente-a",
            "ocorrido_em": "2026-08-10T00:00:00+00:00",
        }
    ]
    assert cross_unit.status_code == 404
    assert cross_unit.json() == {"erro": "crm.cliente_nao_encontrado"}


def test_credito_manual_reutiliza_boundary_exige_step_up_e_e_idempotente(
    monkeypatch,
) -> None:
    engine, client = _infra(monkeypatch)
    _login(client)
    headers = {"Idempotency-Key": "crm-credito-manual-001"}

    sem_step_up = client.post(
        "/v1/crm/clientes/cliente-a/cashback/creditos",
        headers=headers,
        json={"valor": "5.00"},
    )
    assert sem_step_up.status_code == 403
    assert sem_step_up.json() == {"erro": "seguranca.admin_step_up_exigido"}

    elevado = client.post("/v1/auth/admin-step-up", json={"senha": SENHA})
    assert elevado.status_code == 200

    primeiro = client.post(
        "/v1/crm/clientes/cliente-a/cashback/creditos",
        headers=headers,
        json={"valor": "5.00"},
    )
    replay = client.post(
        "/v1/crm/clientes/cliente-a/cashback/creditos",
        headers=headers,
        json={"valor": "5.00"},
    )

    assert primeiro.status_code == 200
    assert primeiro.json() == {
        "cliente_id": "cliente-a",
        "legacy_cliente_id": 1,
        "saldo": "17.00",
    }
    assert replay.status_code == 200
    assert replay.json() == primeiro.json()

    with engine.begin() as connection:
        saldo_legado = connection.execute(
            text("SELECT saldo_cashback FROM clientes WHERE id = 1")
        ).scalar_one()
        total_movimentos = connection.execute(
            text(
                "SELECT COUNT(*) FROM crm_cashback_movimentos_v1 "
                "WHERE tenant_id = :tenant AND unidade_id = :unidade "
                "AND cliente_id = 'cliente-a'"
            ),
            {"tenant": TENANT, "unidade": UNIDADE_A},
        ).scalar_one()
    assert float(saldo_legado) == 17.0
    assert int(total_movimentos) == 2


def test_credito_manual_falha_sem_mapping_legado(monkeypatch) -> None:
    _, client = _infra(monkeypatch)
    _login(client)
    assert (
        client.post("/v1/auth/admin-step-up", json={"senha": SENHA}).status_code == 200
    )

    response = client.post(
        "/v1/crm/clientes/cliente-sem-legado/cashback/creditos",
        headers={"Idempotency-Key": "crm-sem-mapping-001"},
        json={"valor": "5.00"},
    )

    assert response.status_code == 409
    assert response.json() == {"erro": "cliente_legado_sem_mapping_crm"}


def test_resgates_http_reutiliza_boundary_e_preserva_escopo_da_sessao(
    monkeypatch,
) -> None:
    _, client = _infra(monkeypatch)
    monkeypatch.setattr(
        "http_api.crm.generate_content",
        lambda **_: SimpleNamespace(text="Mensagem Gemini WP-017"),
    )
    _login(client)

    response = client.get(
        "/v1/crm/resgates/inativos",
        headers={"X-Tenant-ID": "tenant-spoof", "X-Unit-ID": UNIDADE_B},
    )

    assert response.status_code == 200
    assert response.json() == {
        "itens": [
            {
                "legacy_cliente_id": 1,
                "cliente_id": "cliente-a",
                "nome": "Ana Cliente",
                "whatsapp": "5511999000001",
                "ultima_compra": "2026-08-20T00:00:00",
                "total_gasto": 120.0,
                "status": "Ativo",
                "mensagem_sugerida": "Mensagem Gemini WP-017",
            }
        ]
    }


def test_despacho_resgate_http_exige_step_up_e_delega_ao_boundary(
    monkeypatch,
) -> None:
    _, client = _infra(monkeypatch)
    chamadas = []

    def despachar_fake(**kwargs):
        chamadas.append(kwargs)
        return SimpleNamespace(
            cliente_id="cliente-a",
            enviado=True,
            motivo="enviado",
            mensagem_id="msg-http-wp017",
        )

    monkeypatch.setattr(
        "http_api.crm.despachar_resgate_cliente_inativo",
        despachar_fake,
    )
    _login(client)

    sem_step_up = client.post(
        "/v1/crm/resgates/1/despachar",
        json={"texto": "Mensagem sugerida pela autoridade."},
    )
    assert sem_step_up.status_code == 403
    assert sem_step_up.json() == {"erro": "seguranca.admin_step_up_exigido"}
    assert chamadas == []

    assert (
        client.post("/v1/auth/admin-step-up", json={"senha": SENHA}).status_code
        == 200
    )
    response = client.post(
        "/v1/crm/resgates/1/despachar",
        headers={
            "X-Tenant-ID": "tenant-spoof",
            "X-Unit-ID": UNIDADE_B,
            "X-Correlation-ID": "corr-http-wp017",
        },
        json={"texto": "Mensagem sugerida pela autoridade."},
    )

    assert response.status_code == 200
    assert response.json() == {
        "cliente_id": "cliente-a",
        "enviado": True,
        "motivo": "enviado",
        "mensagem_id": "msg-http-wp017",
    }
    assert len(chamadas) == 1
    assert chamadas[0]["legacy_cliente_id"] == 1
    assert chamadas[0]["texto"] == "Mensagem sugerida pela autoridade."
    assert chamadas[0]["contexto"].tenant_id == TENANT
    assert chamadas[0]["contexto"].unidade_id == UNIDADE_A
    assert chamadas[0]["contexto"].correlation_id == "corr-http-wp017"
