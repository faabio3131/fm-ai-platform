"""Diagnostico seguro da secret de webhook Mercado Pago salva no cofre.

Compara, sem exibir os valores, a secret ativa resolvida pelo runtime com a
Assinatura secreta exibida especificamente em Webhooks > Modo de teste da mesma
aplicacao Mercado Pago. Tambem correlaciona o Client ID publico do Access Token,
o ambiente configurado e o host da URL de notificacao, sem imprimir tokens,
segredos, assinatura HMAC ou URL completa.
"""

from __future__ import annotations

import getpass
import hashlib
import json
import secrets
from dataclasses import dataclass
from urllib.parse import urlparse

from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.runtime import build_engine, load_runtime_settings
from infra.integracoes.repositorio_sqlalchemy import RepositorioConfiguracoesExternasSQLAlchemy
from infra.seguranca.modelos_orm import CredencialReferenciaORM
from infra.seguranca.segredos_sqlalchemy import EncryptedSQLAlchemySecretStore
from infra.seguranca.session_guard import build_session_factory
from scripts.mercado_pago_access_token_identidade import identificar_token

_CONFIG_ID = "pagamentos.pix--mercado_pago"
_PROVEDOR = "mercado_pago"


def _fingerprint(valor: str) -> str:
    """Fingerprint curto e irreversivel para diagnostico visual."""
    return hashlib.sha256(valor.encode("utf-8")).hexdigest()[:12]


def _host_notificacao(url: str) -> str:
    host = (urlparse(url).hostname or "").strip().lower()
    return host or "ausente"


@dataclass(frozen=True)
class DiagnosticoSecret:
    finalidade: str
    versao: int
    criada_em: str
    fingerprint_cofre: str
    fingerprint_painel: str
    corresponde: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "finalidade": self.finalidade,
            "versao": self.versao,
            "criada_em": self.criada_em,
            "fingerprint_cofre": self.fingerprint_cofre,
            "fingerprint_painel": self.fingerprint_painel,
            "corresponde": self.corresponde,
        }


def _resolver_credencial_ativa(
    session: Session,
    *,
    tenant_id: str,
    unidade_id: str,
    finalidade: str,
) -> tuple[CredencialReferenciaORM, str]:
    row = session.scalar(
        select(CredencialReferenciaORM)
        .where(
            CredencialReferenciaORM.tenant_id == tenant_id,
            CredencialReferenciaORM.unidade_id == unidade_id,
            CredencialReferenciaORM.provedor == _PROVEDOR,
            CredencialReferenciaORM.finalidade == finalidade,
            CredencialReferenciaORM.ativa.is_(True),
        )
        .order_by(CredencialReferenciaORM.versao.desc())
        .limit(1)
    )
    if row is None:
        raise RuntimeError(f"credencial Mercado Pago ativa nao encontrada: {finalidade}")
    segredo = EncryptedSQLAlchemySecretStore(session).resolve(row.referencia).reveal()
    if not segredo:
        raise RuntimeError(f"credencial Mercado Pago resolvida vazia: {finalidade}")
    return row, segredo


def _resolver_ativa(
    session: Session,
    *,
    tenant_id: str,
    unidade_id: str,
) -> tuple[CredencialReferenciaORM, str]:
    config = RepositorioConfiguracoesExternasSQLAlchemy(session).obter(
        tenant_id=tenant_id,
        unidade_id=unidade_id,
        configuracao_id=_CONFIG_ID,
    )
    if config is None:
        raise RuntimeError("configuracao Mercado Pago nao encontrada")

    finalidade = str(config.credenciais.get("webhook_secret") or "").strip()
    if not finalidade:
        raise RuntimeError("finalidade webhook_secret nao configurada")
    return _resolver_credencial_ativa(
        session,
        tenant_id=tenant_id,
        unidade_id=unidade_id,
        finalidade=finalidade,
    )


def comparar(*, row: CredencialReferenciaORM, segredo_cofre: str, segredo_painel: str) -> DiagnosticoSecret:
    painel = segredo_painel.strip()
    if not painel:
        raise ValueError("secret do painel nao informada")
    fp_cofre = _fingerprint(segredo_cofre)
    fp_painel = _fingerprint(painel)
    return DiagnosticoSecret(
        finalidade=row.finalidade,
        versao=row.versao,
        criada_em=row.criada_em.isoformat(),
        fingerprint_cofre=fp_cofre,
        fingerprint_painel=fp_painel,
        corresponde=secrets.compare_digest(fp_cofre, fp_painel),
    )


def main() -> None:
    load_dotenv()
    settings = load_runtime_settings()
    engine = build_engine(settings)
    session_factory = build_session_factory(engine=engine, commercial=settings.commercial)

    with session_factory() as session:
        config = RepositorioConfiguracoesExternasSQLAlchemy(session).obter(
            tenant_id=settings.tenant_id,
            unidade_id=settings.unidade_id,
            configuracao_id=_CONFIG_ID,
        )
        if config is None or not config.habilitada:
            raise RuntimeError("configuracao Mercado Pago nao encontrada")

        row, segredo_cofre = _resolver_ativa(
            session,
            tenant_id=settings.tenant_id,
            unidade_id=settings.unidade_id,
        )

        finalidade_access = str(config.credenciais.get("access_token") or "").strip()
        if not finalidade_access:
            raise RuntimeError("finalidade access_token nao configurada")
        _, access_token = _resolver_credencial_ativa(
            session,
            tenant_id=settings.tenant_id,
            unidade_id=settings.unidade_id,
            finalidade=finalidade_access,
        )
        identidade = identificar_token(access_token)

        segredo_painel = getpass.getpass(
            "Cole a Assinatura secreta exibida em KORDENA GERENTE AI > Webhooks > Modo de teste "
            "para a URL atualmente configurada (entrada oculta): "
        )
        diagnostico = comparar(
            row=row,
            segredo_cofre=segredo_cofre,
            segredo_painel=segredo_painel,
        )

        notification_url = str(config.parametros.get("notification_url") or "").strip()
        ambiente = getattr(config.ambiente, "value", str(config.ambiente))

    payload = diagnostico.as_dict()
    payload.update(
        {
            "configuracao_id": _CONFIG_ID,
            "ambiente": ambiente,
            "notification_host": _host_notificacao(notification_url),
            "access_token_client_id": identidade.get("client_id"),
            "access_token_formato_reconhecido": identidade.get("formato_reconhecido"),
        }
    )
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
