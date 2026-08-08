from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.dominio.dinheiro import Dinheiro
from core.dominio.enums import PagamentoStatus
from core.pagamentos.adaptador_sqlalchemy import RepositorioPagamentosSQLAlchemy
from core.pagamentos.erros import ConcorrenciaPagamento
from core.pagamentos.modelos import (
    CodigoCriterioFinanceiro,
    CriterioFinanceiro,
    MetodoPagamento,
    ObrigacaoPagamento,
    Pagamento,
    StatusTransacao,
    TipoTransacao,
    TransacaoPagamento,
    VendaFinanceira,
)
from core.pagamentos.modelos_orm import TransacaoPagamentoORM, VendaFinanceiraORM
from migrations.payments_v1 import upgrade

AGORA = datetime(2026, 8, 8, tzinfo=timezone.utc)


def dinheiro(valor: str) -> Dinheiro:
    return Dinheiro(Decimal(valor))


def obrigacao(identificador: str, valor: str) -> ObrigacaoPagamento:
    return ObrigacaoPagamento(
        identificador,
        "t",
        "u",
        f"pedido-{identificador}",
        dinheiro(valor),
        AGORA,
        1,
        "corr",
    )


def pagamento(identificador: str, valor: str) -> Pagamento:
    previsto = dinheiro(valor)
    return Pagamento(
        identificador,
        "t",
        "u",
        f"pedido-{identificador}",
        PagamentoStatus.PENDENTE,
        MetodoPagamento.PIX,
        previsto,
        dinheiro("0"),
        dinheiro("0"),
        previsto,
        "BRL",
        False,
        AGORA,
        AGORA,
        1,
        "corr",
        provedor="sandbox",
    )


def transacao(
    pagamento_id: str, valor: str, *, chave: str, externo: str
) -> TransacaoPagamento:
    return TransacaoPagamento(
        str(uuid4()),
        pagamento_id,
        "t",
        "u",
        TipoTransacao.CONFIRMACAO,
        StatusTransacao.CONFIRMADA,
        dinheiro(valor),
        MetodoPagamento.PIX,
        "sandbox",
        externo,
        chave,
        AGORA,
        AGORA,
        "corr",
        None,
    )


def criterio(p: Pagamento) -> CriterioFinanceiro:
    return CriterioFinanceiro(
        True,
        CodigoCriterioFinanceiro.PAGAMENTO_CONFIRMADO,
        "saldo resolvido",
        p.pedido_id,
        p.valor_previsto,
        "financeiro_v1",
        2,
        "ator",
        AGORA,
        "corr",
        p.id,
    )


def venda(p: Pagamento, chave: str = "venda") -> VendaFinanceira:
    return VendaFinanceira(
        str(uuid4()),
        "t",
        "u",
        p.pedido_id,
        p.id,
        None,
        CodigoCriterioFinanceiro.PAGAMENTO_CONFIRMADO,
        2,
        p.valor_previsto,
        MetodoPagamento.PIX,
        AGORA,
        "corr",
        chave,
    )


def test_roundtrip_sql_de_todos_agregados_e_decimais(tmp_path) -> None:
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'payments_roundtrip_test.db'}"
    )
    upgrade(engine)
    with Session(engine) as session:
        repo = RepositorioPagamentosSQLAlchemy(session)
        for numero, valor in enumerate(("0.01", "29.90", "999999.99"), 1):
            identificador = f"pay-{numero}"
            o = obrigacao(identificador, valor)
            p = pagamento(identificador, valor)
            repo.salvar_obrigacao(o, f"ob-{numero}", f"hash-ob-{numero}")
            repo.salvar_pagamento(p, 0)
            t = transacao(
                identificador, valor, chave=f"tx-{numero}", externo=f"ext-{numero}"
            )
            repo.append_transacao(t, f"hash-tx-{numero}")
            c = criterio(replace(p, versao=2))
            repo.salvar_criterio("t", "u", c, f"criterio-{numero}", f"hash-c-{numero}")
            v = venda(replace(p, versao=2), f"venda-{numero}")
            repo.salvar_venda(v, f"hash-v-{numero}")
        session.commit()

    with Session(engine) as session:
        repo = RepositorioPagamentosSQLAlchemy(session)
        for numero, valor in enumerate(("0.01", "29.90", "999999.99"), 1):
            identificador = f"pay-{numero}"
            esperado = Decimal(valor)
            obrigacao_salva = repo.buscar_obrigacao("t", "u", identificador)
            pagamento_salvo = repo.buscar_pagamento("t", "u", identificador)
            criterio_salvo = repo.buscar_criterio(
                "t", "u", f"pedido-{identificador}", 2
            )
            venda_salva = repo.buscar_venda_pedido(
                "t", "u", f"pedido-{identificador}", 2
            )
            assert obrigacao_salva and obrigacao_salva.valor_previsto.valor == esperado
            assert pagamento_salvo and pagamento_salvo.valor_previsto.valor == esperado
            assert (
                repo.listar_transacoes("t", "u", identificador)[0].valor.valor
                == esperado
            )
            assert (
                criterio_salvo and criterio_salvo.valor_reconhecivel.valor == esperado
            )
            assert venda_salva and venda_salva.valor.valor == esperado
            assert repo.buscar_pagamento("outro", "u", identificador) is None
            assert repo.buscar_pagamento("t", "outra", identificador) is None


def test_cas_pagamentos_parciais_impede_ultrapassar_obrigacao(tmp_path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'payments_cas_test.db'}")
    upgrade(engine)
    with Session(engine) as session:
        repo = RepositorioPagamentosSQLAlchemy(session)
        repo.salvar_obrigacao(obrigacao("pay", "100"), "ob", "h-ob")
        repo.salvar_pagamento(pagamento("pay", "100"), 0)
        session.commit()
    s1, s2 = Session(engine), Session(engine)
    try:
        r1, r2 = (
            RepositorioPagamentosSQLAlchemy(s1),
            RepositorioPagamentosSQLAlchemy(s2),
        )
        p1 = r1.buscar_pagamento("t", "u", "pay")
        p2 = r2.buscar_pagamento("t", "u", "pay")
        assert p1 and p2
        r1.salvar_pagamento(
            replace(
                p1,
                status=PagamentoStatus.PARCIALMENTE_PAGO,
                valor_pago=dinheiro("60"),
                saldo=dinheiro("40"),
                versao=2,
            ),
            1,
        )
        s1.commit()
        with pytest.raises(ConcorrenciaPagamento, match="compare_and_swap"):
            r2.salvar_pagamento(
                replace(
                    p2,
                    status=PagamentoStatus.PARCIALMENTE_PAGO,
                    valor_pago=dinheiro("50"),
                    saldo=dinheiro("50"),
                    versao=2,
                ),
                1,
            )
        s2.rollback()
    finally:
        s1.close()
        s2.close()
    with Session(engine) as session:
        final = RepositorioPagamentosSQLAlchemy(session).buscar_pagamento(
            "t", "u", "pay"
        )
        assert (
            final
            and final.valor_pago == dinheiro("60")
            and final.saldo == dinheiro("40")
        )


def test_constraints_exatamente_uma_venda_e_uma_confirmacao_externa(tmp_path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'payments_unique_test.db'}")
    upgrade(engine)
    p = pagamento("pay", "29.90")
    with Session(engine) as session:
        repo = RepositorioPagamentosSQLAlchemy(session)
        repo.salvar_obrigacao(obrigacao("pay", "29.90"), "ob", "h-ob")
        repo.salvar_pagamento(p, 0)
        session.commit()
    with Session(engine) as worker1:
        RepositorioPagamentosSQLAlchemy(worker1).salvar_venda(
            venda(replace(p, versao=2), "v1"), "mesmo-conteudo"
        )
        worker1.commit()
    with Session(engine) as worker2:
        with pytest.raises(Exception, match="venda_equivalente_existente"):
            RepositorioPagamentosSQLAlchemy(worker2).salvar_venda(
                venda(replace(p, versao=2), "v2"), "mesmo-conteudo"
            )
        worker2.rollback()
    with Session(engine) as worker1:
        RepositorioPagamentosSQLAlchemy(worker1).append_transacao(
            transacao("pay", "29.90", chave="webhook-1", externo="pix-unico"),
            "hash-evento",
        )
        worker1.commit()
    with Session(engine) as worker2:
        with pytest.raises(IntegrityError):
            RepositorioPagamentosSQLAlchemy(worker2).append_transacao(
                transacao("pay", "29.90", chave="webhook-2", externo="pix-unico"),
                "hash-evento",
            )
        worker2.rollback()
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(VendaFinanceiraORM)) == 1
        assert (
            session.scalar(select(func.count()).select_from(TransacaoPagamentoORM)) == 1
        )
