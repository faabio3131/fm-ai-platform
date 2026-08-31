"""Contact Store cifrado para dados de contato do ClienteCRM."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.crm.modelos import CanalMarketing
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Permissao
from core.seguranca.segredos import SecretValue

from .contatos_orm import ContatoSeguroORM


class EncryptedSQLAlchemyContactStore:
    """Mantém PII em claro somente no boundary autorizado do CRM."""

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

        self._hmac_key = hashlib.sha256(b"fm-ai-crm-contact-v1:" + chave).digest()
        self._session = session

    @staticmethod
    def _autorizar_edicao(contexto: ContextoExecucao) -> None:
        if Permissao.CLIENTE_EDITAR not in contexto.permissoes:
            raise PermissionError("cliente.editar obrigatoria")

    @staticmethod
    def _autorizar_visualizacao(contexto: ContextoExecucao) -> None:
        if Permissao.CLIENTE_VISUALIZAR not in contexto.permissoes:
            raise PermissionError("cliente.visualizar obrigatoria")

    @staticmethod
    def _normalizar(*, canal: CanalMarketing, valor: str) -> str:
        bruto = valor.strip()
        if not bruto:
            raise ValueError("contato vazio")

        if canal is CanalMarketing.EMAIL:
            normalizado = bruto.casefold()
            if "@" not in normalizado:
                raise ValueError("email invalido")
            return normalizado

        if canal in {CanalMarketing.WHATSAPP, CanalMarketing.SMS}:
            prefixo_mais = bruto.startswith("+")
            digitos = re.sub(r"\D", "", bruto)
            if not digitos:
                raise ValueError("telefone invalido")
            return f"+{digitos}" if prefixo_mais else digitos

        raise ValueError("canal de contato nao suportado")

    def _hash(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        canal: CanalMarketing,
        valor_normalizado: str,
    ) -> str:
        material = (
            f"{tenant_id}:{unidade_id}:{canal.value}:{valor_normalizado}"
        ).encode()
        return hmac.new(self._hmac_key, material, hashlib.sha256).hexdigest()

    def armazenar(
        self,
        *,
        contexto: ContextoExecucao,
        canal: CanalMarketing,
        valor: str,
    ) -> str:
        self._autorizar_edicao(contexto)
        normalizado = self._normalizar(canal=canal, valor=valor)
        valor_hash = self._hash(
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
            canal=canal,
            valor_normalizado=normalizado,
        )
        existente = self._session.scalar(
            select(ContatoSeguroORM).where(
                ContatoSeguroORM.tenant_id == contexto.tenant_id,
                ContatoSeguroORM.unidade_id == contexto.unidade_id,
                ContatoSeguroORM.canal == canal.value,
                ContatoSeguroORM.valor_hash == valor_hash,
            )
        )
        if existente is not None:
            return existente.referencia

        referencia = f"contact://{uuid4().hex}"
        ciphertext = self._fernet.encrypt(normalizado.encode("utf-8")).decode("ascii")
        self._session.add(
            ContatoSeguroORM(
                referencia=referencia,
                tenant_id=contexto.tenant_id,
                unidade_id=contexto.unidade_id,
                canal=canal.value,
                valor_hash=valor_hash,
                ciphertext=ciphertext,
                criado_por=contexto.usuario_id,
                correlation_id=contexto.correlation_id,
            )
        )
        self._session.flush()
        return referencia

    def buscar(
        self,
        *,
        contexto: ContextoExecucao,
        canal: CanalMarketing,
        valor: str,
    ) -> str | None:
        self._autorizar_visualizacao(contexto)
        normalizado = self._normalizar(canal=canal, valor=valor)
        valor_hash = self._hash(
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
            canal=canal,
            valor_normalizado=normalizado,
        )
        row = self._session.scalar(
            select(ContatoSeguroORM).where(
                ContatoSeguroORM.tenant_id == contexto.tenant_id,
                ContatoSeguroORM.unidade_id == contexto.unidade_id,
                ContatoSeguroORM.canal == canal.value,
                ContatoSeguroORM.valor_hash == valor_hash,
            )
        )
        return row.referencia if row is not None else None

    def pertence_ao_escopo(
        self,
        *,
        contexto: ContextoExecucao,
        referencia: str,
    ) -> bool:
        row = self._session.get(ContatoSeguroORM, referencia)
        return bool(
            row
            and row.tenant_id == contexto.tenant_id
            and row.unidade_id == contexto.unidade_id
        )

    def resolver(
        self,
        *,
        contexto: ContextoExecucao,
        referencia: str,
    ) -> SecretValue:
        self._autorizar_visualizacao(contexto)
        if not isinstance(referencia, str) or not referencia.startswith("contact://"):
            raise ValueError("referencia de contato invalida")

        row = self._session.get(ContatoSeguroORM, referencia)
        if row is None:
            raise LookupError("contato indisponivel")
        if (
            row.tenant_id != contexto.tenant_id
            or row.unidade_id != contexto.unidade_id
        ):
            raise PermissionError("contato fora do escopo")

        try:
            plain = self._fernet.decrypt(row.ciphertext.encode("ascii")).decode("utf-8")
        except (InvalidToken, UnicodeDecodeError, UnicodeEncodeError) as exc:
            raise LookupError("contato nao pode ser decifrado") from exc

        return SecretValue(plain)
