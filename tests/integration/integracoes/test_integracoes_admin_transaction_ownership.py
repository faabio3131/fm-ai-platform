from __future__ import annotations

from datetime import UTC, datetime

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from application import integracoes_admin_transacoes
from application.integracoes_admin_transacoes import (
    AplicacaoIntegracoesAdminV1,
)
from core.integracoes.modelos import AmbienteIntegracao
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Papel, Permissao
from infra.integracoes.modelos_orm import (
    IntegrationConfigBase,
    ServicoExternoConfigORM,
)
from infra.seguranca.modelos_orm import (
    CredencialReferenciaORM,
    EventoAuditoriaORM,
    SecurityBase,
)
from infra.seguranca.segredos_orm import (
    SecretVaultBase,
    SegredoIntegracaoORM,
)

TENANT = "tenant-sd1e-integracoes"
UNIDADE = "unidade-sd1e-integracoes"
AGORA = datetime(
    2026,
    8,
    27,
    22,
    0,
    tzinfo=UTC,
)


def _contexto() -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        usuario_id="admin-sd1e",
        papeis=frozenset(
            {
                Papel.ADMINISTRADOR,
            }
        ),
        permissoes=frozenset(
            Permissao
        ),
        correlation_id="corr-sd1e-integracoes",
        solicitado_em=AGORA,
        origem="tests.sd1e.integracoes_admin",
        unidades_permitidas=frozenset(
            {
                UNIDADE,
            }
        ),
    )


def _infra():
    engine = create_engine(
        "sqlite://",
        connect_args={
            "check_same_thread": False,
        },
        poolclass=StaticPool,
    )

    SecurityBase.metadata.create_all(
        engine
    )
    SecretVaultBase.metadata.create_all(
        engine
    )
    IntegrationConfigBase.metadata.create_all(
        engine
    )

    factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    master_key = Fernet.generate_key().decode(
        "ascii"
    )

    application = AplicacaoIntegracoesAdminV1(
        factory,
        master_key=master_key,
    )

    return (
        engine,
        factory,
        application,
    )


def _salvar(
    application: AplicacaoIntegracoesAdminV1,
):
    return application.salvar_configuracao(
        _contexto(),
        configuracao_id="ia.generativa--gemini",
        servico="ia.generativa",
        provedor="gemini",
        conta_externa="principal",
        ambiente=AmbienteIntegracao.HOMOLOGACAO,
        parametros_publicos={
            "model": "gemini-test",
        },
        finalidades_atuais={},
        novos_segredos={
            "api_key": "segredo-super-secreto",
        },
        habilitada=True,
        versao_esperada=0,
    )


def test_application_integracoes_salva_tudo_atomicamente() -> None:
    engine, _factory, application = _infra()

    configuracao, rotacionada = _salvar(
        application
    )

    assert rotacionada is True
    assert configuracao.versao == 1
    assert configuracao.homologada is False

    with Session(engine) as session:
        configs = session.scalars(
            select(
                ServicoExternoConfigORM
            )
        ).all()

        refs = session.scalars(
            select(
                CredencialReferenciaORM
            )
        ).all()

        secrets = session.scalars(
            select(
                SegredoIntegracaoORM
            )
        ).all()

        audits = session.scalars(
            select(
                EventoAuditoriaORM
            )
        ).all()

        assert len(configs) == 1
        assert len(refs) == 1
        assert len(secrets) == 1
        assert len(audits) == 1

        assert configs[0].versao == 1
        assert refs[0].ativa is True

        assert (
            refs[0].referencia
            == secrets[0].referencia
        )

        assert (
            "segredo-super-secreto"
            not in secrets[0].ciphertext
        )

        assert audits[0].acao == (
            "integracao.configurar"
        )


def test_application_integracoes_rollback_remove_todos_os_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        engine,
        _factory,
        application,
    ) = _infra()

    real = (
        integracoes_admin_transacoes
        .ServicoConfiguracoesExternas
        .configurar
    )

    def falhar_depois_do_write(
        self,
        *args,
        **kwargs,
    ):
        real(
            self,
            *args,
            **kwargs,
        )

        raise RuntimeError(
            "falha_depois_do_write_integracoes"
        )

    monkeypatch.setattr(
        integracoes_admin_transacoes
        .ServicoConfiguracoesExternas,
        "configurar",
        falhar_depois_do_write,
    )

    with pytest.raises(
        RuntimeError,
        match="falha_depois_do_write_integracoes",
    ):
        _salvar(
            application
        )

    with Session(engine) as session:
        assert (
            session.scalars(
                select(
                    ServicoExternoConfigORM
                )
            ).all()
            == []
        )

        assert (
            session.scalars(
                select(
                    CredencialReferenciaORM
                )
            ).all()
            == []
        )

        assert (
            session.scalars(
                select(
                    SegredoIntegracaoORM
                )
            ).all()
            == []
        )

        assert (
            session.scalars(
                select(
                    EventoAuditoriaORM
                )
            ).all()
            == []
        )


def test_application_integracoes_homologacao_commita_com_auditoria() -> None:
    engine, _factory, application = _infra()

    _salvar(
        application
    )

    homologada = application.homologar(
        _contexto(),
        configuracao_id="ia.generativa--gemini",
        evidencia_ref=(
            "healthcheck://gemini/sd1e7"
        ),
    )

    assert homologada.homologada is True
    assert homologada.versao == 2

    with Session(engine) as session:
        config = session.scalar(
            select(
                ServicoExternoConfigORM
            ).where(
                ServicoExternoConfigORM.configuracao_id
                == "ia.generativa--gemini"
            )
        )

        audits = session.scalars(
            select(
                EventoAuditoriaORM
            ).order_by(
                EventoAuditoriaORM.timestamp,
                EventoAuditoriaORM.audit_id,
            )
        ).all()

        assert config is not None
        assert config.homologada is True
        assert config.versao == 2

        assert {
            audit.acao
            for audit in audits
        } == {
            "integracao.configurar",
            "integracao.homologar",
        }
