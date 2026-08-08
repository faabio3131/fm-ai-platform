from datetime import datetime, timezone
from decimal import Decimal

from core.dominio.decisoes import DecisaoCozinha
from core.dominio.dinheiro import Dinheiro
from core.dominio.enums import (
    CodigoDecisaoCozinha,
    PagamentoStatus,
    PapelUsuario,
    RiscoPedido,
)
from core.estados.maquinas import ComandoTransicao, SnapshotEstado, transicionar
from core.estoque.modelos import ItemSnapshotFicha, SnapshotFichaEstoque, TipoMovimento
from core.estoque.repositorios import RepositorioEstoqueEmMemoria
from core.estoque.servicos import (
    consumir_reserva,
    registrar_movimento,
    reservar_estoque,
)
from core.pagamentos import (
    AdapterVendaLegada,
    MetodoPagamento,
    RepositorioPagamentosEmMemoria,
    avaliar_criterio_financeiro,
    confirmar_pagamento,
    criar_obrigacao_pagamento,
    reconhecer_venda,
)
from core.seguranca import ContextoExecucao, Permissao
from core.seguranca.permissoes import Papel
from tests.unit.orders.factories import pedido

AGORA = datetime(2026, 8, 8, tzinfo=timezone.utc)


def contexto() -> ContextoExecucao:
    return ContextoExecucao(
        "tenant-a",
        "unidade-a",
        "operador-gate-a",
        frozenset({Papel.GERENTE}),
        frozenset(Permissao),
        "corr-gate-a",
        AGORA,
        "teste_integrado",
        unidades_permitidas=frozenset({"unidade-a"}),
    )


def avancar(
    snapshot: SnapshotEstado, destino: str, chave: str, **precondicoes: bool
) -> SnapshotEstado:
    decisao = None
    if destino == "enviado_producao":
        decisao = DecisaoCozinha(
            permitido=True,
            codigo_decisao=CodigoDecisaoCozinha.PERMITIDO_PAGAMENTO_POSTERIOR,
            justificativa="politica permite producao antes do pagamento",
            confirmacao_exigida=False,
            risco=RiscoPedido.BAIXO,
            politica_aplicada="gate_a",
            versao_politica="v1",
            decidido_em=AGORA,
            papel_responsavel_exigido=PapelUsuario.GERENTE,
        )
    return transicionar(
        snapshot,
        ComandoTransicao(
            destino,
            snapshot.version,
            chave,
            AGORA,
            contexto(),
            precondicoes=precondicoes,
            decisao_cozinha=decisao,
        ),
    ).snapshot


def test_gate_a_fluxo_real_prova_zero_dupla_baixa_e_zero_dupla_venda() -> None:
    contrato_pedido = pedido()
    assert contrato_pedido.total == Dinheiro(Decimal("24.00"))
    estado = SnapshotEstado(
        "pedido", str(contrato_pedido.id), "tenant-a", "unidade-a", "rascunho", 1
    )
    estado = avancar(
        estado,
        "aguardando_confirmacao",
        "estado-1",
        itens_validos=True,
        precos_calculados=True,
    )
    estado = avancar(estado, "confirmado", "estado-2", dados_confirmados=True)

    estoque = RepositorioEstoqueEmMemoria()
    registrar_movimento(
        contexto=contexto(),
        repositorio=estoque,
        insumo_id="farinha",
        tipo=TipoMovimento.ENTRADA,
        quantidade_movimento="10",
        unidade_medida="kg",
        origem_tipo="inventario",
        origem_id="saldo-inicial",
        origem_versao=1,
        idempotency_key="entrada-gate",
        motivo="saldo de teste",
    )
    ficha = SnapshotFichaEstoque(
        str(contrato_pedido.id),
        "ficha-v3",
        AGORA,
        (
            ItemSnapshotFicha(
                "produto", "item-1", "farinha", Decimal("2"), Decimal("2"), "kg"
            ),
        ),
    )
    reservar_estoque(
        contexto=contexto(),
        repositorio=estoque,
        pedido_id=str(contrato_pedido.id),
        pedido_version=estado.version,
        snapshot_ficha=ficha,
        idempotency_key="reserva-gate",
    )
    estado = avancar(estado, "enviado_producao", "estado-3", itens_roteados=True)
    estado = avancar(estado, "em_preparo", "estado-4", producao_iniciada=True)
    consumir_reserva(
        contexto=contexto(),
        repositorio=estoque,
        pedido_id=str(contrato_pedido.id),
        pedido_version=estado.version,
        idempotency_key="consumo-gate",
    )
    antes_financeiro = estoque.listar_movimentos("tenant-a", "unidade-a", "farinha")

    financeiro = RepositorioPagamentosEmMemoria()
    criar_obrigacao_pagamento(
        contexto=contexto(),
        repositorio=financeiro,
        pagamento_id="pay-gate",
        pedido_id=str(contrato_pedido.id),
        valor_previsto=contrato_pedido.total,
        metodo=MetodoPagamento.PIX,
        idempotency_key="obrigacao-gate",
        timestamp=AGORA,
    )
    confirmado = confirmar_pagamento(
        contexto=contexto(),
        repositorio=financeiro,
        pagamento_id="pay-gate",
        valor=contrato_pedido.total,
        metodo=MetodoPagamento.PIX,
        idempotency_key="confirmacao-gate",
        expected_version=1,
        timestamp=AGORA,
        referencia_externa="pix-gate",
    )
    assert confirmado.pagamento.status == PagamentoStatus.PAGO
    criterio = avaliar_criterio_financeiro(
        contexto=contexto(),
        pagamento=confirmado.pagamento,
        pedido_id=str(contrato_pedido.id),
        timestamp=AGORA,
    )
    primeira = reconhecer_venda(
        contexto=contexto(),
        repositorio=financeiro,
        criterio=criterio,
        metodo=MetodoPagamento.PIX,
        idempotency_key="venda-gate",
        timestamp=AGORA,
    )
    repetida = reconhecer_venda(
        contexto=contexto(),
        repositorio=financeiro,
        criterio=criterio,
        metodo=MetodoPagamento.PIX,
        idempotency_key="venda-gate",
        timestamp=AGORA,
    )
    confirmacao_repetida = confirmar_pagamento(
        contexto=contexto(),
        repositorio=financeiro,
        pagamento_id="pay-gate",
        valor=contrato_pedido.total,
        metodo=MetodoPagamento.PIX,
        idempotency_key="confirmacao-gate",
        expected_version=2,
        timestamp=AGORA,
        referencia_externa="pix-gate",
    )
    antes_adapter = estoque.listar_movimentos("tenant-a", "unidade-a", "farinha")
    AdapterVendaLegada().materializar(primeira.venda, produto_id=1)
    depois_financeiro = estoque.listar_movimentos("tenant-a", "unidade-a", "farinha")

    assert repetida.idempotente and confirmacao_repetida.idempotente
    assert antes_financeiro == antes_adapter == depois_financeiro
    assert (
        sum(m.tipo_movimento == TipoMovimento.RESERVA for m in depois_financeiro) == 1
    )
    assert (
        sum(m.tipo_movimento == TipoMovimento.CONSUMO for m in depois_financeiro) == 1
    )
    assert len(financeiro.listar_vendas("tenant-a", "unidade-a")) == 1
    assert (
        len(
            [
                t
                for t in financeiro.listar_transacoes(
                    "tenant-a", "unidade-a", "pay-gate"
                )
                if t.tipo.value == "confirmacao"
            ]
        )
        == 1
    )
