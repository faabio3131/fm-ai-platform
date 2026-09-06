from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, insert
from sqlalchemy.orm import sessionmaker

from application.crm_marketing_comercial import despachar_resgate_whatsapp_legado
from core.seguranca.contexto import ContextoExecucao
from infra.crm.cliente_legado_schema import crm_cliente_legado_v1
from infra.crm.consentimentos_schema import crm_consentimentos_v1
from infra.legacy_schema import clientes
from migrations.crm_cliente_legado_mapping_v1 import (
    upgrade_crm_cliente_legado_mapping_v1,
)
from migrations.crm_clientes_persistencia_v1 import upgrade_crm_clientes_persistencia_v1
from migrations.crm_consentimentos_historico_v1 import (
    upgrade_crm_consentimentos_historico_v1,
)

TENANT = "tenant-f13c-marketing"
UNIDADE = "unidade-f13c-marketing"
CLIENTE = "cliente-f13c-marketing"
LEGACY_ID = 92
AGORA = datetime(2026, 9, 6, 1, 30, tzinfo=timezone.utc)
PROVA = "a" * 64


class EnvioCaptura:
    def __init__(self) -> None:
        self.chamadas: list[tuple[str, str, str]] = []
        self.mensagem_id = "teste-msg-1"

    def enviar(
        self,
        *,
        referencia_contato: str,
        campanha_ref: str,
        idempotency_key: str,
    ) -> None:
        self.chamadas.append(
            (referencia_contato, campanha_ref, idempotency_key)
        )


def _contexto() -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        usuario_id="operador-f13c",
        papeis=frozenset(),
        permissoes=frozenset(),
        correlation_id="corr-f13c-marketing",
        solicitado_em=AGORA,
        origem="teste-f13c",
        unidades_permitidas=frozenset({UNIDADE}),
    )


def _fabrica():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys = ON")
        clientes.create(connection, checkfirst=True)
        upgrade_crm_clientes_persistencia_v1(connection)
        upgrade_crm_cliente_legado_mapping_v1(connection)
        upgrade_crm_consentimentos_historico_v1(connection)
        connection.execute(
            insert(clientes).values(
                id=LEGACY_ID,
                nome="Cliente Marketing",
                whatsapp="5511999990002",
                total_gasto=0.0,
                saldo_cashback=0.0,
                status="Ativo",
            )
        )
        connection.exec_driver_sql(
            """
            INSERT INTO crm_clientes_v1
                (tenant_id, unidade_id, cliente_id, origem, marketplace_origem,
                 criado_em, versao)
            VALUES (?, ?, ?, 'manual', NULL, ?, 1)
            """,
            (TENANT, UNIDADE, CLIENTE, AGORA.replace(tzinfo=None)),
        )
        connection.exec_driver_sql(
            """
            INSERT INTO crm_cliente_contatos_v1
                (tenant_id, unidade_id, cliente_id, canal, referencia)
            VALUES (?, ?, ?, 'whatsapp', 'contact://f13c-marketing')
            """,
            (TENANT, UNIDADE, CLIENTE),
        )
        connection.execute(
            insert(crm_cliente_legado_v1).values(
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                legacy_cliente_id=LEGACY_ID,
                cliente_id=CLIENTE,
                criado_por="teste-f13c",
                correlation_id="corr-f13c-marketing",
                criado_em=AGORA,
            )
        )
    return engine, sessionmaker(bind=engine, future=True)


def _consentir(engine, *, status: str, instante: datetime, chave: str) -> None:
    with engine.begin() as connection:
        concedido = status == "concedido"
        connection.execute(
            insert(crm_consentimentos_v1).values(
                consentimento_id=f"cons-{chave}",
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                cliente_id=CLIENTE,
                canal="whatsapp",
                finalidade="promocoes",
                status=status,
                base_legal="consentimento",
                texto_versao="marketing-v1",
                origem="teste",
                prova_hash=PROVA,
                ocorrido_em=instante,
                idempotency_key=f"idem-{chave}",
                correlation_id=f"corr-{chave}",
                concedido_em=instante if concedido else None,
                revogado_em=None if concedido else instante,
            )
        )


def test_sem_consentimento_nega_e_nao_chama_transporte() -> None:
    _, fabrica = _fabrica()
    envio = EnvioCaptura()
    resultado = despachar_resgate_whatsapp_legado(
        session_factory=fabrica,
        contexto=_contexto(),
        legacy_cliente_id=LEGACY_ID,
        campanha_ref="resgate-f13c",
        texto="Volte para aproveitar sua oferta.",
        idempotency_key="envio-f13c-1",
        envio=envio,
    )
    assert not resultado.enviado
    assert resultado.motivo == "marketing_sem_consentimento"
    assert envio.chamadas == []


def test_consentimento_vigente_autoriza_referencia_segura() -> None:
    engine, fabrica = _fabrica()
    _consentir(engine, status="concedido", instante=AGORA, chave="grant")
    envio = EnvioCaptura()
    resultado = despachar_resgate_whatsapp_legado(
        session_factory=fabrica,
        contexto=_contexto(),
        legacy_cliente_id=LEGACY_ID,
        campanha_ref="resgate-f13c",
        texto="Volte para aproveitar sua oferta.",
        idempotency_key="envio-f13c-2",
        envio=envio,
    )
    assert resultado.enviado
    assert resultado.motivo == "enviado"
    assert resultado.mensagem_id == "teste-msg-1"
    assert envio.chamadas == [
        ("contact://f13c-marketing", "resgate-f13c", "envio-f13c-2")
    ]


def test_revogacao_mais_recente_bloqueia_envio() -> None:
    engine, fabrica = _fabrica()
    _consentir(engine, status="concedido", instante=AGORA, chave="grant")
    _consentir(
        engine,
        status="revogado",
        instante=AGORA + timedelta(minutes=1),
        chave="revoke",
    )
    envio = EnvioCaptura()
    resultado = despachar_resgate_whatsapp_legado(
        session_factory=fabrica,
        contexto=_contexto(),
        legacy_cliente_id=LEGACY_ID,
        campanha_ref="resgate-f13c",
        texto="Volte para aproveitar sua oferta.",
        idempotency_key="envio-f13c-3",
        envio=envio,
    )
    assert not resultado.enviado
    assert resultado.motivo == "marketing_sem_consentimento"
    assert envio.chamadas == []
