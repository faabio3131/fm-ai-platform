from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, insert
from sqlalchemy.orm import sessionmaker

import application.crm_marketing_comercial as marketing
from application.crm_marketing_comercial import (
    despachar_resgate_cliente_inativo,
    despachar_resgate_whatsapp_legado,
    preparar_resgates_clientes_inativos,
)
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


def _adicionar_cliente(
    engine,
    *,
    legacy_id: int,
    cliente_id: str,
    tenant_id: str = TENANT,
    unidade_id: str = UNIDADE,
    ultima_compra: datetime,
    status: str = "Ativo",
) -> None:
    with engine.begin() as connection:
        connection.execute(
            insert(clientes).values(
                id=legacy_id,
                nome=f"Cliente {legacy_id}",
                whatsapp=f"551199999{legacy_id:04d}",
                ultima_compra=ultima_compra,
                total_gasto=150.0,
                saldo_cashback=0.0,
                status=status,
            )
        )
        connection.exec_driver_sql(
            """
            INSERT INTO crm_clientes_v1
                (tenant_id, unidade_id, cliente_id, origem, marketplace_origem,
                 criado_em, versao)
            VALUES (?, ?, ?, 'manual', NULL, ?, 1)
            """,
            (tenant_id, unidade_id, cliente_id, AGORA.replace(tzinfo=None)),
        )
        connection.execute(
            insert(crm_cliente_legado_v1).values(
                tenant_id=tenant_id,
                unidade_id=unidade_id,
                legacy_cliente_id=legacy_id,
                cliente_id=cliente_id,
                criado_por="teste-wp017",
                correlation_id=f"corr-{legacy_id}",
                criado_em=AGORA,
            )
        )


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


def test_resgate_preserva_corte_or_prompt_e_escopo(monkeypatch) -> None:
    engine, fabrica = _fabrica()
    agora = datetime(2026, 9, 9, 12, 0)  # noqa: DTZ001

    class DataHoraFixa(datetime):
        @classmethod
        def now(cls, tz=None):
            return agora

    monkeypatch.setattr(marketing, "datetime", DataHoraFixa)
    _adicionar_cliente(
        engine,
        legacy_id=101,
        cliente_id="cliente-corte",
        ultima_compra=agora - timedelta(days=15),
    )
    _adicionar_cliente(
        engine,
        legacy_id=102,
        cliente_id="cliente-recente-inativo",
        ultima_compra=agora - timedelta(days=2),
        status="Inativo",
    )
    _adicionar_cliente(
        engine,
        legacy_id=103,
        cliente_id="cliente-recente-ativo",
        ultima_compra=agora - timedelta(days=14),
    )
    _adicionar_cliente(
        engine,
        legacy_id=104,
        cliente_id="cliente-outra-unidade",
        unidade_id="unidade-fora-wp017",
        ultima_compra=agora - timedelta(days=30),
    )
    prompts: list[str] = []

    def gerar(*, contents: str):
        prompts.append(contents)
        return SimpleNamespace(text="  Mensagem Gemini preservada.  ")

    oportunidades = preparar_resgates_clientes_inativos(
        session_factory=fabrica,
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        genai_disponivel=True,
        generate_content=gerar,
    )

    assert [item.legacy_cliente_id for item in oportunidades] == [101, 102]
    assert [item.mensagem_sugerida for item in oportunidades] == [
        "Mensagem Gemini preservada.",
        "Mensagem Gemini preservada.",
    ]
    assert prompts == [
        (
            "Escreva uma mensagem curta, carinhosa e persuasiva de WhatsApp para "
            "resgatar o cliente 'Cliente 101'. Ofereça 15% de desconto com o cupom "
            "VOLTA15. Sem clichês em excesso."
        ),
        (
            "Escreva uma mensagem curta, carinhosa e persuasiva de WhatsApp para "
            "resgatar o cliente 'Cliente 102'. Ofereça 15% de desconto com o cupom "
            "VOLTA15. Sem clichês em excesso."
        ),
    ]


@pytest.mark.parametrize(
    "gerar",
    [
        lambda **_: SimpleNamespace(text=""),
        lambda **_: SimpleNamespace(text=None),
        lambda **_: (_ for _ in ()).throw(RuntimeError("Gemini indisponível")),
    ],
)
def test_resgate_preserva_fallback_para_resposta_invalida_ou_excecao(
    monkeypatch,
    gerar,
) -> None:
    engine, fabrica = _fabrica()
    agora = datetime(2026, 9, 9, 12, 0)  # noqa: DTZ001

    class DataHoraFixa(datetime):
        @classmethod
        def now(cls, tz=None):
            return agora

    monkeypatch.setattr(marketing, "datetime", DataHoraFixa)
    _adicionar_cliente(
        engine,
        legacy_id=105,
        cliente_id="cliente-fallback",
        ultima_compra=agora - timedelta(days=20),
    )

    oportunidade = preparar_resgates_clientes_inativos(
        session_factory=fabrica,
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        genai_disponivel=True,
        generate_content=gerar,
    )[0]

    assert oportunidade.mensagem_sugerida == (
        "Olá Cliente 105! Sentimos sua falta. Preparamos um cupom exclusivo de "
        "15% de desconto para você voltar hoje!"
    )


def test_resgate_sem_gemini_usa_mensagem_padrao_sem_chamar_provider() -> None:
    engine, fabrica = _fabrica()
    _adicionar_cliente(
        engine,
        legacy_id=106,
        cliente_id="cliente-sem-gemini",
        ultima_compra=datetime.now() - timedelta(days=20),  # noqa: DTZ005
    )

    def nao_deve_chamar(**_):
        raise AssertionError("provider não deveria ser chamado")

    oportunidade = preparar_resgates_clientes_inativos(
        session_factory=fabrica,
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        genai_disponivel=False,
        generate_content=nao_deve_chamar,
    )[0]

    assert oportunidade.mensagem_sugerida == (
        "Olá Cliente 106! Sentimos sua falta. Preparamos um cupom exclusivo de "
        "15% de desconto para você voltar hoje!"
    )


def test_despacho_resgate_preserva_campanha_e_idempotencia_diarias(
    monkeypatch,
) -> None:
    engine, fabrica = _fabrica()
    _consentir(engine, status="concedido", instante=AGORA, chave="daily")
    envio = EnvioCaptura()

    class DataFixa(date):
        @classmethod
        def today(cls):
            return cls(2026, 9, 9)

    monkeypatch.setattr(marketing, "date", DataFixa)
    resultado = despachar_resgate_cliente_inativo(
        session_factory=fabrica,
        contexto=_contexto(),
        legacy_cliente_id=LEGACY_ID,
        texto="Mensagem preservada.",
        envio=envio,
    )

    assert resultado.enviado
    assert envio.chamadas == [
        (
            "contact://f13c-marketing",
            "resgate-2026-09-09",
            f"crm-resgate-{LEGACY_ID}-2026-09-09",
        )
    ]
