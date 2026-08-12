"""Guardas de minimização para payloads de observabilidade/auditoria."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

CAMPOS_SENSIVEIS = frozenset(
    {
        "access_token",
        "address",
        "authorization",
        "client_secret",
        "cpf",
        "documento",
        "email",
        "endereco",
        "mensagem_bruta",
        "nome_completo",
        "password",
        "payload_bruto",
        "phone",
        "prova_bruta",
        "senha",
        "secret",
        "telefone",
        "token",
        "whatsapp",
    }
)

CAMPOS_REFERENCIA_SEGUROS = frozenset(
    {
        "cliente_ref",
        "email_hash",
        "payload_hash",
        "prova_hash",
        "segredo_ref",
        "telefone_hash",
    }
)


def _normalizar_chave(chave: object) -> str:
    return str(chave).strip().lower().replace("-", "_")


def chave_sensivel(chave: object) -> bool:
    normalizada = _normalizar_chave(chave)
    if normalizada in CAMPOS_REFERENCIA_SEGUROS or normalizada.endswith("_hash"):
        return False
    return normalizada in CAMPOS_SENSIVEIS or any(
        normalizada.endswith(f"_{campo}") for campo in CAMPOS_SENSIVEIS
    )


def encontrar_campos_sensiveis(payload: object, prefixo: str = "$") -> tuple[str, ...]:
    encontrados: list[str] = []
    if isinstance(payload, Mapping):
        for chave, valor in payload.items():
            nome = _normalizar_chave(chave)
            caminho = f"{prefixo}.{nome}"
            if chave_sensivel(nome):
                encontrados.append(caminho)
            encontrados.extend(encontrar_campos_sensiveis(valor, caminho))
    elif isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
        for indice, valor in enumerate(payload):
            encontrados.extend(encontrar_campos_sensiveis(valor, f"{prefixo}[{indice}]"))
    return tuple(sorted(set(encontrados)))


def sanitizar_payload(payload: object) -> object:
    """Redige valores sensíveis preservando estrutura para diagnóstico."""
    if isinstance(payload, Mapping):
        resultado: dict[str, Any] = {}
        for chave, valor in payload.items():
            nome = str(chave)
            resultado[nome] = "<redacted>" if chave_sensivel(chave) else sanitizar_payload(valor)
        return resultado
    if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
        return [sanitizar_payload(valor) for valor in payload]
    return payload


def exigir_payload_minimizado(payload: object) -> None:
    encontrados = encontrar_campos_sensiveis(payload)
    if encontrados:
        raise ValueError(f"payload_contem_pii_ou_segredo:{','.join(encontrados)}")
