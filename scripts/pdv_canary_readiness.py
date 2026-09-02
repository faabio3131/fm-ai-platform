"""CLI somente leitura para decisao operacional do canary PDV F6-E."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from core.pdv.adaptadores_sqlalchemy import RepositorioPDVSQLAlchemy
from core.pdv.reconciliacao import RecomendacaoCoortePDV
from core.runtime.config import load_runtime_settings
from migrations.runner import assert_schema_current


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Readiness do canary PDV")
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument(
        "--require-eligible",
        action="store_true",
        help="retorna status 2 se a coorte nao estiver elegivel para ampliacao",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    settings = load_runtime_settings()
    engine = create_engine(settings.database_url, future=True)
    assert_schema_current(engine)

    with Session(engine) as session:
        resumo = RepositorioPDVSQLAlchemy(session).resumir_readiness(
            settings.tenant_id,
            settings.unidade_id,
            limite=args.limit,
        )

    payload = {
        "tenant_id": settings.tenant_id,
        "unidade_id": settings.unidade_id,
        "environment": settings.environment.value,
        "total_registros": resumo.total_registros,
        "divergentes": resumo.divergentes,
        "reparo_necessario": resumo.reparo_necessario,
        "pendentes": resumo.pendentes,
        "chaves_invalidas": resumo.chaves_invalidas,
        "recomendacao": resumo.recomendacao.value,
        "apto_ampliacao": resumo.apto_ampliacao,
        "metricas": [asdict(metrica) for metrica in resumo.metricas],
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))

    if args.require_eligible and (
        resumo.recomendacao is not RecomendacaoCoortePDV.AMPLIACAO_ELEGIVEL
    ):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
