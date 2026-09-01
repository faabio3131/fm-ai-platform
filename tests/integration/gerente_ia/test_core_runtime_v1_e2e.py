from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from application.ai_router_runtime import construir_ai_model_router
from application.gerente_ia_runtime import PlanejadorAIRouterCore
from core.ai_router import CapabilityIA, MedidorUsoIAEmMemoria
from core.dominio.ids import (
    CorrelationId,
    EventoId,
    IdempotencyKey,
    TenantId,
    UnidadeId,
)
from core.eventos.modelos import EnvelopeMensagem
from core.gerente_ia.modelos import ChamadaTool, ToolGerenteIA
from core.kds.modelos_orm import ProducaoItemORM, SetorProducaoORM
from core.pedidos.modelos_orm import ItemPedidoORM, PedidoORM
from core.runtime.config import load_runtime_settings
from core.seguranca.permissoes import Papel
from core.seguranca.segredos import ReferenceSecretStore
from http_api.app import build_http_app
from infra.gerente_ia.modelos_orm import (
    ConsentimentoCRMAtualORM,
    DisponibilidadeProdutoORM,
    EventoCoreORM,
    IdentidadeAssistenteORM,
    PreviewGerenteIAORM,
    RascunhoCampanhaORM,
    ResultadoAcaoGerenteIAORM,
)
from infra.gerente_ia.persistencia_sqlalchemy import ConsumidorEventosCoreSQLAlchemy
from infra.integracoes.modelos_orm import ServicoExternoConfigORM
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy
from infra.seguranca.modelos_orm import CredencialReferenciaORM
from infra.transacoes.uow import UnitOfWorkV1
from migrations.runner import run_migrations

AGORA = datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc)
SENHA = "Senha-Segura-123"


class PlanejadorCaptura:
    def __init__(self) -> None:
        self.chamadas: list[tuple[str, str]] = []

    def planejar(self, *, pergunta: str, nome_assistente: str) -> ChamadaTool:
        self.chamadas.append((pergunta, nome_assistente))
        return ChamadaTool.de_dict(
            ToolGerenteIA.GERAR_RELATORIO, {"tipo": "operacional"}
        )


class GatewayGeminiCaptura:
    def __init__(self) -> None:
        self.chamadas: list[dict] = []

    def generate_content(self, *, api_key: str, model: str, contents, timeout_seconds: float):
        self.chamadas.append(
            {"api_key": api_key, "model": model, "contents": contents, "timeout": timeout_seconds}
        )
        return '{"tool":"gerar_relatorio","argumentos":{"tipo":"operacional"}}'


def _infra():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    run_migrations(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return engine, factory


def _seed(factory) -> None:
    with factory() as session:
        identidades = RepositorioIdentidadesSQLAlchemy(session)
        for tenant, email in (("tenant-a", "admin-a@example.com"), ("tenant-b", "admin-b@example.com")):
            identidades.criar_usuario(
                email=email,
                password=SENHA,
                tenant_id=tenant,
                unidade_padrao_id="loja-1",
                papeis=(Papel.ADMINISTRADOR,),
            )
        session.add_all(
            [
                PedidoORM(
                    id=f"pedido-{sufixo}", tenant_id=tenant, unidade_id="loja-1",
                    origem="pdv", canal="pdv", status="confirmado", cliente_id=None,
                    criado_em=AGORA, atualizado_em=AGORA, versao=1,
                    correlation_id=f"corr-{sufixo}", idempotency_key=f"pedido-{sufixo}",
                    request_hash=(sufixo * 64)[:64], subtotal=Decimal(30),
                    descontos=Decimal(0), taxas=Decimal(0), total=Decimal(30),
                )
                for tenant, sufixo in (("tenant-a", "a"), ("tenant-b", "b"))
            ]
        )
        session.add_all(
            [
                ItemPedidoORM(
                    id=f"item-{sufixo}", tenant_id=tenant, unidade_id="loja-1",
                    pedido_id=f"pedido-{sufixo}", ordem=0, produto_id="produto-1",
                    nome_produto="Produto", quantidade=1, preco_unitario=Decimal(30),
                    subtotal=Decimal(30), observacao=None, ficha_versao=None,
                )
                for tenant, sufixo in (("tenant-a", "a"), ("tenant-b", "b"))
            ]
        )
        session.add(
            SetorProducaoORM(
                id="setor-a", tenant_id="tenant-a", unidade_id="loja-1",
                codigo="chapa", nome="Chapa", ordem=1, sla_segundos=600, ativo=True,
                criado_em=AGORA, atualizado_em=AGORA,
            )
        )
        session.add(
            ProducaoItemORM(
                id="producao-a", tenant_id="tenant-a", unidade_id="loja-1",
                pedido_id="pedido-a", pedido_item_id="item-a", setor_id="setor-a",
                status="em_preparo", prioridade=2, quantidade=Decimal(1), tentativa=1,
                versao=1, criado_em=AGORA, atualizado_em=AGORA,
                pausa_acumulada_segundos=0, idempotency_key="producao-a",
                request_hash="c" * 64,
            )
        )
        session.commit()


def _evento_crm() -> EnvelopeMensagem:
    return EnvelopeMensagem(
        event_id=EventoId("evento-crm-a"),
        event_type="cliente.consentiu_marketing",
        aggregate_id="cliente-a",
        aggregate_type="cliente",
        tenant_id=TenantId("tenant-a"),
        unidade_id=UnidadeId("loja-1"),
        correlation_id=CorrelationId("corr-crm-a"),
        causation_id=None,
        idempotency_key=IdempotencyKey("crm-consentimento-a"),
        occurred_at=AGORA,
        payload={
            "cliente_id": "cliente-a", "canal": "whatsapp",
            "finalidade": "promocoes", "status": "concedido",
            "token": "nao-persistir",
        },
    )


def test_runtime_real_autenticado_eventos_acoes_llm_e_assistente_isolados(monkeypatch) -> None:
    monkeypatch.setenv("FM_AI_TEST_MODE", "1")
    engine, factory = _infra()
    _seed(factory)
    with UnitOfWorkV1(factory) as uow:
        uow.registrar_efeitos(eventos=(_evento_crm(),))
        uow.commit()
    with factory() as session:
        assert ConsumidorEventosCoreSQLAlchemy(session).consumir(_evento_crm()) is False

    planejador = PlanejadorCaptura()
    settings = load_runtime_settings(test_database_url="sqlite:///:memory:")
    app = build_http_app(
        settings=settings,
        engine=engine,
        session_factory=factory,
        planejador_llm_factory=lambda _: planejador,
    )
    client = TestClient(app)
    auth_a = ("admin-a@example.com", SENHA)
    auth_b = ("admin-b@example.com", SENHA)

    fallback = client.get("/v1/core/assistente-atendimento/identidade", auth=auth_a)
    assert fallback.status_code == 200
    assert fallback.json()["nome_publico"] == "Assistente de Atendimento"

    resposta_a = client.put(
        "/v1/core/assistente-atendimento/identidade",
        auth=auth_a,
        json={"nome_publico": "Lia", "atributos": {"tom": "acolhedor"}},
    )
    resposta_b = client.put(
        "/v1/core/assistente-atendimento/identidade",
        auth=auth_b,
        json={"nome_publico": "Beto", "atributos": {"tom": "direto"}},
    )
    assert resposta_a.json()["nome_publico"] == "Lia"
    assert resposta_b.json()["nome_publico"] == "Beto"
    alterada = client.put(
        "/v1/core/assistente-atendimento/identidade",
        auth=auth_a,
        json={"nome_publico": "Lia Nova", "versao_esperada": 1},
    )
    assert alterada.json()["versao"] == 2
    assert client.get("/v1/core/assistente-atendimento/identidade", auth=auth_b).json()["nome_publico"] == "Beto"

    relatorio = client.post(
        "/v1/core/tools", auth=auth_a,
        json={"tool": "gerar_relatorio", "argumentos": {"tipo": "operacional"}},
    )
    assert relatorio.status_code == 200
    registros = relatorio.json()["registros"]
    assert registros[0]["campos"]

    conversao = client.post(
        "/v1/core/tools", auth=auth_a,
        json={"tool": "acompanhar_conversao", "argumentos": {"canal": "whatsapp"}},
    )
    assert next(iter(conversao.json()["registros"]))["campos"]

    campanha = client.post(
        "/v1/core/tools", auth=auth_a,
        json={
            "tool": "preparar_campanha",
            "argumentos": {
                "canal": "whatsapp", "finalidade": "promocoes",
                "objetivo": "Retenção", "texto_base": "Mensagem para revisão humana",
                "idempotency_key": "campanha-a",
            },
        },
    )
    assert campanha.status_code == 200
    assert campanha.json()["audiencia_elegivel"] == 1
    assert campanha.json()["status"] == "rascunho"

    preview_response = client.post(
        "/v1/core/tools", auth=auth_a,
        json={
            "tool": "priorizar_pedido",
            "argumentos": {"pedido_id": "pedido-a", "prioridade": 8, "motivo": "SLA excedido"},
        },
    )
    assert preview_response.status_code == 200
    preview = preview_response.json()
    negado_outro_tenant = client.post(
        f"/v1/core/actions/{preview['preview_id']}/confirm", auth=auth_b,
        json={"fingerprint": preview["fingerprint"], "idempotency_key": "acao-a"},
    )
    assert negado_outro_tenant.status_code == 400
    confirmado = client.post(
        f"/v1/core/actions/{preview['preview_id']}/confirm", auth=auth_a,
        json={"fingerprint": preview["fingerprint"], "idempotency_key": "acao-a"},
    )
    assert confirmado.status_code == 200
    assert confirmado.json()["resultado"].startswith("pedido_priorizado:pedido-a:8")
    repetido = client.post(
        f"/v1/core/actions/{preview['preview_id']}/confirm", auth=auth_a,
        json={"fingerprint": preview["fingerprint"], "idempotency_key": "acao-a"},
    )
    assert repetido.json()["idempotente"] is True

    preview_pausa = client.post(
        "/v1/core/tools", auth=auth_a,
        json={
            "tool": "pausar_produto",
            "argumentos": {
                "produto_id": "produto-1", "duracao_minutos": 30,
                "motivo": "Estoque crítico",
            },
        },
    ).json()
    pausa = client.post(
        f"/v1/core/actions/{preview_pausa['preview_id']}/confirm", auth=auth_a,
        json={"fingerprint": preview_pausa["fingerprint"], "idempotency_key": "pausa-a"},
    )
    assert pausa.status_code == 200
    assert pausa.json()["resultado"].startswith("produto_pausado:produto-1")

    pergunta_a = client.post("/v1/core/perguntar", auth=auth_a, json={"pergunta": "Como está a operação?"})
    pergunta_b = client.post("/v1/core/perguntar", auth=auth_b, json={"pergunta": "Como está a operação?"})
    assert pergunta_a.status_code == pergunta_b.status_code == 200
    assert pergunta_a.json()["assistente"] == "Lia Nova"
    assert pergunta_b.json()["assistente"] == "Beto"
    assert planejador.chamadas[-2:] == [
        ("Como está a operação?", "Lia Nova"),
        ("Como está a operação?", "Beto"),
    ]

    with Session(engine) as session:
        assert session.scalar(select(ProducaoItemORM.prioridade).where(ProducaoItemORM.id == "producao-a")) == 8
        assert session.scalar(select(EventoCoreORM).where(EventoCoreORM.event_id == "evento-crm-a")).payload_seguro["token"] == "[REDACTED]"
        assert session.scalar(select(ConsentimentoCRMAtualORM).where(ConsentimentoCRMAtualORM.tenant_id == "tenant-a")) is not None
        assert session.scalar(select(IdentidadeAssistenteORM).where(IdentidadeAssistenteORM.tenant_id == "tenant-b")).nome_publico == "Beto"
        assert session.scalar(select(PreviewGerenteIAORM).where(PreviewGerenteIAORM.preview_id == preview["preview_id"])).status == "executado"
        assert session.scalar(select(ResultadoAcaoGerenteIAORM).where(ResultadoAcaoGerenteIAORM.idempotency_key == "acao-a")) is not None
        assert session.scalar(select(RascunhoCampanhaORM).where(RascunhoCampanhaORM.idempotency_key == "campanha-a")).status == "rascunho"
        disponibilidade = session.get(DisponibilidadeProdutoORM, ("tenant-a", "loja-1", "produto-1"))
        assert disponibilidade is not None and disponibilidade.pausado is True


def test_ai_router_resolve_gemini_por_tenant_sem_acoplar_consumer() -> None:
    _, factory = _infra()
    _seed(factory)

    with factory() as session:
        for tenant, sufixo in (
            ("tenant-a", "a"),
            ("tenant-b", "b"),
        ):
            session.add(
                ServicoExternoConfigORM(
                    tenant_id=tenant,
                    unidade_id="loja-1",
                    configuracao_id="gemini-padrao",
                    servico="ia.generativa",
                    provedor="gemini",
                    conta_externa=f"conta-{sufixo}",
                    ambiente="homologacao",
                    parametros_publicos={
                        "model": f"modelo-{sufixo}",
                    },
                    finalidades_credenciais={
                        "api_key": "core_llm",
                    },
                    habilitada=True,
                    homologada=True,
                    evidencia_homologacao_ref=(
                        f"evidencia://{sufixo}"
                    ),
                    versao=1,
                    atualizado_por="admin",
                    correlation_id=f"corr-{sufixo}",
                    criado_em=AGORA,
                    atualizado_em=AGORA,
                )
            )

            session.add(
                CredencialReferenciaORM(
                    tenant_id=tenant,
                    unidade_id="loja-1",
                    provedor="gemini",
                    finalidade="core_llm",
                    referencia=f"mapping:key-{sufixo}",
                    versao=1,
                    ativa=True,
                    rotacionada_por="admin",
                    correlation_id=f"corr-{sufixo}",
                    criada_em=AGORA,
                )
            )

        session.commit()

    gateway = GatewayGeminiCaptura()

    store = ReferenceSecretStore(
        mapping={
            "key-a": "segredo-a",
            "key-b": "segredo-b",
        }
    )

    metering = MedidorUsoIAEmMemoria()

    with factory() as session:
        repo = RepositorioIdentidadesSQLAlchemy(session)

        identidade_a = repo.obter_por_email(
            "admin-a@example.com"
        )
        identidade_b = repo.obter_por_email(
            "admin-b@example.com"
        )

        assert identidade_a is not None
        assert identidade_b is not None

        contexto_a = identidade_a.contexto(
            origem="teste"
        )
        contexto_b = identidade_b.contexto(
            origem="teste"
        )

        router_a = construir_ai_model_router(
            session=session,
            contexto=contexto_a,
            secret_store=store,
            gemini_gateway=gateway,
            metering=metering,
        )

        router_b = construir_ai_model_router(
            session=session,
            contexto=contexto_b,
            secret_store=store,
            gemini_gateway=gateway,
            metering=metering,
        )

        chamada_a = PlanejadorAIRouterCore(
            router=router_a,
            contexto=contexto_a,
        ).planejar(
            pergunta="Como está?",
            nome_assistente="Lia",
        )

        chamada_b = PlanejadorAIRouterCore(
            router=router_b,
            contexto=contexto_b,
        ).planejar(
            pergunta="Como está?",
            nome_assistente="Beto",
        )

    assert (
        chamada_a.tool
        is chamada_b.tool
        is ToolGerenteIA.GERAR_RELATORIO
    )

    assert [
        (item["api_key"], item["model"])
        for item in gateway.chamadas
    ] == [
        ("segredo-a", "modelo-a"),
        ("segredo-b", "modelo-b"),
    ]

    assert "Lia" in gateway.chamadas[0]["contents"]["system"]
    assert "Beto" in gateway.chamadas[1]["contents"]["system"]

    assert len(metering.eventos) == 2

    assert [
        evento.provider
        for evento in metering.eventos
    ] == ["gemini", "gemini"]

    assert all(
        evento.capability is CapabilityIA.TOOL_PLANNING
        for evento in metering.eventos
    )

    assert all(
        evento.price_snapshot_id == "legacy-unpriced-v1"
        for evento in metering.eventos
    )
