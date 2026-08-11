from datetime import datetime, timezone

import pytest

from core.entrega import (
    ChecklistExpedicao,
    Entrega,
    ErroEntrega,
    ModalidadeEntrega,
    ProvaEntrega,
    StatusEntrega,
    TentativaEntrega,
)


AGORA = datetime(2026, 8, 11, 15, 0, tzinfo=timezone.utc)


def test_checklist_so_fica_completo_com_todos_os_itens():
    incompleto = ChecklistExpedicao(True, True, False)
    completo = ChecklistExpedicao(True, True, True)

    assert incompleto.completo is False
    assert completo.completo is True


def test_prova_e_tentativa_exigem_dados_minimos():
    prova = ProvaEntrega("proof://pedido-1", "confirmacao", AGORA)
    tentativa = TentativaEntrega(1, "cliente ausente", AGORA)

    assert prova.referencia == "proof://pedido-1"
    assert tentativa.numero == 1


def test_entrega_valida_escopo_e_versao():
    entrega = Entrega(
        entrega_id="entrega-1",
        tenant_id="tenant-1",
        unidade_id="unidade-1",
        pedido_id="pedido-1",
        endereco_id="endereco-1",
        modalidade=ModalidadeEntrega.PROPRIA,
        status=StatusEntrega.AGUARDANDO_PRODUCAO,
        versao=1,
    )

    assert entrega.status == StatusEntrega.AGUARDANDO_PRODUCAO
    assert entrega.tentativa == 1


def test_entrega_recusa_identificador_vazio():
    with pytest.raises(ErroEntrega) as erro:
        Entrega(
            entrega_id="",
            tenant_id="tenant-1",
            unidade_id="unidade-1",
            pedido_id="pedido-1",
            endereco_id="endereco-1",
            modalidade=ModalidadeEntrega.PROPRIA,
            status=StatusEntrega.AGUARDANDO_PRODUCAO,
            versao=1,
        )

    assert erro.value.codigo == "identificador_invalido"
