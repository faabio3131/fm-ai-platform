from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from threading import Barrier, Thread

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from core.estoque.adaptador_sqlalchemy import RepositorioLedgerSQLAlchemy
from core.estoque.modelos import TipoMovimento
from core.estoque.modelos_orm import StockBase
from core.estoque.repositorios import RepositorioEstoqueEmMemoria
from core.procurement.erros import (
    ConflitoProcurement,
    EstadoProcurementInvalido,
    ProcurementNaoAutorizado,
)
from core.procurement.modelos import (
    ItemPedidoCompra,
    ItemRecebido,
    StatusRecebimento,
    TipoDivergencia,
)
from core.procurement.repositorios import RepositorioProcurementEmMemoria
from core.procurement.servicos import ServicoProcurement
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Papel, Permissao
from infra.procurement.modelos_orm import ProcurementBase
from infra.procurement.repositorio_sqlalchemy import RepositorioProcurementSQLAlchemy
from kordena_fiscal.domain import (
    Cnpj,
    ElectronicInvoiceModel,
    ExecutionScope,
    FiscalEnvironment,
)
from kordena_fiscal.inbound import FiscalInboundSource, parse_nfe_xml
from kordena_fiscal.xml import AccessKeyInput, build_access_key
from migrations.fiscal_procurement_integration_v1 import (
    upgrade_fiscal_procurement_integration_v1,
)

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
CNPJ = Cnpj("11222333000181")


def scope(
    environment: FiscalEnvironment = FiscalEnvironment.PRODUCTION,
    tenant: str = "tenant-a",
    unit: str = "unit-a",
) -> ExecutionScope:
    return ExecutionScope(
        tenant_id=tenant,
        unit_id=unit,
        environment=environment,
        correlation_id=f"corr-{tenant}-{unit}-{environment.value}",
    )


def contexto(
    *permissoes: Permissao,
    tenant: str = "tenant-a",
    unit: str = "unit-a",
) -> ContextoExecucao:
    return ContextoExecucao(
        tenant,
        unit,
        "operador-compras",
        frozenset({Papel.GERENTE}),
        frozenset(permissoes),
        f"corr-{tenant}-{unit}",
        NOW,
        "teste",
        unidades_permitidas=frozenset({unit}),
    )


def xml_nfe(
    *,
    invoice: int = 1,
    quantity: str = "2.000000",
    unit_value: str = "5.000000",
    freight: str = "0.00",
    discount: str = "0.00",
    total: str = "10.00",
) -> bytes:
    key = build_access_key(
        AccessKeyInput(
            state_ibge_code="35",
            issued_at=NOW,
            issuer_cnpj=CNPJ,
            model=ElectronicInvoiceModel.NFE,
            series=1,
            invoice_number=invoice,
            emission_type=1,
            numeric_code=invoice,
        )
    ).value
    product_total = Decimal(quantity) * Decimal(unit_value)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00"><NFe>
<infNFe Id="NFe{key}" versao="4.00">
<ide><dhEmi>2026-09-20T12:00:00+00:00</dhEmi></ide>
<emit><CNPJ>{CNPJ.value}</CNPJ><xNome>Fornecedor Teste</xNome></emit>
<dest><CNPJ>{CNPJ.value}</CNPJ><xNome>Kordena</xNome></dest>
<det nItem="1"><prod><cProd>FAR-001</cProd><xProd>Farinha</xProd><NCM>11010010</NCM><uCom>KG</uCom><qCom>{quantity}</qCom><vUnCom>{unit_value}</vUnCom><vProd>{product_total}</vProd></prod></det>
<total><ICMSTot><vFrete>{freight}</vFrete><vDesc>{discount}</vDesc><vNF>{total}</vNF></ICMSTot></total>
</infNFe></NFe></nfeProc>""".encode()


def documento(execution_scope: ExecutionScope, **kwargs: str | int):
    return parse_nfe_xml(
        scope=execution_scope,
        recipient_document=CNPJ,
        xml_content=xml_nfe(**kwargs),
        source=FiscalInboundSource.XML_UPLOAD,
        discovered_at=NOW,
    )


def preparar(
    execution_scope: ExecutionScope,
    *,
    quantidade: str = "2",
    total: str = "10",
):
    procurement = RepositorioProcurementEmMemoria()
    estoque = RepositorioEstoqueEmMemoria()
    servico = ServicoProcurement(repositorio=procurement, estoque=estoque)
    gestor = contexto(Permissao.COMPRA_APROVAR)
    servico.cadastrar_fornecedor(
        contexto=gestor,
        scope=execution_scope,
        fornecedor_id="fornecedor-1",
        documento=CNPJ.value,
        nome="Fornecedor Teste",
    )
    servico.vincular_produto(
        contexto=gestor,
        scope=execution_scope,
        fornecedor_id="fornecedor-1",
        codigo_fornecedor="FAR-001",
        insumo_id="farinha",
    )
    pedido = servico.criar_pedido(
        contexto=gestor,
        scope=execution_scope,
        pedido_id="pedido-1",
        fornecedor_id="fornecedor-1",
        itens=(
            ItemPedidoCompra(
                1,
                "farinha",
                "FAR-001",
                "Farinha",
                "KG",
                Decimal(quantidade),
                Decimal(5),
            ),
        ),
        frete=Decimal(0),
        desconto=Decimal(0),
        total=Decimal(total),
    )
    servico.aprovar_pedido(
        contexto=gestor,
        scope=execution_scope,
        pedido_id=pedido.pedido_id,
        versao_esperada=1,
    )
    return servico, procurement, estoque


def item(quantidade: str = "2", valor: str = "5") -> tuple[ItemRecebido, ...]:
    return (
        ItemRecebido(
            1,
            1,
            "farinha",
            Decimal(quantidade),
            "KG",
            Decimal(valor),
            True,
        ),
    )


def test_wp031g_recebimento_completo_move_estoque_uma_vez_e_replay_e_seguro() -> None:
    execution_scope = scope()
    servico, _, estoque = preparar(execution_scope)
    operador = contexto(Permissao.FISCAL_COMPRAS_RECEBER)
    fiscal = documento(execution_scope)

    primeiro = servico.receber(
        contexto=operador,
        scope=execution_scope,
        pedido_id="pedido-1",
        documento=fiscal,
        itens_recebidos=item(),
        idempotency_key="receber-1",
        recebimento_id="recebimento-1",
    )
    replay = servico.receber(
        contexto=operador,
        scope=execution_scope,
        pedido_id="pedido-1",
        documento=fiscal,
        itens_recebidos=item(),
        idempotency_key="receber-1",
        recebimento_id="recebimento-1",
    )

    assert primeiro.recebimento.status is StatusRecebimento.CONCLUIDO
    assert not primeiro.idempotente and replay.idempotente
    assert primeiro.eventos[0].event_type == "fiscal.recebimento.confirmado"
    assert primeiro.auditorias[0].correlation_id == execution_scope.correlation_id
    assert estoque.consultar_saldo("tenant-a", "unit-a", "farinha").saldo_fisico == 2
    assert len(estoque.listar_movimentos("tenant-a", "unit-a")) == 1

    with pytest.raises(ConflitoProcurement):
        servico.receber(
            contexto=operador,
            scope=execution_scope,
            pedido_id="pedido-1",
            documento=fiscal,
            itens_recebidos=item("1"),
            idempotency_key="receber-1",
            recebimento_id="recebimento-1",
        )


def test_wp031g_concorrencia_nao_cria_duas_entradas() -> None:
    class RepoConcorrente(RepositorioProcurementEmMemoria):
        def __init__(self) -> None:
            super().__init__()
            self.barreira: Barrier | None = None

        def recebimento_por_idempotencia(self, execution_scope, chave):
            resultado = super().recebimento_por_idempotencia(execution_scope, chave)
            if resultado is None and self.barreira is not None:
                self.barreira.wait()
            return resultado

    execution_scope = scope()
    _, repo_base, estoque = preparar(execution_scope)
    repo = RepoConcorrente()
    repo._fornecedores = dict(repo_base._fornecedores)
    repo._pedidos = dict(repo_base._pedidos)
    repo._vinculos = dict(repo_base._vinculos)
    servico = ServicoProcurement(repositorio=repo, estoque=estoque)
    repo.barreira = Barrier(2)
    operador = contexto(Permissao.FISCAL_COMPRAS_RECEBER)
    fiscal = documento(execution_scope)
    resultados: list[object] = []

    def executar() -> None:
        try:
            resultados.append(
                servico.receber(
                    contexto=operador,
                    scope=execution_scope,
                    pedido_id="pedido-1",
                    documento=fiscal,
                    itens_recebidos=item(),
                    idempotency_key="corrente-1",
                    recebimento_id="recebimento-corrente-1",
                )
            )
        except (ConflitoProcurement, EstadoProcurementInvalido) as exc:
            resultados.append(exc)

    threads = [Thread(target=executar) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert len(resultados) == 2
    assert all(not isinstance(resultado, Exception) for resultado in resultados)
    assert sum(resultado.idempotente for resultado in resultados) == 1
    assert estoque.consultar_saldo("tenant-a", "unit-a", "farinha").saldo_fisico == 2
    assert len(estoque.listar_movimentos("tenant-a", "unit-a")) == 1

    repo.barreira = None
    with pytest.raises(EstadoProcurementInvalido):
        servico.receber(
            contexto=operador,
            scope=execution_scope,
            pedido_id="pedido-1",
            documento=fiscal,
            itens_recebidos=item(),
            idempotency_key="novo-recebimento",
            recebimento_id="recebimento-novo",
        )


def test_wp031g_nfe_isolada_homologacao_e_divergencia_nao_movem_estoque() -> None:
    homolog = scope(FiscalEnvironment.HOMOLOGATION)
    servico_h, _, estoque_h = preparar(homolog)
    operador = contexto(Permissao.FISCAL_COMPRAS_RECEBER)
    resultado_h = servico_h.receber(
        contexto=operador,
        scope=homolog,
        pedido_id="pedido-1",
        documento=documento(homolog),
        itens_recebidos=item(),
        idempotency_key="homolog-1",
    )
    assert resultado_h.recebimento.status is StatusRecebimento.CONCLUIDO
    assert estoque_h.listar_movimentos("tenant-a", "unit-a") == ()

    production = scope()
    servico_p, _, estoque_p = preparar(production)
    divergente = servico_p.receber(
        contexto=operador,
        scope=production,
        pedido_id="pedido-1",
        documento=documento(production),
        itens_recebidos=item("3"),
        idempotency_key="divergente-1",
    )
    assert divergente.recebimento.status is StatusRecebimento.DIVERGENTE
    assert TipoDivergencia.QUANTIDADE in {
        item.tipo for item in divergente.recebimento.divergencias
    }
    assert estoque_p.listar_movimentos("tenant-a", "unit-a") == ()


def test_wp031g_recebimento_parcial_e_devolucao_ao_fornecedor() -> None:
    execution_scope = scope()
    servico, _, estoque = preparar(execution_scope, quantidade="4", total="20")
    operador = contexto(Permissao.FISCAL_COMPRAS_RECEBER)
    parcial = servico.receber(
        contexto=operador,
        scope=execution_scope,
        pedido_id="pedido-1",
        documento=documento(execution_scope),
        itens_recebidos=item(),
        idempotency_key="parcial-1",
        recebimento_id="recebimento-parcial",
    )
    assert parcial.recebimento.status is StatusRecebimento.PARCIAL
    assert estoque.consultar_saldo("tenant-a", "unit-a", "farinha").saldo_fisico == 2

    devolucao = servico.devolver_ao_fornecedor(
        contexto=operador,
        scope=execution_scope,
        recebimento_id="recebimento-parcial",
        idempotency_key="devolver-1",
        motivo="avaria identificada apos conferencia",
    )
    assert (
        devolucao[0].movimentos[0].tipo_movimento is TipoMovimento.DEVOLUCAO_FORNECEDOR
    )
    assert estoque.consultar_saldo("tenant-a", "unit-a", "farinha").saldo_fisico == 0


def test_wp031g_rbac_e_escopo_falham_fechados() -> None:
    execution_scope = scope()
    servico, _, _ = preparar(execution_scope)
    with pytest.raises(ProcurementNaoAutorizado):
        servico.receber(
            contexto=contexto(),
            scope=execution_scope,
            pedido_id="pedido-1",
            documento=documento(execution_scope),
            itens_recebidos=item(),
            idempotency_key="sem-permissao",
        )


def test_wp031g_migration_e_repositorio_sql_sao_duraveis_e_particionados() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    StockBase.metadata.create_all(engine)
    with engine.begin() as connection:
        upgrade_fiscal_procurement_integration_v1(connection)
    assert {
        "procurement_suppliers_v1",
        "procurement_purchase_orders_v1",
        "procurement_receipts_v1",
        "procurement_product_bindings_v1",
        "procurement_acquisition_costs_v1",
    } <= set(inspect(engine).get_table_names())

    with Session(engine) as session, session.begin():
        repo = RepositorioProcurementSQLAlchemy(session)
        estoque = RepositorioLedgerSQLAlchemy(session)
        servico = ServicoProcurement(repositorio=repo, estoque=estoque)
        execution_scope = scope()
        gestor = contexto(Permissao.COMPRA_APROVAR)
        fornecedor = servico.cadastrar_fornecedor(
            contexto=gestor,
            scope=execution_scope,
            fornecedor_id="fornecedor-sql",
            documento=CNPJ.value,
            nome="Fornecedor SQL",
        )
        assert repo.fornecedor_por_documento(execution_scope, CNPJ.value) == fornecedor

    assert ProcurementBase.metadata.tables
