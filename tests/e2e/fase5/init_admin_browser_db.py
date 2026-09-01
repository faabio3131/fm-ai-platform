from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session

from core.seguranca.permissoes import Papel
from infra.administracao.repositorio_sqlalchemy import (
    RepositorioAdministracaoSQLAlchemy,
)
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy
from migrations.runner import run_migrations

db_path = Path(os.environ["FM_AI_F5_E2E_DB_PATH"]).resolve()
db_path.parent.mkdir(parents=True, exist_ok=True)
if db_path.exists():
    db_path.unlink()

url = URL.create("sqlite", database=str(db_path))
engine = create_engine(url, future=True)
run_migrations(engine)

with Session(engine) as session:
    owner = RepositorioIdentidadesSQLAlchemy(session).criar_usuario(
        email="owner.f5.e2e@example.test",
        password="senha-owner-f5-e2e-123",
        admin_pin="472839",
        tenant_id="tenant-f5-e2e",
        unidade_padrao_id="matriz-f5-e2e",
        papeis=(Papel.ADMINISTRADOR,),
        unidades_permitidas=("matriz-f5-e2e",),
        acesso_admin_sensivel=True,
    )
    RepositorioIdentidadesSQLAlchemy(session).criar_usuario(
        email="caixa.f5.e2e@example.test",
        password="senha-caixa-f5-e2e-456",
        tenant_id="tenant-f5-e2e",
        unidade_padrao_id="matriz-f5-e2e",
        papeis=(Papel.CAIXA,),
        unidades_permitidas=("matriz-f5-e2e",),
        acesso_admin_sensivel=True,
    )
    admin = RepositorioAdministracaoSQLAlchemy(session)
    admin.garantir_escopo(
        tenant_id=owner.tenant_id,
        unidade_id=owner.unidade_id,
        nome_empresa="Empresa F5 E2E",
        nome_unidade="Matriz F5 E2E",
    )
    session.commit()

engine.dispose()
print(db_path)
