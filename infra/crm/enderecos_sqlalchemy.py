"""Vault cifrado de endereços autorizados para Customer Context V1."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import insert, select, update
from sqlalchemy.orm import Session

from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Permissao

from .enderecos_schema import crm_enderecos_seguros_v1


@dataclass(frozen=True)
class EnderecoClienteResolvido:
    referencia: str
    endereco_formatado: str
    cep: str
    place_id: str
    latitude: Decimal
    longitude: Decimal


class EncryptedSQLAlchemyAddressStore:
    """PII de endereço só é decifrada no boundary operacional autorizado."""

    def __init__(self, session: Session, *, master_key: str | None = None) -> None:
        raw = (master_key or os.getenv("FM_AI_SECRET_MASTER_KEY", "")).strip()
        if not raw:
            raise RuntimeError(
                "FM_AI_SECRET_MASTER_KEY ausente; configure a chave mestra da infraestrutura"
            )
        try:
            chave = raw.encode("ascii")
            self._fernet = Fernet(chave)
        except (ValueError, UnicodeEncodeError) as exc:
            raise RuntimeError("FM_AI_SECRET_MASTER_KEY invalida") from exc
        self._hmac_key = hashlib.sha256(b"fm-ai-crm-address-v1:" + chave).digest()
        self._session = session

    @staticmethod
    def _autorizar_leitura(contexto: ContextoExecucao) -> None:
        if Permissao.CLIENTE_VISUALIZAR not in contexto.permissoes:
            raise PermissionError("cliente.visualizar obrigatoria")

    @staticmethod
    def _autorizar_edicao(contexto: ContextoExecucao) -> None:
        if Permissao.CLIENTE_EDITAR not in contexto.permissoes:
            raise PermissionError("cliente.editar obrigatoria")

    @staticmethod
    def _payload(
        *,
        endereco_formatado: str,
        cep: str,
        place_id: str,
        latitude: Decimal,
        longitude: Decimal,
    ) -> dict[str, str]:
        endereco = " ".join(endereco_formatado.split())
        cep_norm = "".join(ch for ch in cep if ch.isdigit())
        place = place_id.strip()
        if not endereco or len(cep_norm) != 8 or not place:
            raise ValueError("endereco_validado_invalido")
        return {
            "endereco_formatado": endereco,
            "cep": cep_norm,
            "place_id": place,
            "latitude": str(Decimal(latitude)),
            "longitude": str(Decimal(longitude)),
        }

    def _hash(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        cliente_id: str,
        payload: dict[str, str],
    ) -> str:
        serializado = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        material = (
            f"{tenant_id}:{unidade_id}:{cliente_id}:entrega:{serializado}"
        ).encode("utf-8")
        return hmac.new(self._hmac_key, material, hashlib.sha256).hexdigest()

    def armazenar_validado(
        self,
        *,
        contexto: ContextoExecucao,
        cliente_id: str,
        endereco_formatado: str,
        cep: str,
        place_id: str,
        latitude: Decimal,
        longitude: Decimal,
        agora: datetime | None = None,
    ) -> str:
        self._autorizar_edicao(contexto)
        if not cliente_id.strip():
            raise ValueError("cliente_endereco_obrigatorio")
        instante = agora or datetime.now(timezone.utc)
        if instante.tzinfo is None or instante.utcoffset() is None:
            raise ValueError("timestamp_endereco_sem_timezone")
        payload = self._payload(
            endereco_formatado=endereco_formatado,
            cep=cep,
            place_id=place_id,
            latitude=latitude,
            longitude=longitude,
        )
        valor_hash = self._hash(
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
            cliente_id=cliente_id,
            payload=payload,
        )
        existente = self._session.execute(
            select(
                crm_enderecos_seguros_v1.c.referencia,
            ).where(
                crm_enderecos_seguros_v1.c.tenant_id == contexto.tenant_id,
                crm_enderecos_seguros_v1.c.unidade_id == contexto.unidade_id,
                crm_enderecos_seguros_v1.c.cliente_id == cliente_id,
                crm_enderecos_seguros_v1.c.finalidade == "entrega",
                crm_enderecos_seguros_v1.c.valor_hash == valor_hash,
            )
        ).scalar_one_or_none()
        if existente is not None:
            self._session.execute(
                update(crm_enderecos_seguros_v1)
                .where(crm_enderecos_seguros_v1.c.referencia == existente)
                .values(ultimo_uso_em=instante)
            )
            self._session.flush()
            return str(existente)

        referencia = f"address://{uuid4().hex}"
        ciphertext = self._fernet.encrypt(
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).decode("ascii")
        self._session.execute(
            insert(crm_enderecos_seguros_v1).values(
                referencia=referencia,
                tenant_id=contexto.tenant_id,
                unidade_id=contexto.unidade_id,
                cliente_id=cliente_id,
                finalidade="entrega",
                valor_hash=valor_hash,
                ciphertext=ciphertext,
                criado_por=contexto.usuario_id,
                correlation_id=contexto.correlation_id,
                criado_em=instante,
                ultimo_uso_em=instante,
            )
        )
        self._session.flush()
        return referencia

    def ultimo_ref(
        self,
        *,
        contexto: ContextoExecucao,
        cliente_id: str,
    ) -> str | None:
        self._autorizar_leitura(contexto)
        return self._session.execute(
            select(crm_enderecos_seguros_v1.c.referencia)
            .where(
                crm_enderecos_seguros_v1.c.tenant_id == contexto.tenant_id,
                crm_enderecos_seguros_v1.c.unidade_id == contexto.unidade_id,
                crm_enderecos_seguros_v1.c.cliente_id == cliente_id,
                crm_enderecos_seguros_v1.c.finalidade == "entrega",
            )
            .order_by(
                crm_enderecos_seguros_v1.c.ultimo_uso_em.desc(),
                crm_enderecos_seguros_v1.c.referencia,
            )
            .limit(1)
        ).scalar_one_or_none()

    def resolver(
        self,
        *,
        contexto: ContextoExecucao,
        cliente_id: str,
        referencia: str,
    ) -> EnderecoClienteResolvido:
        self._autorizar_leitura(contexto)
        if not referencia.startswith("address://"):
            raise ValueError("referencia_endereco_invalida")
        row = self._session.execute(
            select(crm_enderecos_seguros_v1).where(
                crm_enderecos_seguros_v1.c.referencia == referencia,
                crm_enderecos_seguros_v1.c.tenant_id == contexto.tenant_id,
                crm_enderecos_seguros_v1.c.unidade_id == contexto.unidade_id,
                crm_enderecos_seguros_v1.c.cliente_id == cliente_id,
                crm_enderecos_seguros_v1.c.finalidade == "entrega",
            )
        ).mappings().one_or_none()
        if row is None:
            raise LookupError("endereco_salvo_indisponivel")
        try:
            payload = json.loads(
                self._fernet.decrypt(str(row["ciphertext"]).encode("ascii")).decode(
                    "utf-8"
                )
            )
        except (
            InvalidToken,
            UnicodeDecodeError,
            UnicodeEncodeError,
            json.JSONDecodeError,
        ) as exc:
            raise LookupError("endereco_salvo_nao_pode_ser_decifrado") from exc
        return EnderecoClienteResolvido(
            referencia=referencia,
            endereco_formatado=str(payload["endereco_formatado"]),
            cep=str(payload["cep"]),
            place_id=str(payload["place_id"]),
            latitude=Decimal(str(payload["latitude"])),
            longitude=Decimal(str(payload["longitude"])),
        )
