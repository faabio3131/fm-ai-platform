"""Seed efêmero da F9-E sobre o runtime comercial PostgreSQL da F8-E."""

from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from infra.administracao.modelos_orm import ConfiguracaoEstabelecimentoORM
from scripts.seed_f8e_commercial_runtime import TENANT, UNIDADE, main as seed_f8e


def main() -> None:
    if os.getenv("FM_AI_TEST_MODE") == "1":
        raise RuntimeError("F9-E nao pode executar com FM_AI_TEST_MODE=1")

    seed_f8e()
    engine = create_engine(os.environ["DATABASE_URL"], future=True)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    endpoint = os.environ.get("F9E_PRINT_ENDPOINT", "tcp://127.0.0.1:19100")

    with factory.begin() as session:
        config = session.get(ConfiguracaoEstabelecimentoORM, (TENANT, UNIDADE))
        if config is None:
            config = ConfiguracaoEstabelecimentoORM(
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                formas_pagamento=[],
                parametros_operacionais={},
                politica_financeira={},
            )
            session.add(config)

        parametros = dict(config.parametros_operacionais or {})
        parametros["impressao"] = {
            "destinos": [
                {
                    "provider": "raw_tcp",
                    "setor_id": "setor-f8e",
                    "impressora_id": endpoint,
                    "max_tentativas": 2,
                    "ativo": True,
                }
            ]
        }
        config.parametros_operacionais = parametros
        config.versao += 1

    print(f"F9-E commercial print destination ready: {endpoint}")


if __name__ == "__main__":
    main()
