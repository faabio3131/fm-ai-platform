"""Diagnostico seguro da secret de webhook Mercado Pago salva no cofre.

Compara, sem exibir os valores, a secret ativa resolvida pelo runtime com uma
secret informada interativamente pelo operador a partir do painel Mercado Pago.
A entrada do painel usa getpass para nao aparecer no terminal.
"""

from __future__ import annotations

import getpass
import hashlib
import json
import secrets
from dataclasses import dataclass

from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.runtime import build_engine, load_runtime_settings
from infra.integracoes.repositorio_sqlalchemy import RepositorioConfiguracoesExternasSQLAlchemy
from infra.seguranca.modelos_orm import CredencialReferenciaORM
from infra.seguranca.segredos_sqlalchemy import EncryptedSQLAlchemySecretStore
from infra.seguranca.session_guard import build_session_factory

_CONFIG_ID = "pagamentos.pix--mercado_pago"
_PROVEDOR = "mercado_pago"


def _fingerprint(valor: str) -> str:
    """Fingerprint curto e irreversivel para diagnostico visual."""
    return hashlib.sha256(valor.encode("utf-8")).hexdigest()[:12]


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
        raise RuntimeError("webhook_secret ativa nao encontrada no cofre")

    segredo = EncryptedSQLAlchemySecretStore(session).resolve(row.referencia).reveal()
    if not segredo:
        raise RuntimeError("webhook_secret resolvida vazia")
    return row, segredo


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
        row, segredo_cofre = _resolver_ativa(
            session,
            tenant_id=settings.tenant_id,
            unidade_id=settings.unidade_id,
        )
        segredo_painel = getpass.getpass(
            "Cole a Assinatura secreta do Modo de teste do Mercado Pago (entrada oculta): "
        )
        diagnostico = comparar(
            row=row,
            segredo_cofre=segredo_cofre,
            segredo_painel=segredo_painel,
        )

    print(json.dumps(diagnostico.as_dict(), ensure_ascii=False))


if __name__ == "__main__":
    main()
