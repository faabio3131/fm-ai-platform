from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from core.pagamentos.modelos_orm import PaymentsBase
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Papel, Permissao
from infra.integracoes.pix_durabilidade import (
    recuperar_pix_aberto_por_terminal,
    recuperar_vinculo_cobranca_pix,
    registrar_vinculo_cobranca_pix,
)


def _contexto(*, tenant: str = "tenant-a", unidade: str = "loja-1") -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id=tenant,
        unidade_id=unidade,
        usuario_id="admin-1",
        papeis=frozenset({Papel.ADMINISTRADOR}),
        permissoes=frozenset(Permissao),
        correlation_id=f"corr-{tenant}-{unidade}",
        solicitado_em=datetime.now(timezone.utc),
        origem="tests.pix-durabilidade",
        unidades_permitidas=frozenset({unidade}),
    )


def test_vinculo_pix_sobrevive_a_nova_sessao_de_banco() -> None:
    engine = create_engine("sqlite:///:memory:")
    PaymentsBase.metadata.create_all(engine)
    contexto = _contexto()
    instante = datetime(2026, 8, 18, 14, 30, tzinfo=timezone.utc)

    with Session(engine) as session:
        salva = registrar_vinculo_cobranca_pix(
            session=session,
            contexto=contexto,
            pagamento_id="pdv-checkout-1",
            pedido_id="checkout-1",
            valor=Decimal("49.90"),
            provedor="pagbank",
            id_externo="charge-123",
            idempotency_key="pdv-pix-checkout-1:charge",
            timestamp=instante,
        )
        assert salva.id_externo == "charge-123"
        assert salva.provedor == "pagbank"

    with Session(engine) as nova_session:
        recuperada = recuperar_vinculo_cobranca_pix(
            session=nova_session,
            contexto=contexto,
            pagamento_id="pdv-checkout-1",
        )
        assert recuperada is not None
        assert recuperada.id_externo == "charge-123"
        assert recuperada.provedor == "pagbank"
        assert recuperada.valor.valor == Decimal("49.90")


def test_vinculo_pix_e_idempotente_e_isolado_por_tenant_unidade() -> None:
    engine = create_engine("sqlite:///:memory:")
    PaymentsBase.metadata.create_all(engine)
    contexto = _contexto()
    instante = datetime(2026, 8, 18, 14, 35, tzinfo=timezone.utc)

    with Session(engine) as session:
        primeira = registrar_vinculo_cobranca_pix(
            session=session,
            contexto=contexto,
            pagamento_id="pdv-checkout-2",
            pedido_id="checkout-2",
            valor=Decimal("25.00"),
            provedor="mercado_pago",
            id_externo="mp-456",
            idempotency_key="pdv-pix-checkout-2:charge",
            timestamp=instante,
        )
        repetida = registrar_vinculo_cobranca_pix(
            session=session,
            contexto=contexto,
            pagamento_id="pdv-checkout-2",
            pedido_id="checkout-2",
            valor=Decimal("25.00"),
            provedor="mercado_pago",
            id_externo="mp-456",
            idempotency_key="pdv-pix-checkout-2:charge",
            timestamp=instante,
        )
        assert repetida.transacao_id == primeira.transacao_id

        assert recuperar_vinculo_cobranca_pix(
            session=session,
            contexto=_contexto(tenant="tenant-b", unidade="loja-1"),
            pagamento_id="pdv-checkout-2",
        ) is None
        assert recuperar_vinculo_cobranca_pix(
            session=session,
            contexto=_contexto(tenant="tenant-a", unidade="loja-2"),
            pagamento_id="pdv-checkout-2",
        ) is None


def test_pix_aberto_e_recuperado_apos_perda_total_do_session_state() -> None:
    engine = create_engine("sqlite:///:memory:")
    PaymentsBase.metadata.create_all(engine)
    contexto = _contexto()

    with Session(engine) as session:
        registrar_vinculo_cobranca_pix(
            session=session,
            contexto=contexto,
            pagamento_id="pdv-checkout-persistido",
            pedido_id="checkout-persistido",
            valor=Decimal("79.90"),
            provedor="pagbank",
            id_externo="charge-persistida",
            idempotency_key="pdv-pix-checkout-persistido:charge",
            terminal_id="caixa-01",
            assinatura_checkout="produto-7:qtd-2:cliente-3:79.90",
        )

    # Nova sessão não conhece checkout_id nem qualquer estado do navegador.
    with Session(engine) as nova_session:
        recuperado = recuperar_pix_aberto_por_terminal(
            session=nova_session,
            contexto=contexto,
            terminal_id="caixa-01",
            assinatura_checkout="produto-7:qtd-2:cliente-3:79.90",
        )
        assert recuperado is not None
        assert recuperado.pagamento_id == "pdv-checkout-persistido"
        assert recuperado.id_externo == "charge-persistida"
        assert recuperado.provedor == "pagbank"
        assert recuperado.valor == Decimal("79.90")


def test_recuperacao_por_terminal_nao_cruza_caixa_carrinho_tenant_ou_unidade() -> None:
    engine = create_engine("sqlite:///:memory:")
    PaymentsBase.metadata.create_all(engine)
    contexto = _contexto()

    with Session(engine) as session:
        registrar_vinculo_cobranca_pix(
            session=session,
            contexto=contexto,
            pagamento_id="pdv-checkout-isolado",
            pedido_id="checkout-isolado",
            valor=Decimal("18.00"),
            provedor="mercado_pago",
            id_externo="mp-isolado",
            idempotency_key="pdv-pix-checkout-isolado:charge",
            terminal_id="caixa-02",
            assinatura_checkout="produto-1:qtd-1:cliente-8:18.00",
        )

        assert recuperar_pix_aberto_por_terminal(
            session=session,
            contexto=contexto,
            terminal_id="caixa-99",
            assinatura_checkout="produto-1:qtd-1:cliente-8:18.00",
        ) is None
        assert recuperar_pix_aberto_por_terminal(
            session=session,
            contexto=contexto,
            terminal_id="caixa-02",
            assinatura_checkout="outro-carrinho",
        ) is None
        assert recuperar_pix_aberto_por_terminal(
            session=session,
            contexto=_contexto(tenant="tenant-b"),
            terminal_id="caixa-02",
            assinatura_checkout="produto-1:qtd-1:cliente-8:18.00",
        ) is None
        assert recuperar_pix_aberto_por_terminal(
            session=session,
            contexto=_contexto(unidade="loja-2"),
            terminal_id="caixa-02",
            assinatura_checkout="produto-1:qtd-1:cliente-8:18.00",
        ) is None
