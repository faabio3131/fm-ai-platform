"""Adapter comercial RAW TCP/JetDirect para impressoras de rede."""

from __future__ import annotations

import socket
from urllib.parse import urlparse

from core.impressao.adapters import ErroAdaptadorImpressao


class ImpressoraTCPRaw:
    """Envia ticket minimizado por TCP com timeout e erro normalizado."""

    def __init__(self, *, timeout_segundos: float = 3.0) -> None:
        if timeout_segundos <= 0 or timeout_segundos > 30:
            raise ValueError("timeout_impressao_invalido")
        self._timeout = timeout_segundos

    @staticmethod
    def _endpoint(impressora_id: str) -> tuple[str, int]:
        parsed = urlparse(impressora_id)
        if parsed.scheme != "tcp" or not parsed.hostname:
            raise ErroAdaptadorImpressao("endpoint_impressora_invalido")
        porta = parsed.port or 9100
        if porta < 1 or porta > 65535:
            raise ErroAdaptadorImpressao("endpoint_impressora_invalido")
        return parsed.hostname, porta

    def imprimir(self, *, impressora_id: str, job_id: str, conteudo: str) -> None:
        del job_id
        host, porta = self._endpoint(impressora_id)
        payload = (conteudo.rstrip() + "\n").encode("utf-8", errors="replace")
        try:
            with socket.create_connection((host, porta), timeout=self._timeout) as conexao:
                conexao.settimeout(self._timeout)
                conexao.sendall(payload)
        except (OSError, TimeoutError) as exc:
            raise ErroAdaptadorImpressao("impressora_indisponivel") from exc
