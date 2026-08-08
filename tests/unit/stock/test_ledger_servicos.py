from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from decimal import Decimal
from threading import Barrier, Thread

import pytest

from core.estoque.erros import (
    OperacaoEstoqueNaoAutorizada,
    ReservaInvalida,
    SaldoInsuficiente,
)
from core.estoque.modelos import (
    ItemSnapshotFicha,
    SnapshotFichaEstoque,
    TipoMovimento,
)
from core.estoque.repositorios import RepositorioEstoqueEmMemoria
from core.estoque.servicos import (
    consumir_reserva,
    liberar_reserva,
    registrar_devolucao,
    registrar_movimento,
    reservar_estoque,
)
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Papel, Permissao

AGORA = datetime(2026, 1, 1, tzinfo=timezone.utc)


def ctx(
    *permissoes: Permissao,
    tenant: str = "t",
    unidade: str = "u",
    papel: Papel = Papel.GERENTE,
) -> ContextoExecucao:
    return ContextoExecucao(
        tenant,
        unidade,
        "ator",
        frozenset({papel}),
        frozenset(permissoes),
        "corr",
        AGORA,
        "teste",
        unidades_permitidas=frozenset({unidade}),
    )


def sistema() -> ContextoExecucao:
    return ContextoExecucao.sistema(
        identidade="pedidos",
        motivo="reservar pedido",
        tenant_id="t",
        unidade_id="u",
        correlation_id="corr",
        solicitado_em=AGORA,
    )


def snapshot(versao: str = "v1", total: str = "2") -> SnapshotFichaEstoque:
    return SnapshotFichaEstoque(
        "p1",
        versao,
        AGORA,
        (
            ItemSnapshotFicha(
                "produto", "item", "farinha", Decimal("1"), Decimal(total), "kg"
            ),
        ),
    )


def entrada(repo: RepositorioEstoqueEmMemoria, total: str = "10") -> None:
    registrar_movimento(
        contexto=ctx(Permissao.ESTOQUE_AJUSTAR),
        repositorio=repo,
        insumo_id="farinha",
        tipo=TipoMovimento.ENTRADA,
        quantidade_movimento=total,
        unidade_medida="kg",
        origem_tipo="inventario",
        origem_id="inicial",
        origem_versao=1,
        idempotency_key="entrada",
        motivo="carga teste",
    )


def test_ledger_saldo_reserva_consumo_e_idempotencia() -> None:
    repo = RepositorioEstoqueEmMemoria()
    entrada(repo)
    reservado = reservar_estoque(
        contexto=sistema(),
        repositorio=repo,
        pedido_id="p1",
        pedido_version=1,
        snapshot_ficha=snapshot(),
        idempotency_key="reservar",
    )
    assert reservado.saldos[0].saldo_fisico == 10
    assert reservado.saldos[0].saldo_reservado == 2
    assert reservado.saldos[0].saldo_disponivel == 8
    repetido = reservar_estoque(
        contexto=sistema(),
        repositorio=repo,
        pedido_id="p1",
        pedido_version=1,
        snapshot_ficha=snapshot(),
        idempotency_key="reservar",
    )
    assert (
        repetido.idempotente and len(repo.listar_movimentos("t", "u", "farinha")) == 2
    )
    baixado = consumir_reserva(
        contexto=sistema(),
        repositorio=repo,
        pedido_id="p1",
        pedido_version=2,
        idempotency_key="consumir",
    )
    assert (
        baixado.saldos[0].saldo_fisico == 8 and baixado.saldos[0].saldo_reservado == 0
    )
    assert consumir_reserva(
        contexto=sistema(),
        repositorio=repo,
        pedido_id="p1",
        pedido_version=2,
        idempotency_key="consumir",
    ).idempotente
    assert [e.event_type for e in baixado.eventos] == ["estoque.baixado"]
    assert baixado.auditorias[0].correlation_id == "corr"


def test_cancelamento_antes_producao_libera_sem_apagar_historico() -> None:
    repo = RepositorioEstoqueEmMemoria()
    entrada(repo)
    reservar_estoque(
        contexto=sistema(),
        repositorio=repo,
        pedido_id="p1",
        pedido_version=1,
        snapshot_ficha=snapshot(),
        idempotency_key="r",
    )
    resultado = liberar_reserva(
        contexto=sistema(),
        repositorio=repo,
        pedido_id="p1",
        pedido_version=2,
        idempotency_key="l",
        motivo="cancelamento",
    )
    tipos = [m.tipo_movimento for m in repo.listar_movimentos("t", "u", "farinha")]
    assert tipos == [
        TipoMovimento.ENTRADA,
        TipoMovimento.RESERVA,
        TipoMovimento.LIBERACAO_RESERVA,
    ]
    assert (
        resultado.saldos[0].saldo_fisico == 10
        and resultado.saldos[0].saldo_reservado == 0
    )


def test_snapshot_v1_permanece_apos_ficha_atual_mudar() -> None:
    repo = RepositorioEstoqueEmMemoria()
    entrada(repo)
    resultado = reservar_estoque(
        contexto=sistema(),
        repositorio=repo,
        pedido_id="p1",
        pedido_version=1,
        snapshot_ficha=snapshot("v1", "2"),
        idempotency_key="r",
    )
    ficha_atual = snapshot("v2", "5")
    assert ficha_atual.versao_ficha == "v2"
    assert (
        resultado.reserva is not None
        and resultado.reserva.snapshot.versao_ficha == "v1"
    )
    assert resultado.reserva.snapshot.itens[0].quantidade_total == 2


def test_movimento_e_escopo_sao_imutaveis_e_consultas_isoladas() -> None:
    repo = RepositorioEstoqueEmMemoria()
    entrada(repo)
    movimento = repo.listar_movimentos("t", "u", "farinha")[0]
    with pytest.raises(FrozenInstanceError):
        movimento.tenant_id = "outro"  # type: ignore[misc]
    assert repo.listar_movimentos("outro", "u", "farinha") == ()
    assert repo.listar_movimentos("t", "outra", "farinha") == ()
    assert not hasattr(repo, "delete") and not hasattr(repo, "update")


def test_perda_ajuste_devolucao_e_compensacao_exigem_regras() -> None:
    repo = RepositorioEstoqueEmMemoria()
    entrada(repo)
    gerente = ctx(
        Permissao.ESTOQUE_PERDA_REGISTRAR,
        Permissao.ESTOQUE_AJUSTAR,
        Permissao.ESTOQUE_DEVOLVER,
    )
    perda = registrar_movimento(
        contexto=gerente,
        repositorio=repo,
        insumo_id="farinha",
        tipo=TipoMovimento.PERDA,
        quantidade_movimento="1",
        unidade_medida="kg",
        origem_tipo="producao",
        origem_id="x",
        origem_versao=1,
        idempotency_key="perda",
        motivo="quebra",
    )
    assert perda.eventos[0].event_type == "estoque.perda_registrada"
    with pytest.raises(ReservaInvalida):
        registrar_devolucao(
            elegivel=False,
            inspecionada=True,
            politica_permite=True,
            contexto=gerente,
            repositorio=repo,
            insumo_id="farinha",
            quantidade_movimento="1",
            unidade_medida="kg",
            origem_tipo="devolucao",
            origem_id="x",
            origem_versao=1,
            idempotency_key="dev",
            motivo="retorno",
        )
    devolucao = registrar_devolucao(
        elegivel=True,
        inspecionada=True,
        politica_permite=True,
        contexto=gerente,
        repositorio=repo,
        insumo_id="farinha",
        quantidade_movimento="1",
        unidade_medida="kg",
        origem_tipo="devolucao",
        origem_id="x",
        origem_versao=1,
        idempotency_key="dev",
        motivo="inspecionado",
    )
    assert devolucao.eventos[0].event_type == "estoque.devolvido"
    compensacao = registrar_movimento(
        contexto=gerente,
        repositorio=repo,
        insumo_id="farinha",
        tipo=TipoMovimento.COMPENSACAO,
        quantidade_movimento="1",
        unidade_medida="kg",
        origem_tipo="movimento",
        origem_id=perda.movimentos[0].movimento_id,
        origem_versao=1,
        idempotency_key="comp",
        motivo="corrigir perda",
        metadata={
            "direcao": "positivo",
            "movimento_original_id": perda.movimentos[0].movimento_id,
        },
    )
    assert (
        compensacao.movimentos[0].metadata["movimento_original_id"]
        == perda.movimentos[0].movimento_id
    )


def test_saldo_nao_fica_negativo_e_gerente_ia_nao_confirma() -> None:
    repo = RepositorioEstoqueEmMemoria()
    entrada(repo, "1")
    with pytest.raises(SaldoInsuficiente):
        reservar_estoque(
            contexto=sistema(),
            repositorio=repo,
            pedido_id="p1",
            pedido_version=1,
            snapshot_ficha=snapshot(total="2"),
            idempotency_key="r",
        )
    ia = ctx(Permissao.ESTOQUE_AJUSTAR, papel=Papel.GERENTE_IA)
    with pytest.raises(OperacaoEstoqueNaoAutorizada):
        registrar_movimento(
            contexto=ia,
            repositorio=repo,
            insumo_id="farinha",
            tipo=TipoMovimento.AJUSTE_NEGATIVO,
            quantidade_movimento="1",
            unidade_medida="kg",
            origem_tipo="ajuste",
            origem_id="x",
            origem_versao=1,
            idempotency_key="ia",
            motivo="solicitacao",
        )


def test_corrida_real_em_memoria_nao_sobre_reserva() -> None:
    repo = RepositorioEstoqueEmMemoria()
    entrada(repo)
    barreira = Barrier(3)
    resultados: list[str] = []

    def tentar(pedido: str) -> None:
        barreira.wait()
        try:
            ficha = SnapshotFichaEstoque(
                pedido,
                "v1",
                AGORA,
                (
                    ItemSnapshotFicha(
                        "produto", pedido, "farinha", Decimal("7"), Decimal("7"), "kg"
                    ),
                ),
            )
            reservar_estoque(
                contexto=sistema(),
                repositorio=repo,
                pedido_id=pedido,
                pedido_version=1,
                snapshot_ficha=ficha,
                idempotency_key=f"r-{pedido}",
            )
            resultados.append("ok")
        except SaldoInsuficiente:
            resultados.append("insuficiente")

    threads = [Thread(target=tentar, args=(p,)) for p in ("a", "b")]
    for thread in threads:
        thread.start()
    barreira.wait()
    for thread in threads:
        thread.join()
    assert sorted(resultados) == ["insuficiente", "ok"]
    assert repo.consultar_saldo("t", "u", "farinha").saldo_reservado == 7
