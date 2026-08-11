from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from core.dominio.enums import PagamentoStatus
from core.pagamentos.modelos_orm import (
    ObrigacaoPagamentoORM,
    PagamentoORM,
    PaymentsBase,
)
from core.pedidos.modelos_orm import OrdersBase, PedidoORM
from core.salao import (
    ErroSalao,
    MetodoFechamento,
    RepositorioSalaoSQLAlchemy,
    SalaoBase,
    ServicoSalao,
    StatusComanda,
    StatusMesa,
)
from core.seguranca import MATRIZ_PADRAO, ContextoExecucao, Papel

AGORA = datetime(2026, 8, 11, 14, 0, tzinfo=UTC)
TENANT = "tenant-1"
UNIDADE = "unidade-1"


def contexto(papel: Papel = Papel.GERENTE) -> ContextoExecucao:
    return ContextoExecucao(
        TENANT,
        UNIDADE,
        f"ator-{papel.value}",
        frozenset({papel}),
        MATRIZ_PADRAO[papel],
        f"corr-{papel.value}",
        AGORA,
        "pytest-financeiro",
        unidades_permitidas=frozenset({UNIDADE}),
    )


def preparar() -> tuple[Session, ServicoSalao, ContextoExecucao]:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    OrdersBase.metadata.create_all(engine)
    PaymentsBase.metadata.create_all(engine)
    SalaoBase.metadata.create_all(engine)
    session = Session(engine)
    return session, ServicoSalao(RepositorioSalaoSQLAlchemy(session), agora=lambda: AGORA), contexto()


def criar_pedido(session: Session, pedido_id: str = "pedido-1", total: str = "10.00") -> None:
    valor = Decimal(total)
    session.add(
        PedidoORM(
            id=pedido_id,
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            origem="salao",
            canal="mesa",
            status="confirmado",
            cliente_id=None,
            criado_em=AGORA,
            atualizado_em=AGORA,
            versao=1,
            correlation_id=f"corr-{pedido_id}",
            idempotency_key=f"idem-{pedido_id}",
            request_hash=f"hash-{pedido_id}",
            subtotal=valor,
            descontos=Decimal("0.00"),
            taxas=Decimal("0.00"),
            total=valor,
        )
    )
    session.flush()


def criar_pagamento(
    session: Session,
    *,
    pagamento_id: str,
    comanda_id: str,
    metodo: str = "pix",
    valor: Decimal = Decimal("10.00"),
    status: str = PagamentoStatus.PAGO.value,
    comanda_financeira_id: str | None = None,
) -> None:
    comanda_financeira_id = comanda_id if comanda_financeira_id is None else comanda_financeira_id
    session.add(
        ObrigacaoPagamentoORM(
            id=pagamento_id,
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            pedido_id="pedido-1",
            comanda_id=comanda_financeira_id,
            valor_previsto=valor,
            moeda="BRL",
            criado_em=AGORA,
            versao=1,
            correlation_id=f"corr-{pagamento_id}",
            idempotency_key=f"obrigacao-{pagamento_id}",
            request_hash=f"hash-obrigacao-{pagamento_id}",
        )
    )
    session.flush()
    pago = valor if status == PagamentoStatus.PAGO.value else Decimal("0.00")
    session.add(
        PagamentoORM(
            id=pagamento_id,
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            pedido_id="pedido-1",
            comanda_id=comanda_financeira_id,
            status=status,
            metodo=metodo,
            valor_previsto=valor,
            valor_pago=pago,
            valor_estornado=Decimal("0.00"),
            saldo=Decimal("0.00") if status == PagamentoStatus.PAGO.value else valor,
            moeda="BRL",
            recebimento_posterior=False,
            provedor="pytest",
            criado_em=AGORA,
            atualizado_em=AGORA,
            versao=1,
            correlation_id=f"corr-{pagamento_id}",
            idempotency_key=f"pagamento-{pagamento_id}",
            request_hash=f"hash-pagamento-{pagamento_id}",
        )
    )
    session.flush()


def comanda_em_fechamento(
    session: Session, servico: ServicoSalao, ctx: ContextoExecucao
):
    mesa = servico.cadastrar_mesa(
        ctx,
        mesa_id="mesa-1",
        codigo="01",
        capacidade=4,
        idempotency_key="mesa:1",
    )
    criar_pedido(session)
    comanda = servico.abrir_comanda(
        ctx,
        comanda_id="cmd-1",
        numero="C1",
        mesa_id=mesa.mesa_id,
        expected_mesa_version=mesa.versao,
        idempotency_key="abrir:1",
    )
    comanda = servico.vincular_pedido(
        ctx,
        comanda_id=comanda.comanda_id,
        pedido_id="pedido-1",
        expected_version=comanda.versao,
        idempotency_key="vincular:1",
    )
    comanda = servico.solicitar_conta(
        ctx,
        comanda_id=comanda.comanda_id,
        expected_version=comanda.versao,
        idempotency_key="conta:1",
    )
    comanda, _ = servico.definir_divisao_pagamento(
        ctx,
        comanda_id=comanda.comanda_id,
        expected_version=comanda.versao,
        idempotency_key="divisao:1",
        divisoes=((MetodoFechamento.PIX, Decimal("10.00"), None),),
    )
    return comanda


def test_pagamento_precisa_existir_confirmado_no_dominio_financeiro() -> None:
    session, servico, ctx = preparar()
    with session.begin():
        comanda = comanda_em_fechamento(session, servico, ctx)
        with pytest.raises(ErroSalao) as erro:
            servico.registrar_pagamento_confirmado(
                ctx,
                comanda_id=comanda.comanda_id,
                pagamento_id="inexistente",
                metodo=MetodoFechamento.PIX,
                valor=Decimal("10.00"),
                expected_version=comanda.versao,
                idempotency_key="projetar:ausente",
            )
        assert erro.value.codigo == "pagamento_nao_confirmado"


def test_pagamento_pendente_ou_de_outra_comanda_e_rejeitado() -> None:
    session, servico, ctx = preparar()
    with session.begin():
        comanda = comanda_em_fechamento(session, servico, ctx)
        criar_pagamento(
            session,
            pagamento_id="pay-pendente",
            comanda_id=comanda.comanda_id,
            status=PagamentoStatus.PENDENTE.value,
        )
        with pytest.raises(ErroSalao) as erro:
            servico.registrar_pagamento_confirmado(
                ctx,
                comanda_id=comanda.comanda_id,
                pagamento_id="pay-pendente",
                metodo=MetodoFechamento.PIX,
                valor=Decimal("10.00"),
                expected_version=comanda.versao,
                idempotency_key="projetar:pendente",
            )
        assert erro.value.codigo == "pagamento_nao_confirmado"

        criar_pagamento(
            session,
            pagamento_id="pay-outra",
            comanda_id=comanda.comanda_id,
            comanda_financeira_id="cmd-outra",
        )
        with pytest.raises(ErroSalao) as erro:
            servico.registrar_pagamento_confirmado(
                ctx,
                comanda_id=comanda.comanda_id,
                pagamento_id="pay-outra",
                metodo=MetodoFechamento.PIX,
                valor=Decimal("10.00"),
                expected_version=comanda.versao,
                idempotency_key="projetar:outra",
            )
        assert erro.value.codigo == "pagamento_nao_pertence_comanda"


def test_metodo_valor_e_dupla_projecao_sao_protegidos() -> None:
    session, servico, ctx = preparar()
    with session.begin():
        comanda = comanda_em_fechamento(session, servico, ctx)
        criar_pagamento(
            session,
            pagamento_id="pay-1",
            comanda_id=comanda.comanda_id,
            metodo="dinheiro",
        )
        with pytest.raises(ErroSalao) as erro:
            servico.registrar_pagamento_confirmado(
                ctx,
                comanda_id=comanda.comanda_id,
                pagamento_id="pay-1",
                metodo=MetodoFechamento.PIX,
                valor=Decimal("10.00"),
                expected_version=comanda.versao,
                idempotency_key="projetar:metodo",
            )
        assert erro.value.codigo == "pagamento_metodo_divergente"

        criar_pagamento(
            session,
            pagamento_id="pay-2",
            comanda_id=comanda.comanda_id,
            metodo="pix",
            valor=Decimal("9.00"),
        )
        with pytest.raises(ErroSalao) as erro:
            servico.registrar_pagamento_confirmado(
                ctx,
                comanda_id=comanda.comanda_id,
                pagamento_id="pay-2",
                metodo=MetodoFechamento.PIX,
                valor=Decimal("10.00"),
                expected_version=comanda.versao,
                idempotency_key="projetar:valor",
            )
        assert erro.value.codigo == "pagamento_valor_divergente"

        criar_pagamento(
            session,
            pagamento_id="pay-3",
            comanda_id=comanda.comanda_id,
            metodo="pix",
        )
        comanda = servico.registrar_pagamento_confirmado(
            ctx,
            comanda_id=comanda.comanda_id,
            pagamento_id="pay-3",
            metodo=MetodoFechamento.PIX,
            valor=Decimal("10.00"),
            expected_version=comanda.versao,
            idempotency_key="projetar:ok",
        )
        assert comanda.saldo == Decimal("0.00")
        with pytest.raises(ErroSalao) as erro:
            servico.registrar_pagamento_confirmado(
                ctx,
                comanda_id=comanda.comanda_id,
                pagamento_id="pay-3",
                metodo=MetodoFechamento.PIX,
                valor=Decimal("10.00"),
                expected_version=comanda.versao,
                idempotency_key="projetar:duplicado",
            )
        assert erro.value.codigo in {"valor_pagamento_invalido", "pagamento_ja_projetado"}


def test_conta_pode_voltar_ao_consumo_e_cancelamento_e_idempotente() -> None:
    session, servico, ctx = preparar()
    with session.begin():
        mesa = servico.cadastrar_mesa(
            ctx,
            mesa_id="mesa-1",
            codigo="01",
            capacidade=4,
            idempotency_key="mesa:1",
        )
        comanda = servico.abrir_comanda(
            ctx,
            comanda_id="cmd-1",
            numero="C1",
            mesa_id=mesa.mesa_id,
            expected_mesa_version=mesa.versao,
            idempotency_key="abrir:1",
        )
        comanda = servico.solicitar_conta(
            ctx,
            comanda_id=comanda.comanda_id,
            expected_version=comanda.versao,
            idempotency_key="conta:1",
        )
        comanda = servico.retomar_consumo(
            ctx,
            comanda_id=comanda.comanda_id,
            expected_version=comanda.versao,
            idempotency_key="retomar:1",
        )
        assert comanda.status == StatusComanda.EM_CONSUMO
        cancelada = servico.cancelar_comanda(
            ctx,
            comanda_id=comanda.comanda_id,
            expected_version=comanda.versao,
            idempotency_key="cancelar:1",
            pedidos_resolvidos=True,
        )
        assert cancelada.status == StatusComanda.CANCELADA
        repetida = servico.cancelar_comanda(
            ctx,
            comanda_id=comanda.comanda_id,
            expected_version=comanda.versao,
            idempotency_key="cancelar:1",
            pedidos_resolvidos=True,
        )
        assert repetida.status == StatusComanda.CANCELADA
        mesa_final = servico.repositorio.obter_mesa(TENANT, UNIDADE, "mesa-1")
        assert mesa_final is not None and mesa_final.status == StatusMesa.LIVRE
