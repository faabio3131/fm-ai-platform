from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from application.campanhas_governadas import (
    aprovar_campanha_v1,
    publicar_campanha_v1,
)
from core.gerente_ia.erros import ErroGerenteIA
from core.gerente_ia.modelos import CampanhaAprovada, CampanhaPublicavel
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import MATRIZ_PADRAO, Papel
from infra.gerente_ia.modelos_orm import (
    CoreRuntimeBase,
    EventoCoreORM,
    RascunhoCampanhaORM,
)
from infra.seguranca.modelos_orm import EventoAuditoriaORM, SecurityBase

AGORA = datetime(2026, 8, 29, 18, 0, tzinfo=timezone.utc)
TENANT = "tenant-f4g"
UNIDADE = "loja-f4g"
CAMPANHA = "camp-f4g-1"


def _factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    CoreRuntimeBase.metadata.create_all(engine)
    SecurityBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    with factory() as session:
        session.add(
            RascunhoCampanhaORM(
                rascunho_id=CAMPANHA,
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                canal="whatsapp",
                finalidade="promocoes",
                objetivo="reativacao",
                texto_base="Mensagem aprovada somente por humano",
                audiencia_elegivel=8,
                criado_em=AGORA,
                criado_por="gerente-1",
                correlation_id="corr-draft",
                idempotency_key="draft-f4g-1",
                status="rascunho",
            )
        )
        session.commit()
    return factory


def _gerente(
    *, tenant_id: str = TENANT, unidade_id: str = UNIDADE
) -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id=tenant_id,
        unidade_id=unidade_id,
        usuario_id="gerente-1",
        papeis=frozenset({Papel.GERENTE}),
        permissoes=MATRIZ_PADRAO[Papel.GERENTE],
        correlation_id="corr-f4g",
        solicitado_em=AGORA,
        origem="teste_f4g",
        unidades_permitidas=frozenset({unidade_id}),
    )


def test_aprovar_publicar_e_repetir_sem_duplicar_transicao() -> None:
    factory = _factory()

    aprovada = aprovar_campanha_v1(
        session_factory=factory,
        contexto_humano=_gerente(),
        campanha_id=CAMPANHA,
        idempotency_key="approve-f4g-1",
    )
    replay_aprovacao = aprovar_campanha_v1(
        session_factory=factory,
        contexto_humano=_gerente(),
        campanha_id=CAMPANHA,
        idempotency_key="approve-f4g-1",
    )

    assert isinstance(aprovada, CampanhaAprovada)
    assert replay_aprovacao.idempotente is True
    assert replay_aprovacao.fingerprint == aprovada.fingerprint

    publicavel = publicar_campanha_v1(
        session_factory=factory,
        contexto_humano=_gerente(),
        campanha_id=CAMPANHA,
        idempotency_key="publish-f4g-1",
    )
    replay_publicacao = publicar_campanha_v1(
        session_factory=factory,
        contexto_humano=_gerente(),
        campanha_id=CAMPANHA,
        idempotency_key="publish-f4g-1",
    )

    assert isinstance(publicavel, CampanhaPublicavel)
    assert str(publicavel.campanha_ref).startswith("campanha://v1/")
    assert replay_publicacao.idempotente is True
    assert replay_publicacao.campanha_ref == publicavel.campanha_ref

    with factory() as session:
        campanha = session.get(RascunhoCampanhaORM, CAMPANHA)
        assert campanha is not None
        assert campanha.status == "publicavel"

        eventos = tuple(
            session.scalars(
                select(EventoCoreORM)
                .where(
                    EventoCoreORM.tenant_id == TENANT,
                    EventoCoreORM.unidade_id == UNIDADE,
                    EventoCoreORM.aggregate_id == CAMPANHA,
                )
                .order_by(EventoCoreORM.versao)
            )
        )
        assert [evento.event_type for evento in eventos] == [
            "campanha.aprovada",
            "campanha.publicavel",
        ]
        assert all("texto_base" not in evento.payload_seguro for evento in eventos)
        assert all("telefone" not in evento.payload_seguro for evento in eventos)

        auditorias = tuple(
            session.scalars(
                select(EventoAuditoriaORM).where(
                    EventoAuditoriaORM.recurso_id == CAMPANHA
                )
            )
        )
        assert len(auditorias) == 4
        assert all(
            "texto_base" not in auditoria.metadata_segura
            for auditoria in auditorias
        )


def test_publicacao_sem_aprovacao_e_cross_tenant_falham_fechado() -> None:
    factory = _factory()

    with pytest.raises(ErroGerenteIA, match="campanha_nao_esta_aprovada"):
        publicar_campanha_v1(
            session_factory=factory,
            contexto_humano=_gerente(),
            campanha_id=CAMPANHA,
            idempotency_key="publish-before-approval",
        )

    with pytest.raises(ErroGerenteIA, match="recurso_indisponivel"):
        aprovar_campanha_v1(
            session_factory=factory,
            contexto_humano=_gerente(tenant_id="tenant-outro"),
            campanha_id=CAMPANHA,
            idempotency_key="approve-cross-tenant",
        )


def test_identidade_de_sistema_nao_pode_aprovar_campanha() -> None:
    factory = _factory()
    sistema = ContextoExecucao.sistema(
        identidade="gerente-ia",
        motivo="planejamento assistivo",
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        correlation_id="corr-system",
        solicitado_em=AGORA,
    )

    with pytest.raises(
        ErroGerenteIA, match="aprovacao_humana_gerencial_exigida"
    ):
        aprovar_campanha_v1(
            session_factory=factory,
            contexto_humano=sistema,
            campanha_id=CAMPANHA,
            idempotency_key="approve-system",
        )
