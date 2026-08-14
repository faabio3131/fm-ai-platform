from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from core.seguranca.contexto import ContextoExecucao
from core.seguranca.erros import PermissaoInsuficiente
from core.seguranca.permissoes import Papel, Permissao
from core.seguranca.segredos import ReferenceSecretStore
from infra.seguranca.credenciais import ServicoCredenciaisReferenciadas
from infra.seguranca.modelos_orm import CredencialReferenciaORM, SecurityBase


def _context(permissoes: frozenset[Permissao]) -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id="tenant-1",
        unidade_id="loja-a",
        usuario_id="admin-1",
        papeis=frozenset({Papel.ADMINISTRADOR}),
        permissoes=permissoes,
        correlation_id="corr-cred-1",
        solicitado_em=datetime.now(timezone.utc),
        origem="tests",
        unidades_permitidas=frozenset({"loja-a"}),
    )


def test_rotation_is_versioned_append_only_and_resolves_only_current() -> None:
    engine = create_engine("sqlite:///:memory:")
    SecurityBase.metadata.create_all(engine)
    store = ReferenceSecretStore(
        mapping={"ifood-v1": "secret-one", "ifood-v2": "secret-two"}
    )
    contexto = _context(frozenset(Permissao))

    with Session(engine) as session:
        service = ServicoCredenciaisReferenciadas(session, store)
        first = service.rotacionar(
            contexto=contexto,
            provedor="iFood",
            finalidade="client_secret",
            nova_referencia="mapping:ifood-v1",
        )
        second = service.rotacionar(
            contexto=contexto,
            provedor="iFood",
            finalidade="client_secret",
            nova_referencia="mapping:ifood-v2",
        )
        session.commit()

        assert first.versao == 1
        assert second.versao == 2
        assert service.resolver_valor(
            contexto=contexto,
            provedor="IFOOD",
            finalidade="CLIENT_SECRET",
        ) == "secret-two"
        history = service.historico(
            contexto=contexto,
            provedor="ifood",
            finalidade="client_secret",
        )
        assert [item.versao for item in history] == [2, 1]

        rows = session.scalars(
            select(CredencialReferenciaORM).order_by(CredencialReferenciaORM.versao)
        ).all()
        assert rows[0].ativa is False
        assert rows[0].desativada_em is not None
        assert rows[1].ativa is True
        assert rows[0].rotacionada_por == "admin-1"
        assert rows[1].correlation_id == "corr-cred-1"
        assert all("secret-" not in row.referencia for row in rows)


def test_rotation_requires_integration_permission() -> None:
    engine = create_engine("sqlite:///:memory:")
    SecurityBase.metadata.create_all(engine)
    with Session(engine) as session:
        service = ServicoCredenciaisReferenciadas(
            session, ReferenceSecretStore(mapping={"x": "hidden"})
        )
        with pytest.raises(PermissaoInsuficiente):
            service.rotacionar(
                contexto=_context(frozenset({Permissao.PEDIDO_VISUALIZAR})),
                provedor="meta",
                finalidade="whatsapp_token",
                nova_referencia="mapping:x",
            )
