from unittest.mock import MagicMock

import pytest

from core.impressao.adapters import ErroAdaptadorImpressao
from infra.impressao.adapter_tcp import ImpressoraTCPRaw


def test_adapter_tcp_envia_ticket_com_timeout(monkeypatch) -> None:
    conexao = MagicMock()
    conexao.__enter__.return_value = conexao
    monkeypatch.setattr("socket.create_connection", lambda endpoint, timeout: conexao)

    adapter = ImpressoraTCPRaw(timeout_segundos=2.5)
    adapter.imprimir(
        impressora_id="tcp://192.0.2.10:9100",
        job_id="job-1",
        conteudo="PEDIDO: 10",
    )

    conexao.settimeout.assert_called_once_with(2.5)
    conexao.sendall.assert_called_once_with(b"PEDIDO: 10\n")


def test_adapter_tcp_normaliza_indisponibilidade(monkeypatch) -> None:
    def falhar(*_args, **_kwargs):
        raise OSError("rede indisponivel")

    monkeypatch.setattr("socket.create_connection", falhar)
    with pytest.raises(ErroAdaptadorImpressao, match="impressora_indisponivel"):
        ImpressoraTCPRaw().imprimir(
            impressora_id="tcp://192.0.2.10:9100",
            job_id="job-2",
            conteudo="ticket",
        )


def test_adapter_tcp_rejeita_endpoint_nao_tcp() -> None:
    with pytest.raises(ErroAdaptadorImpressao, match="endpoint_impressora_invalido"):
        ImpressoraTCPRaw().imprimir(
            impressora_id="usb://printer",
            job_id="job-3",
            conteudo="ticket",
        )
