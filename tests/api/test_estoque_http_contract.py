from __future__ import annotations

import io
import json
from types import SimpleNamespace

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.runtime.config import RuntimeEnvironment, RuntimeSettings
from core.seguranca.permissoes import Papel
from http_api.frontend_app import build_frontend_http_app
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy
from migrations.runner import run_migrations

AUTH_KEY = "k" * 64
LOGIN_VALUE = "p" * 24
TENANT = "tenant-estoque-http"
UNIDADE_A = "unidade-estoque-a"
UNIDADE_B = "unidade-estoque-b"
ADMIN_EMAIL = "admin-estoque@example.com"
COZINHA_EMAIL = "cozinha-estoque@example.com"


def _infra(monkeypatch) -> tuple[object, TestClient]:
    monkeypatch.setenv("FM_AI_SESSION_SECRET", AUTH_KEY)
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
            usuario_id="usuario-admin-estoque",
            email=ADMIN_EMAIL,
            password=LOGIN_VALUE,
            tenant_id=TENANT,
            unidade_padrao_id=UNIDADE_A,
            papeis=(Papel.ADMINISTRADOR,),
            unidades_permitidas=(UNIDADE_A, UNIDADE_B),
        )
        repositorio.criar_usuario(
            usuario_id="usuario-cozinha-estoque",
            email=COZINHA_EMAIL,
            password=LOGIN_VALUE,
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
                INSERT INTO fm_unidade_loja_legacy_v1
                    (tenant_id, unidade_id, loja_id, ativo)
                VALUES
                    (:tenant, :unidade_a, 71, TRUE),
                    (:tenant, :unidade_b, 72, TRUE)
                """
            ),
            {"tenant": TENANT, "unidade_a": UNIDADE_A, "unidade_b": UNIDADE_B},
        )
        connection.execute(
            text(
                """
                INSERT INTO insumos
                    (id, loja_id, nome, unidade_medida, saldo_atual,
                     estoque_minimo, custo_unitario, data_validade,
                     dias_alerta_vencimento)
                VALUES
                    (11, 71, 'Carne', 'kg', 10.0, 2.0, 30.0,
                     '2026-12-31', 15),
                    (12, 71, 'Pão', 'un', 5.0, 10.0, 1.5,
                     '2026-10-01', 10),
                    (21, 72, 'Queijo outra unidade', 'kg', 5.0, 1.0, 40.0,
                     '2026-11-15', 15)
                """
            )
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
    response = client.post(
        "/v1/auth/login",
        json={"email": email, "senha": LOGIN_VALUE},
    )
    assert response.status_code == 200


def _step_up(client: TestClient) -> None:
    response = client.post(
        "/v1/auth/admin-step-up",
        json={"senha": LOGIN_VALUE},
    )
    assert response.status_code == 200


def _png_bytes() -> bytes:
    arquivo = io.BytesIO()
    Image.new("RGB", (2, 2), "white").save(arquivo, format="PNG")
    return arquivo.getvalue()


def test_estoque_exige_sessao_e_permissao_visualizar(monkeypatch) -> None:
    _, client = _infra(monkeypatch)

    sem_sessao = client.get("/v1/estoque/insumos")
    _login(client, COZINHA_EMAIL)
    sem_permissao = client.get("/v1/estoque/insumos")

    assert sem_sessao.status_code == 401
    assert sem_sessao.json() == {"erro": "seguranca.credenciais_invalidas"}
    assert sem_permissao.status_code == 403
    assert sem_permissao.json() == {"erro": "seguranca.permissao_insuficiente"}


def test_estoque_lista_somente_unidade_ativa_e_ignora_headers_spoof(monkeypatch) -> None:
    _, client = _infra(monkeypatch)
    _login(client)

    response = client.get(
        "/v1/estoque/insumos",
        headers={"X-Tenant-ID": "tenant-spoof", "X-Unit-ID": UNIDADE_B},
    )

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body["itens"]] == ["11", "12"]
    assert all(item["id"] != "21" for item in body["itens"])
    assert body["valor_total"] == 307.5
    assert body["itens"][0]["status_estoque"] == "ok"
    assert body["itens"][1]["status_estoque"] == "reposicao"
    assert body["itens"][0]["status_validade"]


def test_estoque_mutacoes_exigem_step_up_e_persistem_na_unidade(monkeypatch) -> None:
    engine, client = _infra(monkeypatch)
    _login(client)
    payload = {
        "nome": "Tomate",
        "unidade_medida": "kg",
        "saldo_atual": 3.0,
        "estoque_minimo": 1.0,
        "custo_unitario": 8.5,
        "data_fabricacao": "2026-09-15",
        "data_validade": "2026-09-25",
        "dias_alerta_vencimento": 7,
    }

    sem_step_up = client.post("/v1/estoque/insumos", json=payload)
    assert sem_step_up.status_code == 403
    assert sem_step_up.json() == {"erro": "seguranca.admin_step_up_exigido"}

    _step_up(client)
    criado = client.post(
        "/v1/estoque/insumos",
        headers={"X-Tenant-ID": "tenant-spoof", "X-Unit-ID": UNIDADE_B},
        json=payload,
    )

    assert criado.status_code == 201
    assert criado.json()["nome"] == "Tomate"
    assert criado.json()["saldo_atual"] == 3.0
    assert criado.json()["valor_total"] == 25.5

    with engine.begin() as connection:
        row = connection.execute(
            text(
                "SELECT loja_id, saldo_atual, custo_unitario FROM insumos "
                "WHERE nome = 'Tomate'"
            )
        ).one()
    assert int(row.loja_id) == 71
    assert float(row.saldo_atual) == 3.0
    assert float(row.custo_unitario) == 8.5


def test_estoque_leitura_lote_atualiza_existente_e_cria_novo(monkeypatch) -> None:
    engine, client = _infra(monkeypatch)
    _login(client)
    _step_up(client)

    response = client.post(
        "/v1/estoque/leituras",
        json={
            "itens": [
                {
                    "nome": "Carne",
                    "quantidade": 2.5,
                    "unidade": "kg",
                    "data_validade": "2027-01-15",
                },
                {
                    "nome": "Cebola",
                    "quantidade": 4.0,
                    "unidade": "kg",
                    "data_validade": "2026-10-15",
                },
            ]
        },
    )

    assert response.status_code == 200
    assert response.json()["processados"] == 2
    nomes = [item["nome"] for item in response.json()["itens"]]
    assert nomes == ["Carne", "Pão", "Cebola"]

    with engine.begin() as connection:
        carne = connection.execute(
            text("SELECT saldo_atual, loja_id FROM insumos WHERE id = 11")
        ).one()
        cebola = connection.execute(
            text("SELECT saldo_atual, loja_id FROM insumos WHERE nome = 'Cebola'")
        ).one()
    assert float(carne.saldo_atual) == 12.5
    assert int(carne.loja_id) == 71
    assert float(cebola.saldo_atual) == 4.0
    assert int(cebola.loja_id) == 71


def test_estoque_exclusao_falha_fechado_cross_unit_e_remove_local(monkeypatch) -> None:
    engine, client = _infra(monkeypatch)
    _login(client)
    _step_up(client)

    cross_unit = client.delete("/v1/estoque/insumos/21")
    invalido = client.delete("/v1/estoque/insumos/nao-inteiro")
    local = client.delete("/v1/estoque/insumos/12")

    assert cross_unit.status_code == 404
    assert cross_unit.json() == {"erro": "estoque.insumo_nao_encontrado"}
    assert invalido.status_code == 404
    assert local.status_code == 200
    assert local.json() == {"ok": True}

    with engine.begin() as connection:
        local_restante = connection.execute(
            text("SELECT COUNT(*) FROM insumos WHERE id = 12")
        ).scalar_one()
        remoto_restante = connection.execute(
            text("SELECT COUNT(*) FROM insumos WHERE id = 21")
        ).scalar_one()
    assert int(local_restante) == 0
    assert int(remoto_restante) == 1


def test_forecasting_reutiliza_contexto_da_sessao_sem_headers_spoof(
    monkeypatch,
) -> None:
    capturado: dict[str, object] = {}

    def executar_fake(_self, _db_session, **kwargs):
        capturado.update(kwargs)
        return "forecasting-test-ok"

    monkeypatch.setattr(
        "http_api.estoque.AplicacaoForecastingEstoqueV1.executar",
        executar_fake,
    )
    _, client = _infra(monkeypatch)
    _login(client)
    _step_up(client)

    response = client.post(
        "/v1/estoque/forecasting-alertas",
        headers={"X-Tenant-ID": "tenant-spoof", "X-Unit-ID": UNIDADE_B},
    )

    assert response.status_code == 200
    assert response.json() == {"mensagem": "forecasting-test-ok"}
    assert capturado["tenant_id"] == TENANT
    assert capturado["unidade_id"] == UNIDADE_A
    assert callable(capturado["generate_content"])
    assert callable(capturado["mock_whatsapp_send"])


def test_leitura_visual_valida_midia_e_persiste_pelo_application(monkeypatch) -> None:
    monkeypatch.setattr(
        "http_api.estoque.generate_content",
        lambda **_: SimpleNamespace(
            text=json.dumps(
                [
                    {
                        "nome": "Tomate Visual",
                        "quantidade": 2.0,
                        "unidade": "kg",
                        "data_validade": "2026-11-10",
                    }
                ]
            )
        ),
    )
    engine, client = _infra(monkeypatch)
    _login(client)
    _step_up(client)

    tipo_invalido = client.post(
        "/v1/estoque/leituras-visuais",
        content=b"texto",
        headers={"Content-Type": "text/plain"},
    )
    vazio = client.post(
        "/v1/estoque/leituras-visuais",
        content=b"",
        headers={"Content-Type": "image/png"},
    )
    processado = client.post(
        "/v1/estoque/leituras-visuais",
        content=_png_bytes(),
        headers={"Content-Type": "image/png"},
    )

    assert tipo_invalido.status_code == 415
    assert tipo_invalido.json() == {"erro": "estoque.leitura_visual_tipo_invalido"}
    assert vazio.status_code == 400
    assert vazio.json() == {"erro": "estoque.leitura_visual_arquivo_obrigatorio"}
    assert processado.status_code == 200
    assert processado.json()["processados"] == 1
    assert processado.json()["itens_lidos"][0]["nome"] == "Tomate Visual"

    with engine.begin() as connection:
        row = connection.execute(
            text(
                "SELECT loja_id, saldo_atual, data_validade FROM insumos "
                "WHERE nome = 'Tomate Visual'"
            )
        ).one()
    assert int(row.loja_id) == 71
    assert float(row.saldo_atual) == 2.0
    assert str(row.data_validade).startswith("2026-11-10")
