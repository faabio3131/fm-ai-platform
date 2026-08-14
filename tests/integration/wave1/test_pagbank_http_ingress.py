import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.dominio.dinheiro import Dinheiro
from core.pagamentos.modelos import (
    MetodoPagamento,
    StatusTransacao,
    TipoTransacao,
    TransacaoPagamento,
)
from core.pagamentos.servicos import criar_obrigacao_pagamento
from core.runtime.config import RuntimeEnvironment, RuntimeSettings
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import MATRIZ_PADRAO, Papel
from core.seguranca.segredos import ReferenceSecretStore
from http_api.app import build_http_app
from infra.pagamentos.pagbank_runtime import PagBankAdapterFactory, PagBankRuntimeConfig
from infra.seguranca.modelos_orm import CredencialReferenciaORM
from infra.transacoes.uow import UnitOfWorkV1
from migrations.runner import run_migrations

AGORA = datetime(2026, 8, 12, 23, tzinfo=timezone.utc)
TOKEN = "token-pagbank-http-teste"
ORDER_ID = "ORDE_HTTP_PERSISTENTE_1"
PAGAMENTO_ID = "pay-http-pagbank-1"
TENANT = "tenant-http"
UNIDADE = "unidade-http"


def _infra():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    run_migrations(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    settings = RuntimeSettings(
        RuntimeEnvironment.TEST,
        "sqlite://",
        TENANT,
        UNIDADE,
    )
    return engine, factory, settings


def _contexto() -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        usuario_id="admin-http",
        papeis=frozenset({Papel.ADMINISTRADOR}),
        permissoes=MATRIZ_PADRAO[Papel.ADMINISTRADOR],
        correlation_id="corr-http",
        solicitado_em=AGORA,
        origem="integration-test",
        unidades_permitidas=frozenset({UNIDADE}),
    )


def _seed(factory, *, com_credencial: bool = True) -> None:
    contexto = _contexto()
    with UnitOfWorkV1(factory) as uow:
        inicio = criar_obrigacao_pagamento(
            contexto=contexto,
            repositorio=uow.pagamentos,
            pagamento_id=PAGAMENTO_ID,
            pedido_id="pedido-http-pagbank-1",
            valor_previsto=Dinheiro("38.90"),
            metodo=MetodoPagamento.PIX,
            idempotency_key="obrigacao-http-pagbank-1",
            timestamp=AGORA,
            provedor="pagbank",
        )
        uow.registrar_efeitos(eventos=inicio.eventos, auditorias=inicio.auditorias)
        uow.pagamentos.append_transacao(
            TransacaoPagamento(
                str(uuid4()),
                PAGAMENTO_ID,
                TENANT,
                UNIDADE,
                TipoTransacao.INICIACAO,
                StatusTransacao.PENDENTE,
                Dinheiro(0),
                MetodoPagamento.PIX,
                "pagbank",
                ORDER_ID,
                "pagbank:http:order-1",
                AGORA,
                AGORA,
                contexto.correlation_id,
                None,
                (("order_status", "pendente"),),
            ),
            "fingerprint-http-order-1",
        )
        if com_credencial:
            uow.recursos.session.add(
                CredencialReferenciaORM(
                    tenant_id=TENANT,
                    unidade_id=UNIDADE,
                    provedor="pagbank",
                    finalidade="api_token",
                    referencia="mapping:PAGBANK_HTTP_TOKEN",
                    versao=1,
                    ativa=True,
                    rotacionada_por="admin-http",
                    correlation_id="corr-http-credencial",
                    criada_em=AGORA,
                )
            )
        uow.commit()


def _payload(order_id: str = ORDER_ID) -> bytes:
    return json.dumps(
        {
            "id": order_id,
            "charges": [
                {
                    "id": "CHAR_HTTP_1",
                    "status": "PAID",
                    "paid_at": "2026-08-12T23:05:00-03:00",
                    "amount": {"value": 3890, "currency": "BRL"},
                    "payment_method": {"type": "PIX"},
                }
            ],
        },
        separators=(",", ":"),
    ).encode()


def _client(*, com_credencial: bool = True):
    engine, factory, settings = _infra()
    _seed(factory, com_credencial=com_credencial)
    pagbank_factory = PagBankAdapterFactory(
        secret_store=ReferenceSecretStore(mapping={"PAGBANK_HTTP_TOKEN": TOKEN}),
        config=PagBankRuntimeConfig(ambiente="sandbox"),
    )
    app = build_http_app(
        settings=settings,
        engine=engine,
        session_factory=factory,
        pagbank_factory=pagbank_factory,
    )
    return TestClient(app), factory


def _assinatura(payload: bytes) -> str:
    return hashlib.sha256(TOKEN.encode() + b"-" + payload).hexdigest()


def _status_pagamento(factory) -> str:
    with UnitOfWorkV1(factory) as uow:
        pagamento = uow.pagamentos.buscar_pagamento(TENANT, UNIDADE, PAGAMENTO_ID)
        assert pagamento is not None
        return pagamento.status.value


def test_webhook_http_valido_resolve_escopo_e_confirma_pagamento() -> None:
    client, factory = _client()
    payload = _payload()
    resposta = client.post(
        "/webhooks/pagbank",
        content=payload,
        headers={"x-authenticity-token": _assinatura(payload)},
    )
    assert resposta.status_code == 204
    assert _status_pagamento(factory) == "pago"


def test_webhook_http_assinatura_invalida_e_descartado() -> None:
    client, factory = _client()
    resposta = client.post(
        "/webhooks/pagbank",
        content=_payload(),
        headers={"x-authenticity-token": "0" * 64},
    )
    assert resposta.status_code == 204
    assert _status_pagamento(factory) == "pendente"


def test_webhook_http_sem_assinatura_e_descartado() -> None:
    client, factory = _client()
    assert client.post("/webhooks/pagbank", content=_payload()).status_code == 204
    assert _status_pagamento(factory) == "pendente"


def test_webhook_http_order_desconhecida_nao_expoe_existencia() -> None:
    client, factory = _client()
    payload = _payload("ORDE_DESCONHECIDA")
    resposta = client.post(
        "/webhooks/pagbank",
        content=payload,
        headers={"x-authenticity-token": _assinatura(payload)},
    )
    assert resposta.status_code == 204
    assert _status_pagamento(factory) == "pendente"


def test_webhook_http_credencial_operacional_ausente_retorna_503() -> None:
    client, factory = _client(com_credencial=False)
    payload = _payload()
    resposta = client.post(
        "/webhooks/pagbank",
        content=payload,
        headers={"x-authenticity-token": _assinatura(payload)},
    )
    assert resposta.status_code == 503
    assert _status_pagamento(factory) == "pendente"


def test_webhook_http_limita_payload() -> None:
    client, _ = _client()
    resposta = client.post(
        "/webhooks/pagbank",
        content=b"x" * (1024 * 1024 + 1),
        headers={"x-authenticity-token": "0" * 64},
    )
    assert resposta.status_code == 413


def test_healthz_do_ingresso_http() -> None:
    client, _ = _client()
    resposta = client.get("/healthz")
    assert resposta.status_code == 200
    assert resposta.json()["ok"] is True
