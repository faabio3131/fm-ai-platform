"""SecretStore cifrado para credenciais cadastradas pelo navegador.

A chave mestra é configuração de infraestrutura e nunca é gravada no banco. Cada
rotação cria uma nova referência `vault:*`; referências antigas permanecem apenas
para auditoria/rollback operacional e deixam de ser apontadas pelo control plane.
"""

from __future__ import annotations

import os
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from core.seguranca.contexto import ContextoExecucao
from core.seguranca.erros import ReferenciaSegredoInvalida, SegredoAusente
from core.seguranca.permissoes import Permissao
from core.seguranca.segredos import SecretValue

from .segredos_orm import SegredoIntegracaoORM


class EncryptedSQLAlchemySecretStore:
    """Armazena valores cifrados e resolve referências `vault:*`."""

    def __init__(self, session: Session, *, master_key: str | None = None) -> None:
        raw_value = (
            master_key
            if master_key is not None
            else os.getenv("FM_AI_SECRET_MASTER_KEY", "")
        )
        raw = (raw_value or "").strip()
        if not raw:
            raise RuntimeError(
                "FM_AI_SECRET_MASTER_KEY ausente; configure a chave mestra da infraestrutura"
            )
        try:
            self._fernet = Fernet(raw.encode("ascii"))
        except (ValueError, UnicodeEncodeError) as exc:
            raise RuntimeError("FM_AI_SECRET_MASTER_KEY invalida") from exc
        self._session = session

    @staticmethod
    def _autorizar(contexto: ContextoExecucao) -> None:
        if Permissao.INTEGRACAO_GERENCIAR not in contexto.permissoes:
            raise PermissionError("integracao.gerenciar obrigatoria")

    def armazenar(
        self,
        *,
        contexto: ContextoExecucao,
        provedor: str,
        finalidade: str,
        valor: str,
    ) -> str:
        self._autorizar(contexto)
        provider = provedor.strip().casefold()
        purpose = finalidade.strip().casefold()
        secret = valor.strip()
        if not provider or not purpose or not secret:
            raise ValueError("provedor, finalidade e segredo sao obrigatorios")
        reference = f"vault:{uuid4().hex}"
        encrypted = self._fernet.encrypt(secret.encode("utf-8")).decode("ascii")
        self._session.add(
            SegredoIntegracaoORM(
                referencia=reference,
                tenant_id=contexto.tenant_id,
                unidade_id=contexto.unidade_id,
                provedor=provider,
                finalidade=purpose,
                ciphertext=encrypted,
                criado_por=contexto.usuario_id,
                correlation_id=contexto.correlation_id,
            )
        )
        self._session.flush()
        return reference

    def resolve(self, reference: str) -> SecretValue:
        if not isinstance(reference, str) or not reference.startswith("vault:"):
            raise ReferenciaSegredoInvalida("referencia vault invalida")
        row = self._session.get(SegredoIntegracaoORM, reference)
        if row is None:
            raise SegredoAusente("segredo vault indisponivel")
        try:
            plain = self._fernet.decrypt(row.ciphertext.encode("ascii")).decode("utf-8")
        except (InvalidToken, UnicodeDecodeError, UnicodeEncodeError) as exc:
            raise SegredoAusente("segredo vault nao pode ser decifrado") from exc
        return SecretValue(plain)

    def pertence_ao_escopo(self, *, contexto: ContextoExecucao, reference: str) -> bool:
        row = self._session.get(SegredoIntegracaoORM, reference)
        return bool(
            row
            and row.tenant_id == contexto.tenant_id
            and row.unidade_id == contexto.unidade_id
        )
