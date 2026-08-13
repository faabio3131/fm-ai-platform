import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from application.pagbank import (
    criar_pix_pagbank_em_transacao,
    processar_webhook_pagbank_em_transacao,
)
from core.dominio.dinheiro import Dinheiro
from core.dominio.enums import PagamentoStatus
from core.pagamentos.modelos import MetodoPagamento, TipoTransacao
from core.pagamentos.modelos_orm import PagamentoORM, TransacaoPagamentoORM
from core.pagamentos.pagbank import AdapterPagBank, ClientePagBank, ConfiguracaoPagBank
from core.pagamentos.servicos import criar_obrigacao_pagamento
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import MATRIZ_PADRAO, Papel
from infra.eventos.modelos_orm import OutboxEventoORM
from infra.seguranca.modelos_orm import EventoAuditoriaORM
from infra.transacoes.uow import UnitOfWorkV1
from migrations.runner import run_migrations

AGORA = datetime(2026, 8, 12, 22, tzinfo=timezone.utc)
TOKEN = "token-pagbank-teste"


class RespostaFake:
    status_code = 201

    def json(self):
        return {
            "id": "ORDE_PERSISTENTE_1",
            "qr_codes": [
                {
                    "amount": {"value": 3890},
                    "text": "PIX-COPIA-COLA",
                    "links": [],
                }
            ],
            "charges": [],
        }


class TransporteFake:
    def request(self, method, url, *, headers, json=None, timeout):
        del method, url, headers, json, timeout
        return RespostaFake()


def _factory():
    engine = create_engine("sqlite:///:memory:")
    run_migrations(engine)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)


def _contexto() -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id="tenant-pagbank",
        unidade_id="loja-pagbank",
        usuario_id="caixa-pagbank",
        papeis=frozenset({Papel.ADMINISTRADOR}),
        permissoes=MATRIZ_PADRAO[Papel.ADMINISTRADOR],
        correlation_id="corr-pagbank",
        solicitado_em=AGORA,
        origem="integration-test",
        unidades_permitidas=frozenset({"loja-pagbank"}),
    )


def _adapter() -> AdapterPagBank:
    return AdapterPagBank(
        ConfiguracaoPagBank(token=TOKEN, ambiente="sandbox"),
        transporte=TransporteFake(),
    )


def _cliente() -> ClientePagBank:
    return ClientePagBank(
        nome="Cliente PagBank",
        email="cliente@example.com",
        tax_id="12345678909",
    )


def _payload_pago() -> bytes:
    return json.dumps(
        {
            "id": "ORDE_PERSISTENTE_1",
            "charges": [
                {
                    "id": "CHAR_PERSISTENTE_1",
                    "status": "PAID",
                    "paid_at": "2026-08-12T22:10:00-03:00",
                    "amount": {"value": 3890, "currency": "BRL"},
                }
            ],
        },
        separators=(",", ":"),
    ).encode()


def test_order_pagbank_persistido_resolve_webhook_em_nova_sessao() -> None:
    engine, factory = _factory()
    contexto = _contexto()
    adapter = _adapter()

    with UnitOfWorkV1(factory) as uow:
        inicio = criar_obrigacao_pagamento(
            contexto=contexto,
            repositorio=uow.pagamentos,
            pagamento_id="pay-pagbank-1",
            pedido_id="pedido-pagbank-1",
            valor_previsto=Dinheiro("38.90"),
            metodo=MetodoPagamento.PIX,
            idempotency_key="obrigacao-pagbank-1",
            timestamp=AGORA,
            provedor="pagbank",
        )
        uow.registrar_efeitos(eventos=inicio.eventos, auditorias=inicio.auditorias)
        criado = criar_pix_pagbank_em_transacao(
            contexto=contexto,
            recursos=uow.recursos,  # mesma fronteira transacional da UoW
            adapter=adapter,
            pagamento_id="pay-pagbank-1",
            cliente=_cliente(),
            idempotency_key="criar-pix-1",
            timestamp=AGORA,
        )
        assert criado.order_id == "ORDE_PERSISTENTE_1"
        assert dict(criado.payload_exibicao)["pix_copia_cola"] == "PIX-COPIA-COLA"
        uow.commit()

    # A sessão da criação acabou; o vínculo precisa sobreviver no banco.
    with UnitOfWorkV1(factory) as uow:
        vinculo = uow.pagamentos.buscar_transacao_externa(
            "pagbank", "ORDE_PERSISTENTE_1", TipoTransacao.INICIACAO
        )
        assert vinculo is not None
        assert vinculo.pagamento_id == "pay-pagbank-1"
        assert vinculo.tenant_id == "tenant-pagbank"
        assert vinculo.unidade_id == "loja-pagbank"
        uow.rollback()

    bruto = _payload_pago()
    assinatura = hashlib.sha256(TOKEN.encode() + b"-" + bruto).hexdigest()
    with UnitOfWorkV1(factory) as uow:
        resultado = processar_webhook_pagbank_em_transacao(
            recursos=uow.recursos,
            adapter=adapter,
            payload_bruto=bruto,
            assinatura=assinatura,
        )
        assert resultado is not None
        assert resultado.pagamento.status is PagamentoStatus.PAGO
        uow.commit()

    with Session(engine) as session:
        pagamento = session.scalar(
            select(PagamentoORM).where(PagamentoORM.id == "pay-pagbank-1")
        )
        assert pagamento is not None and pagamento.status == "pago"
        assert (
            session.scalar(select(func.count()).select_from(TransacaoPagamentoORM)) == 3
        )
        assert session.scalar(select(func.count()).select_from(OutboxEventoORM)) == 3
        assert session.scalar(select(func.count()).select_from(EventoAuditoriaORM)) == 3


def test_assinatura_invalida_nao_resolve_nem_muda_pagamento() -> None:
    _, factory = _factory()
    contexto = _contexto()
    adapter = _adapter()
    with UnitOfWorkV1(factory) as uow:
        inicio = criar_obrigacao_pagamento(
            contexto=contexto,
            repositorio=uow.pagamentos,
            pagamento_id="pay-pagbank-2",
            pedido_id="pedido-pagbank-2",
            valor_previsto=Dinheiro("38.90"),
            metodo=MetodoPagamento.PIX,
            idempotency_key="obrigacao-pagbank-2",
            timestamp=AGORA,
            provedor="pagbank",
        )
        uow.registrar_efeitos(eventos=inicio.eventos, auditorias=inicio.auditorias)
        criar_pix_pagbank_em_transacao(
            contexto=contexto,
            recursos=uow.recursos,
            adapter=adapter,
            pagamento_id="pay-pagbank-2",
            cliente=_cliente(),
            idempotency_key="criar-pix-2",
            timestamp=AGORA,
        )
        uow.commit()

    with UnitOfWorkV1(factory) as uow:
        assert (
            processar_webhook_pagbank_em_transacao(
                recursos=uow.recursos,
                adapter=adapter,
                payload_bruto=_payload_pago(),
                assinatura="0" * 64,
            )
            is None
        )
        uow.commit()

    with UnitOfWorkV1(factory) as uow:
        pagamento = uow.pagamentos.buscar_pagamento(
            "tenant-pagbank", "loja-pagbank", "pay-pagbank-2"
        )
        assert pagamento is not None and pagamento.status is PagamentoStatus.PENDENTE
