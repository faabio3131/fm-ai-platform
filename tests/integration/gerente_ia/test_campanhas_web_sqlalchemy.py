from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from infra.gerente_ia.campanhas_web_sqlalchemy import CampanhasWebSQLAlchemy
from infra.gerente_ia.modelos_orm import CoreRuntimeBase, RascunhoCampanhaORM

AGORA = datetime(2026, 10, 1, 19, 0, tzinfo=timezone.utc)


def _factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    CoreRuntimeBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        session.add(
            RascunhoCampanhaORM(
                rascunho_id="camp-web-1",
                tenant_id="tenant-1",
                unidade_id="unidade-1",
                canal="whatsapp",
                finalidade="promocoes",
                objetivo="reativacao",
                texto_base="Mensagem inicial",
                audiencia_elegivel=0,
                criado_em=AGORA,
                criado_por="admin-1",
                correlation_id="corr-create",
                idempotency_key="create-1",
                status="rascunho",
            )
        )
        session.commit()
    return factory


def test_audiencia_e_submissao_preservam_mesmo_aggregate() -> None:
    factory = _factory()
    with factory() as session:
        repo = CampanhasWebSQLAlchemy(session)
        repo.definir_audiencia(
            tenant_id="tenant-1",
            unidade_id="unidade-1",
            campanha_id="camp-web-1",
            cliente_ids=("cliente-1", "cliente-2"),
            usuario_id="admin-1",
            correlation_id="corr-audience",
            idempotency_key="audience-1",
            agora=AGORA,
        )
        assert repo.audiencia_ids(
            tenant_id="tenant-1",
            unidade_id="unidade-1",
            campanha_id="camp-web-1",
        ) == ("cliente-1", "cliente-2")
        row_antes = repo.obter_web(
            tenant_id="tenant-1",
            unidade_id="unidade-1",
            campanha_id="camp-web-1",
        )
        fingerprint_com_audiencia = repo.fingerprint_web(row_antes)
        assert fingerprint_com_audiencia != repo.fingerprint(row_antes)
        row = repo.submeter(
            tenant_id="tenant-1",
            unidade_id="unidade-1",
            campanha_id="camp-web-1",
            usuario_id="admin-1",
            correlation_id="corr-submit",
            idempotency_key="submit-1",
            agora=AGORA,
        )
        assert row.status == "aguardando_aprovacao"
        assert repo.fingerprint_web(row) == fingerprint_com_audiencia
        aprovado = repo.aprovar(
            tenant_id="tenant-1",
            unidade_id="unidade-1",
            campanha_id="camp-web-1",
            usuario_id="admin-1",
            correlation_id="corr-approve",
            idempotency_key="approve-1",
            agora=AGORA,
        )
        assert aprovado.campanha_id == "camp-web-1"
        publicado = repo.publicar(
            tenant_id="tenant-1",
            unidade_id="unidade-1",
            campanha_id="camp-web-1",
            usuario_id="admin-1",
            correlation_id="corr-publish",
            idempotency_key="publish-1",
            agora=AGORA,
        )
        assert str(publicado.campanha_ref).startswith("campanha://v1/camp-web-1/")
        tipos = [item.event_type for item in repo.historico(
            tenant_id="tenant-1",
            unidade_id="unidade-1",
            campanha_id="camp-web-1",
        )]
        assert tipos == [
            "campanha.audiencia_definida",
            "campanha.submetida",
            "campanha.aprovada",
            "campanha.publicavel",
        ]


def test_edicao_de_canal_invalida_audiencia_anterior() -> None:
    factory = _factory()
    with factory() as session:
        repo = CampanhasWebSQLAlchemy(session)
        repo.definir_audiencia(
            tenant_id="tenant-1",
            unidade_id="unidade-1",
            campanha_id="camp-web-1",
            cliente_ids=("cliente-1",),
            usuario_id="admin-1",
            correlation_id="corr-audience",
            idempotency_key="audience-1",
            agora=AGORA,
        )
        row = repo.atualizar_rascunho(
            tenant_id="tenant-1",
            unidade_id="unidade-1",
            campanha_id="camp-web-1",
            canal="email",
            finalidade="promocoes",
            objetivo="reativacao",
            texto_base="Mensagem alterada",
            usuario_id="admin-1",
            correlation_id="corr-edit",
            idempotency_key="edit-1",
            agora=AGORA,
        )
        assert row.audiencia_elegivel == 0
