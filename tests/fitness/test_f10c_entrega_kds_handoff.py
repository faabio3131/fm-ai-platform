from __future__ import annotations

import inspect

from application import kds_transacoes
from core.entrega.adaptador_sqlalchemy import RepositorioEntregaSQLAlchemy


def test_handoff_entrega_ocorre_depois_do_commit_kds() -> None:
    source = inspect.getsource(kds_transacoes.transicionar_kds_v1)
    assert source.index("uow.commit()") < source.index(
        "_notificar_entrega_pedido_pronto_best_effort"
    )


def test_falha_handoff_nao_propaga_para_kds_autoritativo() -> None:
    source = inspect.getsource(
        kds_transacoes._notificar_entrega_pedido_pronto_best_effort
    )
    assert "PedidoStatus.PRONTO" in source
    assert "except Exception" in source
    assert "logger.exception" in source
    assert "HandoffEntregaKDSV1" in source


def test_repositorio_entrega_nao_assume_commit() -> None:
    source = inspect.getsource(RepositorioEntregaSQLAlchemy)
    assert ".commit(" not in source
