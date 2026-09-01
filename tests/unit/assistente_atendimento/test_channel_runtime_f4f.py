from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from application.assistente_atendimento_runtime import ResultadoRuntimeAssistente
from application.assistente_channel_runtime import RuntimeCanalWhatsAppV1
from core.assistente_atendimento.atendimento_modelos import (
    CarrinhoAtendimento,
    EstadoAtendimento,
    ItemCarrinhoAtendimento,
    ModalidadePedidoAtendimento,
    ResultadoAtendimento,
)
from core.assistente_atendimento.contexto import (
    ClienteAtendimento,
    ContextoAtendimento,
    TipoClienteAtendimento,
)
from core.entrega.modelos_orm import EntregaORM, EventoEntregaORM
from core.integracoes.provedores import (
    ErroProvedorTransitorio,
    MensagemWhatsAppEntrada,
)
from core.kds.modelos_orm import ProducaoItemORM, SetorProducaoORM
from core.pagamentos.modelos_orm import ObrigacaoPagamentoORM, PagamentoORM
from core.pedidos.modelos_orm import PedidoORM
from core.seguranca.contexto import ContextoExecucao
from infra.assistente_atendimento.canal_estado_sqlalchemy import (
    EncryptedSQLAlchemyChannelStateStore,
)
from infra.assistente_atendimento.canal_schema import assistente_canal_conversas_v1
from infra.eventos.modelos_orm import InboxEventoORM
from migrations.runner import run_migrations

AGORA = datetime(2026, 8, 31, 22, 0, tzinfo=timezone.utc)
TENANT = "tenant-f4f"
UNIDADE = "unidade-f4f"
TELEFONE = "5511999999999"


def _infra(monkeypatch):
    monkeypatch.setenv(
        "FM_AI_SECRET_MASTER_KEY",
        Fernet.generate_key().decode("ascii"),
    )
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    run_migrations(engine)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)


def _contexto(
    tenant: str = TENANT,
    unidade: str = UNIDADE,
    correlation_id: str = "corr-f4f",
) -> ContextoExecucao:
    return ContextoExecucao.sistema(
        identidade="teste-f4f",
        motivo="teste do runtime de canal",
        tenant_id=tenant,
        unidade_id=unidade,
        correlation_id=correlation_id,
        solicitado_em=AGORA,
    )


def _carrinho(
    *,
    conversa_id: str,
    mensagem_id: str,
    modalidade: ModalidadePedidoAtendimento = ModalidadePedidoAtendimento.INDEFINIDA,
) -> CarrinhoAtendimento:
    return CarrinhoAtendimento(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        conversa_id=conversa_id,
        mensagem_id=mensagem_id,
        itens=(
            ItemCarrinhoAtendimento(
                produto_id="101",
                nome_produto="Produto F4F",
                quantidade=1,
                preco_unitario=Decimal(25),
            ),
        ),
        fingerprint=f"fp:{mensagem_id}:{modalidade.value}",
        modalidade=modalidade,
    )


class RuntimeFake:
    def __init__(self) -> None:
        self.transcricoes = 0
        self.modalidades = 0

    @staticmethod
    def _inicial(
        *,
        contexto_solicitante: ContextoExecucao,
        conversa_id: str,
        mensagem_id: str,
    ) -> ResultadoRuntimeAssistente:
        contexto = ContextoAtendimento(
            contexto_execucao=contexto_solicitante,
            conversa_id=conversa_id,
            canal="whatsapp",
            cliente=ClienteAtendimento(
                tipo=TipoClienteAtendimento.NOVO,
                cliente_ref=None,
            ),
        )
        return ResultadoRuntimeAssistente(
            contexto=contexto,
            resultado=ResultadoAtendimento(
                estado=EstadoAtendimento.AGUARDANDO_MODALIDADE_ENTREGA,
                mensagem="Você prefere retirada ou entrega?",
                carrinho=_carrinho(
                    conversa_id=conversa_id,
                    mensagem_id=mensagem_id,
                ),
            ),
        )

    def interpretar_texto(self, **kwargs):
        return self._inicial(
            contexto_solicitante=kwargs["contexto_solicitante"],
            conversa_id=kwargs["conversa_id"],
            mensagem_id=kwargs["mensagem_id"],
        )

    def interpretar_audio(self, **kwargs):
        return self._inicial(
            contexto_solicitante=kwargs["contexto_solicitante"],
            conversa_id=kwargs["conversa_id"],
            mensagem_id=kwargs["mensagem_id"],
        )

    def transcrever_audio(self, **_kwargs) -> str:
        self.transcricoes += 1
        return "retirada"

    def definir_modalidade(
        self,
        *,
        runtime_anterior: ResultadoRuntimeAssistente,
        modalidade: ModalidadePedidoAtendimento,
    ) -> ResultadoRuntimeAssistente:
        self.modalidades += 1
        carrinho = runtime_anterior.resultado.carrinho
        assert carrinho is not None
        atualizado = replace(
            carrinho,
            modalidade=modalidade,
            fingerprint=f"{carrinho.fingerprint}:{modalidade.value}",
        )
        return ResultadoRuntimeAssistente(
            contexto=runtime_anterior.contexto,
            resultado=replace(
                runtime_anterior.resultado,
                estado=EstadoAtendimento.AGUARDANDO_FORMA_PAGAMENTO,
                mensagem="Qual forma de pagamento você prefere?",
                carrinho=atualizado,
            ),
        )


class MetaFake:
    def __init__(self, *, falhar_envio: bool = False) -> None:
        self.falhar_envio = falhar_envio
        self.envios: list[dict[str, str]] = []
        self.downloads = 0

    def enviar_whatsapp(self, *, destinatario: str, texto: str, idempotency_key: str):
        self.envios.append(
            {
                "destinatario": destinatario,
                "texto": texto,
                "idempotency_key": idempotency_key,
            }
        )
        if self.falhar_envio:
            raise ErroProvedorTransitorio("Meta indisponivel")
        return f"wamid-out-{len(self.envios)}"

    def baixar_audio_whatsapp(self, **_kwargs):
        self.downloads += 1
        return b"ogg-audio", "audio/ogg"


def test_estado_de_canal_e_cifrado_escopado_e_versionado(monkeypatch) -> None:
    engine, factory = _infra(monkeypatch)
    contexto = _contexto()

    with factory() as session:
        store = EncryptedSQLAlchemyChannelStateStore(session)
        salvo = store.salvar(
            contexto=contexto,
            canal="whatsapp",
            recipient=TELEFONE,
            conversa_id="conv-f4f",
            estado="aguardando",
            state={"mensagem": "conteudo privado f4f"},
            versao_esperada=0,
            agora=AGORA,
        )
        session.commit()
        assert salvo.versao == 1

    with engine.connect() as connection:
        row = connection.execute(
            select(
                assistente_canal_conversas_v1.c.sender_hash,
                assistente_canal_conversas_v1.c.recipient_ciphertext,
                assistente_canal_conversas_v1.c.state_ciphertext,
            )
        ).one()
        assert TELEFONE not in str(row.recipient_ciphertext)
        assert "conteudo privado f4f" not in str(row.state_ciphertext)
        assert row.sender_hash != TELEFONE

    with factory() as session:
        outro = EncryptedSQLAlchemyChannelStateStore(session).obter(
            contexto=_contexto("tenant-outro", UNIDADE),
            canal="whatsapp",
            recipient=TELEFONE,
        )
        assert outro is None

        store = EncryptedSQLAlchemyChannelStateStore(session)
        with pytest.raises(RuntimeError, match="estado_canal_concorrente"):
            store.salvar(
                contexto=contexto,
                canal="whatsapp",
                recipient=TELEFONE,
                conversa_id="conv-f4f",
                estado="alterado",
                state={"x": 1},
                versao_esperada=99,
                agora=AGORA,
            )


def test_replay_da_mesma_mensagem_nao_repete_resposta_ou_efeito(monkeypatch) -> None:
    engine, factory = _infra(monkeypatch)
    runtime_fake = RuntimeFake()
    meta = MetaFake()
    canal = RuntimeCanalWhatsAppV1(factory, runtime=runtime_fake)
    mensagem = MensagemWhatsAppEntrada(
        mensagem_id="wamid-in-1",
        remetente=TELEFONE,
        tipo="text",
        timestamp="1",
        texto="Quero um produto",
    )

    primeiro = canal.processar_mensagem(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        mensagem=mensagem,
        adapter=meta,
    )
    replay = canal.processar_mensagem(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        mensagem=mensagem,
        adapter=meta,
    )

    assert primeiro.duplicada is False
    assert replay.duplicada is True
    assert len(meta.envios) == 1

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(InboxEventoORM)) == 1


def test_audio_followup_reutiliza_conversa_e_avanca_estado(monkeypatch) -> None:
    _engine, factory = _infra(monkeypatch)
    runtime_fake = RuntimeFake()
    meta = MetaFake()
    canal = RuntimeCanalWhatsAppV1(factory, runtime=runtime_fake)

    canal.processar_mensagem(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        mensagem=MensagemWhatsAppEntrada(
            mensagem_id="wamid-texto-inicial",
            remetente=TELEFONE,
            tipo="text",
            timestamp="1",
            texto="Quero um produto",
        ),
        adapter=meta,
    )
    resultado = canal.processar_mensagem(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        mensagem=MensagemWhatsAppEntrada(
            mensagem_id="wamid-audio-followup",
            remetente=TELEFONE,
            tipo="audio",
            timestamp="2",
            media_id="media-audio-1",
            mime_type="audio/ogg",
        ),
        adapter=meta,
    )

    assert resultado.estado == EstadoAtendimento.AGUARDANDO_FORMA_PAGAMENTO.value
    assert runtime_fake.transcricoes == 1
    assert runtime_fake.modalidades == 1
    assert meta.downloads == 1
    assert len(meta.envios) == 2


def test_falha_incerta_no_outbound_para_em_handoff_sem_retry_automatico(
    monkeypatch,
) -> None:
    _engine, factory = _infra(monkeypatch)
    meta = MetaFake(falhar_envio=True)
    canal = RuntimeCanalWhatsAppV1(factory, runtime=RuntimeFake())
    mensagem = MensagemWhatsAppEntrada(
        mensagem_id="wamid-falha-outbound",
        remetente=TELEFONE,
        tipo="text",
        timestamp="1",
        texto="Quero um produto",
    )

    resultado = canal.processar_mensagem(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        mensagem=mensagem,
        adapter=meta,
    )

    assert resultado.handoff is True
    assert resultado.outbound_id is None
    assert len(meta.envios) == 1

    with factory() as session:
        estado = EncryptedSQLAlchemyChannelStateStore(session).obter(
            contexto=_contexto(
                correlation_id="wa:wamid-falha-outbound",
            ),
            canal="whatsapp",
            recipient=TELEFONE,
        )
        assert estado is not None
        assert estado.estado == EstadoAtendimento.HANDOFF_HUMANO.value
        assert estado.state is not None
        payload_resultado = estado.state["resultado"]
        assert isinstance(payload_resultado, dict)
        assert payload_resultado["estado"] == EstadoAtendimento.HANDOFF_HUMANO.value


def test_status_operacional_combina_pedido_pagamento_kds_e_entrega_reais(
    monkeypatch,
) -> None:
    _engine, factory = _infra(monkeypatch)
    with factory() as session:
        session.add(
            PedidoORM(
                id="pedido-status-f4f",
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                origem="whatsapp",
                canal="whatsapp",
                status="em_preparo",
                cliente_id=None,
                criado_em=AGORA,
                atualizado_em=AGORA,
                versao=3,
                correlation_id="corr-status",
                idempotency_key="pedido-status-f4f",
                request_hash="hash-pedido",
                subtotal=Decimal(25),
                descontos=Decimal(0),
                taxas=Decimal(8),
                total=Decimal(33),
            )
        )
        session.add(
            ObrigacaoPagamentoORM(
                id="pag-status-f4f",
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                pedido_id="pedido-status-f4f",
                comanda_id=None,
                valor_previsto=Decimal(33),
                moeda="BRL",
                criado_em=AGORA,
                versao=1,
                correlation_id="corr-status",
                idempotency_key="obrigacao-status-f4f",
                request_hash="hash-obrigacao",
            )
        )
        session.flush()
        session.add(
            PagamentoORM(
                id="pag-status-f4f",
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                pedido_id="pedido-status-f4f",
                comanda_id=None,
                status="pago",
                metodo="pix",
                valor_previsto=Decimal(33),
                valor_pago=Decimal(33),
                valor_estornado=Decimal(0),
                saldo=Decimal(0),
                moeda="BRL",
                recebimento_posterior=False,
                provedor="pagbank",
                criado_em=AGORA,
                atualizado_em=AGORA,
                versao=2,
                correlation_id="corr-status",
                idempotency_key="pag-status-f4f",
                request_hash="hash-pagamento",
            )
        )
        session.add(
            SetorProducaoORM(
                id="setor-f4f",
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                codigo="quente",
                nome="Cozinha quente",
                ordem=1,
                sla_segundos=900,
                ativo=True,
                criado_em=AGORA,
                atualizado_em=AGORA,
            )
        )
        session.flush()
        session.add(
            ProducaoItemORM(
                id="prod-status-f4f",
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                pedido_id="pedido-status-f4f",
                pedido_item_id="item-status-f4f",
                setor_id="setor-f4f",
                status="em_preparo",
                prioridade=0,
                quantidade=Decimal(1),
                tentativa=1,
                versao=2,
                criado_em=AGORA,
                atualizado_em=AGORA,
                aceita_em=AGORA,
                iniciada_em=AGORA,
                pausa_iniciada_em=None,
                pronta_em=None,
                retirada_em=None,
                responsavel_id=None,
                pausa_acumulada_segundos=0,
                idempotency_key="prod-status-f4f",
                request_hash="hash-producao",
            )
        )
        session.add(
            EntregaORM(
                id="entrega-status-f4f",
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                pedido_id="pedido-status-f4f",
                endereco_id="address://status-f4f",
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
        session.flush()
        session.add(
            EventoEntregaORM(
                event_id="evt-entrega-status-f4f",
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                entrega_id="entrega-status-f4f",
                pedido_id="pedido-status-f4f",
                tipo="entrega.criada",
                ator_id="assistente-delivery-convergence-v1",
                correlation_id="corr-status",
                causation_id=None,
                idempotency_key="evt-entrega-status-f4f",
                request_hash="hash-evento-entrega",
                ocorrido_em=AGORA,
                versao_entrega=1,
                payload_seguro={},
            )
        )
        session.commit()

    canal = RuntimeCanalWhatsAppV1(factory, runtime=RuntimeFake())
    with factory() as session:
        snapshot = canal.consultar_status(
            session=session,
            contexto=_contexto(correlation_id="corr-status"),
            pedido_id="pedido-status-f4f",
            pagamento_id="pag-status-f4f",
        )

    assert snapshot.pedido_status == "em_preparo"
    assert snapshot.pagamento_status == "pago"
    assert snapshot.producao_status == ("em_preparo",)
    assert snapshot.entrega_status == "aguardando_producao"
    assert snapshot.entrega_evento == "entrega.criada"


def test_notificador_envia_apenas_quando_snapshot_operacional_muda(
    monkeypatch,
) -> None:
    _engine, factory = _infra(monkeypatch)
    contexto = _contexto(correlation_id="corr-monitor-f4f")
    with factory() as session:
        session.add(
            PedidoORM(
                id="pedido-monitor-f4f",
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                origem="whatsapp",
                canal="whatsapp",
                status="confirmado",
                cliente_id=None,
                criado_em=AGORA,
                atualizado_em=AGORA,
                versao=2,
                correlation_id="corr-monitor-f4f",
                idempotency_key="pedido-monitor-f4f",
                request_hash="hash-monitor-pedido",
                subtotal=Decimal(25),
                descontos=Decimal(0),
                taxas=Decimal(0),
                total=Decimal(25),
            )
        )
        session.add(
            ObrigacaoPagamentoORM(
                id="pag-monitor-f4f",
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                pedido_id="pedido-monitor-f4f",
                comanda_id=None,
                valor_previsto=Decimal(25),
                moeda="BRL",
                criado_em=AGORA,
                versao=1,
                correlation_id="corr-monitor-f4f",
                idempotency_key="obrigacao-monitor-f4f",
                request_hash="hash-monitor-obrigacao",
            )
        )
        session.flush()
        session.add(
            PagamentoORM(
                id="pag-monitor-f4f",
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                pedido_id="pedido-monitor-f4f",
                comanda_id=None,
                status="pendente",
                metodo="pix",
                valor_previsto=Decimal(25),
                valor_pago=Decimal(0),
                valor_estornado=Decimal(0),
                saldo=Decimal(25),
                moeda="BRL",
                recebimento_posterior=False,
                provedor="pagbank",
                criado_em=AGORA,
                atualizado_em=AGORA,
                versao=1,
                correlation_id="corr-monitor-f4f",
                idempotency_key="pag-monitor-f4f",
                request_hash="hash-monitor-pagamento",
            )
        )
        EncryptedSQLAlchemyChannelStateStore(session).salvar(
            contexto=contexto,
            canal="whatsapp",
            recipient=TELEFONE,
            conversa_id="conv-monitor-f4f",
            estado=EstadoAtendimento.CHECKOUT_REGISTRADO.value,
            state=None,
            pedido_id="pedido-monitor-f4f",
            pagamento_id="pag-monitor-f4f",
            versao_esperada=0,
            agora=AGORA,
        )
        session.commit()

    meta = MetaFake()
    canal = RuntimeCanalWhatsAppV1(factory, runtime=RuntimeFake())

    assert canal.notificar_status_pedido(
        contexto=contexto,
        pedido_id="pedido-monitor-f4f",
        adapter=meta,
    ) == 1
    assert canal.notificar_status_pedido(
        contexto=contexto,
        pedido_id="pedido-monitor-f4f",
        adapter=meta,
    ) == 0
    assert len(meta.envios) == 1

    with factory() as session:
        pagamento = session.get(
            PagamentoORM,
            ("pag-monitor-f4f", TENANT, UNIDADE),
        )
        assert pagamento is not None
        pagamento.status = "pago"
        pagamento.valor_pago = Decimal(25)
        pagamento.saldo = Decimal(0)
        pagamento.versao = 2
        session.commit()

    assert canal.notificar_status_pedido(
        contexto=contexto,
        pedido_id="pedido-monitor-f4f",
        adapter=meta,
    ) == 1
    assert len(meta.envios) == 2
    assert "Pagamento: pago." in meta.envios[-1]["texto"]
