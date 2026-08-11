"""Guardas fail-closed para scripts de restore/migração em teste/homologação."""

from __future__ import annotations

from urllib.parse import urlparse

from .modelos import ErroHardening

HOSTS_LOCAIS = frozenset({"", "127.0.0.1", "localhost", "::1"})
MARCADORES_PRODUCAO = (
    "prod",
    "production",
    "rds.amazonaws.com",
    "cloudsql",
    "database.windows.net",
)


def classificar_destino_banco(url: str) -> str:
    valor = url.strip()
    if not valor:
        raise ErroHardening("url_banco_vazia")
    if valor == "sqlite:///:memory:" or valor.startswith("sqlite+pysqlite:///:memory:"):
        return "efemero"
    parsed = urlparse(valor)
    if parsed.username or parsed.password:
        raise ErroHardening("url_banco_contem_credencial")
    host = (parsed.hostname or "").lower()
    texto = valor.lower()
    if any(marcador in texto for marcador in MARCADORES_PRODUCAO):
        return "producao_ou_gerenciado"
    if host in HOSTS_LOCAIS:
        return "local"
    return "remoto"


def exigir_destino_nao_producao(url: str) -> str:
    classificacao = classificar_destino_banco(url)
    if classificacao not in {"efemero", "local"}:
        raise ErroHardening(f"destino_banco_bloqueado:{classificacao}")
    return classificacao
