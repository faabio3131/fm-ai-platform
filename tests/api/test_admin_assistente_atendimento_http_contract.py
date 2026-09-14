from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.assistente_atendimento.atendimento_modelos import EstadoAtendimento
from core.runtime.config import RuntimeEnvironment, RuntimeSettings
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Papel
from http_api.frontend_app import build_frontend_http_app
from infra.assistente_atendimento.canal_estado_sqlalchemy import (
    EncryptedSQLAlchemyChannelStateStore,
)
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy
from migrations.runner import run_migrations

SESSION_SECRET = "admin-assistente-session-secret-0123456789"
SENHA = "Senha-Segura-Assistente-123"
TENANT = "tenant-assistente-http"
UNIDADE_A = "unidade-assistente-a"
UNIDADE_B = "unidade-assistente-b"
ADMIN_EMAIL = "admin-assistente@example.com"
CONVERSA_A = "conv-assistente-a"
CONVERSA_B = "conv-assistente-b"
TELEFONE_A = "5511999990001"
TELEFONE_B = "5511999990002"


def _infra(monkeypatch) -> tuple[TestClient, sessionmaker]:
    monkeypatch.setenv("FM_AI_SESSION_SECRET", SESSION_SECRET)
    monkeypatch.setenv(
        "FM_AI_SECRET_MASTER_KEY",
        Fernet.generate_key().decode("ascii"),
    )
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    run_migrations(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        RepositorioIdentidadesSQLAlchemy(session).criar_usuario(
            usuario_id="admin-assistente-user",
            email=ADMIN_EMAIL,
            password=SENHA,
            tenant_id=TENANT,
            unidade_padrao_id=UNIDADE_A,
            papeis=(Papel.ADMINISTRADOR,),
            unidades_permitidas=(UNIDADE_A, UNIDADE_B),
            acesso_admin_sensivel=True,
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
    response = client.post(
        "/v1/auth/login",
        json={"email": ADMIN_EMAIL, "senha": SENHA},
    )
    assert response.status_code == 200
    if elevar:
        response = client.post("/v1/auth/admin-step-up", json={"senha": SENHA})
        assert response.status_code == 200


def _contexto(tenant_id: str, unidade_id: str) -> ContextoExecucao:
    return ContextoExecucao.sistema(
        identidade="seed-assistente-http",
        motivo="seed do contrato HTTP WP-027",
        tenant_id=tenant_id,
        unidade_id=unidade_id,
        correlation_id=f"seed:{tenant_id}:{unidade_id}",
        solicitado_em=datetime.now(timezone.utc),
    )


def _state_runtime(estado: str) -> dict:
    return {
        "cliente_tipo": "novo",
        "cliente_ref": None,
        "cliente_nome": None,
        "resultado": {
            "estado": estado,
            "mensagem": "Mensagem operacional anterior.",
            "carrinho": None,
            "checkout": None,
            "handoff_motivo": None,
            "auditoria": [],
        },
    }


def _seed_conversa(
    factory,
    *,
    tenant_id: str,
    unidade_id: str,
    conversa_id: str,
    telefone: str,
) -> None:
    with factory() as session:
        EncryptedSQLAlchemyChannelStateStore(session).salvar(
            contexto=_contexto(tenant_id, unidade_id),
            canal="whatsapp",
            recipient=telefone,
            conversa_id=conversa_id,
            estado=EstadoAtendimento.AGUARDANDO_MODALIDADE_ENTREGA.value,
            state=_state_runtime(EstadoAtendimento.AGUARDANDO_MODALIDADE_ENTREGA.value),
            pedido_id="pedido-wp027",
            pagamento_id="pagamento-wp027",
            entrega_id="entrega-wp027",
            ultimo_inbound_id="inbound-wp027",
            ultimo_outbound_id="outbound-wp027",
            ultimo_status_hash="status-wp027",
            versao_esperada=0,
        )
        session.commit()


def test_assistente_admin_exige_sessao_e_stepup(monkeypatch) -> None:
    client, _ = _infra(monkeypatch)

    sem_sessao = client.get("/v1/admin/assistente-atendimento/identidade")
    assert sem_sessao.status_code == 401

    _login(client, elevar=False)
    sem_stepup = client.get("/v1/admin/assistente-atendimento/identidade")
    assert sem_stepup.status_code == 403
    assert sem_stepup.json() == {"erro": "seguranca.admin_step_up_exigido"}


def test_identidade_fallback_bootstrap_e_concorrencia(monkeypatch) -> None:
    client, _ = _infra(monkeypatch)
    _login(client)

    fallback = client.get("/v1/admin/assistente-atendimento/identidade")
    assert fallback.status_code == 200
    assert fallback.json()["nome_publico"] == "Assistente de Atendimento"
    assert fallback.json()["versao"] == 1
    assert fallback.json()["atualizado_em"] is None

    primeira = client.put(
        "/v1/admin/assistente-atendimento/identidade",
        json={
            "nome_publico": "Lia",
            "atributos": {"tom": "acolhedor"},
            "versao_esperada": 1,
        },
    )
    assert primeira.status_code == 200
    assert primeira.json()["nome_publico"] == "Lia"
    assert primeira.json()["versao"] == 1
    assert primeira.json()["atualizado_em"] is not None

    segunda = client.put(
        "/v1/admin/assistente-atendimento/identidade",
        json={
            "nome_publico": "Lia Atendimento",
            "atributos": {"tom": "objetivo"},
            "versao_esperada": 1,
        },
    )
    assert segunda.status_code == 200
    assert segunda.json()["versao"] == 2

    conflito = client.put(
        "/v1/admin/assistente-atendimento/identidade",
        json={
            "nome_publico": "Versão antiga",
            "atributos": {},
            "versao_esperada": 1,
        },
    )
    assert conflito.status_code == 409
    assert conflito.json() == {"erro": "configuracao_assistente_desatualizada"}


def test_listagem_e_detalhe_respeitam_tenant_e_unidade(monkeypatch) -> None:
    client, factory = _infra(monkeypatch)
    _seed_conversa(
        factory,
        tenant_id=TENANT,
        unidade_id=UNIDADE_A,
        conversa_id=CONVERSA_A,
        telefone=TELEFONE_A,
    )
    _seed_conversa(
        factory,
        tenant_id=TENANT,
        unidade_id=UNIDADE_B,
        conversa_id=CONVERSA_B,
        telefone=TELEFONE_B,
    )
    _login(client)

    response = client.get("/v1/admin/assistente-atendimento/conversas")
    assert response.status_code == 200
    conversas = response.json()["conversas"]
    assert [item["conversa_id"] for item in conversas] == [CONVERSA_A]
    assert conversas[0]["atualizado_em"]

    detalhe = client.get(f"/v1/admin/assistente-atendimento/conversas/{CONVERSA_A}")
    assert detalhe.status_code == 200
    assert detalhe.json()["conversa_id"] == CONVERSA_A
    assert detalhe.json()["ultimo_inbound_id"] == "inbound-wp027"
    assert detalhe.json()["ultimo_outbound_id"] == "outbound-wp027"

    fora_escopo = client.get(
        f"/v1/admin/assistente-atendimento/conversas/{CONVERSA_B}"
    )
    assert fora_escopo.status_code == 404
    assert fora_escopo.json() == {"erro": "conversa_nao_encontrada"}


def test_handoff_forcado_pausa_runtime_e_preserva_estado_operacional(monkeypatch) -> None:
    client, factory = _infra(monkeypatch)
    _seed_conversa(
        factory,
        tenant_id=TENANT,
        unidade_id=UNIDADE_A,
        conversa_id=CONVERSA_A,
        telefone=TELEFONE_A,
    )
    _login(client)

    response = client.post(
        f"/v1/admin/assistente-atendimento/conversas/{CONVERSA_A}/handoff",
        json={"motivo": "cliente solicitou atendimento humano"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "handoff_registrado"

    with factory() as session:
        estado = EncryptedSQLAlchemyChannelStateStore(session).obter_por_conversa(
            contexto=_contexto(TENANT, UNIDADE_A),
            conversa_id=CONVERSA_A,
        )
        assert estado is not None
        assert estado.estado == EstadoAtendimento.HANDOFF_HUMANO.value
        assert estado.pedido_id == "pedido-wp027"
        assert estado.pagamento_id == "pagamento-wp027"
        assert estado.entrega_id == "entrega-wp027"
        assert estado.ultimo_inbound_id == "inbound-wp027"
        assert estado.ultimo_outbound_id == "outbound-wp027"
        assert estado.ultimo_status_hash == "status-wp027"
        assert estado.state is not None
        resultado = estado.state["resultado"]
        assert resultado["estado"] == EstadoAtendimento.HANDOFF_HUMANO.value
        assert resultado["handoff_motivo"] == "cliente solicitou atendimento humano"

    detalhe = client.get(f"/v1/admin/assistente-atendimento/conversas/{CONVERSA_A}")
    assert detalhe.status_code == 200
    assert detalhe.json()["estado"] == EstadoAtendimento.HANDOFF_HUMANO.value
    assert detalhe.json()["handoff_contexto"]["motivo"] == (
        "cliente solicitou atendimento humano"
    )


def test_handoff_forcado_e_idempotente_quando_ja_esta_em_handoff(monkeypatch) -> None:
    client, factory = _infra(monkeypatch)
    _seed_conversa(
        factory,
        tenant_id=TENANT,
        unidade_id=UNIDADE_A,
        conversa_id=CONVERSA_A,
        telefone=TELEFONE_A,
    )
    _login(client)

    primeiro = client.post(
        f"/v1/admin/assistente-atendimento/conversas/{CONVERSA_A}/handoff",
        json={"motivo": "primeiro handoff"},
    )
    assert primeiro.status_code == 200

    with factory() as session:
        antes = EncryptedSQLAlchemyChannelStateStore(session).obter_por_conversa(
            contexto=_contexto(TENANT, UNIDADE_A),
            conversa_id=CONVERSA_A,
        )
        assert antes is not None
        versao = antes.versao

    segundo = client.post(
        f"/v1/admin/assistente-atendimento/conversas/{CONVERSA_A}/handoff",
        json={"motivo": "segundo handoff"},
    )
    assert segundo.status_code == 200

    with factory() as session:
        depois = EncryptedSQLAlchemyChannelStateStore(session).obter_por_conversa(
            contexto=_contexto(TENANT, UNIDADE_A),
            conversa_id=CONVERSA_A,
        )
        assert depois is not None
        assert depois.versao == versao


def test_router_wp027_permanece_http_fino() -> None:
    source = Path("http_api/admin_assistente_atendimento.py").read_text(encoding="utf-8")
    assert "from infra." not in source
    assert "session.execute" not in source
    assert "UnitOfWorkV1" not in source
