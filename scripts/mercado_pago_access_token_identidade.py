"""Diagnostico sanitizado da identidade do Access Token Mercado Pago salvo no cofre.

Uso exclusivo de homologacao/desenvolvimento. O script carrega o Access Token ja
armazenado para o tenant/unidade do runtime, extrai somente o identificador publico
da aplicacao/Client ID embutido no formato documentado do token e imprime um JSON
sanitizado. O token completo nunca e exibido nem persistido.
"""

from __future__ import annotations

import json

from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.runtime import build_engine, load_runtime_settings
from infra.integracoes.mercado_pago_webhook_app import _CONFIG_ID, _finalidade
from infra.integracoes.repositorio_sqlalchemy import (
    RepositorioConfiguracoesExternasSQLAlchemy,
)
from infra.seguranca.modelos_orm import CredencialReferenciaORM
from infra.seguranca.segredos_sqlalchemy import EncryptedSQLAlchemySecretStore
from infra.seguranca.session_guard import build_session_factory


def _segredo_access_token(
    session: Session, *, tenant_id: str, unidade_id: str, finalidade: str
) -> str:
    row = session.scalar(
        select(CredencialReferenciaORM)
        .where(
            CredencialReferenciaORM.tenant_id == tenant_id,
            CredencialReferenciaORM.unidade_id == unidade_id,
            CredencialReferenciaORM.provedor == "mercado_pago",
            CredencialReferenciaORM.finalidade == finalidade,
            CredencialReferenciaORM.ativa.is_(True),
        )
        .order_by(CredencialReferenciaORM.versao.desc())
        .limit(1)
    )
    if row is None:
        raise RuntimeError("Access Token Mercado Pago indisponivel")
    return EncryptedSQLAlchemySecretStore(session).resolve(row.referencia).reveal()


def identificar_token(access_token: str) -> dict[str, object]:
    """Extrai somente metadados nao secretos do formato documentado APP_USR-*.

    Mercado Pago documenta o Client ID como o primeiro segmento numerico depois
    de APP_USR. Nenhuma outra parte do token e retornada.
    """

    token = access_token.strip()
    partes = token.split("-")
    prefixo = partes[0] if partes else ""
    client_id = partes[1].strip() if len(partes) > 1 else ""
    formato_reconhecido = prefixo in {"APP_USR", "TEST"} and client_id.isdigit()
    return {
        "prefixo": prefixo if prefixo in {"APP_USR", "TEST"} else "desconhecido",
        "client_id": client_id if formato_reconhecido else None,
        "formato_reconhecido": formato_reconhecido,
    }


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
        finalidade = _finalidade(config, "access_token")
        token = _segredo_access_token(
            session,
            tenant_id=settings.tenant_id,
            unidade_id=settings.unidade_id,
            finalidade=finalidade,
        )

    resultado = identificar_token(token)
    print(json.dumps(resultado, ensure_ascii=False))


if __name__ == "__main__":
    main()

