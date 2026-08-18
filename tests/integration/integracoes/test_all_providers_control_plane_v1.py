from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from core.integracoes import (
    AmbienteIntegracao,
    EstadoProntidaoServico,
    ServicoConfiguracoesExternas,
)
from core.seguranca.auditoria import RepositorioAuditoriaEmMemoria
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Papel, Permissao
from core.seguranca.segredos import ReferenceSecretStore
from infra.integracoes import (
    IntegrationConfigBase,
    ProntidaoCredenciaisSQLAlchemy,
    RepositorioConfiguracoesExternasSQLAlchemy,
)
from infra.seguranca.credenciais import ServicoCredenciaisReferenciadas
from infra.seguranca.modelos_orm import SecurityBase


def _contexto() -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id="tenant-a",
        unidade_id="loja-1",
        usuario_id="admin-1",
        papeis=frozenset({Papel.ADMINISTRADOR}),
        permissoes=frozenset(Permissao),
        correlation_id="corr-all-providers",
        solicitado_em=datetime.now(timezone.utc),
        origem="tests",
        unidades_permitidas=frozenset({"loja-1"}),
    )


CASOS = (
    (
        "social.facebook",
        "meta",
        {"page_id": "page-1", "app_id": "app-1"},
        ("access_token", "app_secret"),
    ),
    (
        "social.instagram",
        "meta",
        {
            "business_account_id": "ig-business-1",
            "facebook_page_id": "page-1",
            "app_id": "app-1",
        },
        ("access_token", "app_secret"),
    ),
    (
        "mensageria.whatsapp",
        "meta",
        {
            "business_account_id": "waba-1",
            "phone_number_id": "phone-1",
            "app_id": "app-1",
        },
        ("access_token", "app_secret", "webhook_verify_token"),
    ),
    (
        "mapas",
        "google_maps",
        {
            "origin_address": "Rua Exemplo, 100",
            "country_code": "BR",
            "language": "pt-BR",
            "currency": "BRL",
        },
        ("browser_api_key", "server_api_key"),
    ),
    (
        "pagamentos.pix",
        "pagbank",
        {"notification_url": "https://example.test/webhooks/pagbank"},
        ("api_token",),
    ),
    (
        "pagamentos.pix",
        "mercado_pago",
        {"notification_url": "https://example.test/webhooks/mercado-pago"},
        ("access_token", "webhook_secret"),
    ),
    (
        "ia.generativa",
        "gemini",
        {"model": "gemini-test"},
        ("api_key",),
    ),
)


@pytest.mark.parametrize(("servico", "provedor", "parametros", "roles"), CASOS)
def test_todos_provedores_v1_configuram_persistem_e_so_ficam_ativos_apos_homologacao(
    servico: str,
    provedor: str,
    parametros: dict[str, str],
    roles: tuple[str, ...],
) -> None:
    engine = create_engine("sqlite:///:memory:")
    SecurityBase.metadata.create_all(engine)
    IntegrationConfigBase.metadata.create_all(engine)

    mapping: dict[str, str] = {}
    finalidades: dict[str, str] = {}
    for role in roles:
        purpose = f"{servico.replace('.', '_')}_{role}"
        ref_key = f"{provedor}-{servico.replace('.', '-')}-{role}"
        mapping[ref_key] = f"secret-{ref_key}"
        finalidades[role] = purpose

    store = ReferenceSecretStore(mapping=mapping)
    contexto = _contexto()
    config_id = f"{servico}--{provedor}"

    with Session(engine) as session:
        credentials = ServicoCredenciaisReferenciadas(session, store)
        for role, purpose in finalidades.items():
            ref_key = f"{provedor}-{servico.replace('.', '-')}-{role}"
            credentials.rotacionar(
                contexto=contexto,
                provedor=provedor,
                finalidade=purpose,
                nova_referencia=f"mapping:{ref_key}",
            )

        servico_config = ServicoConfiguracoesExternas(
            repositorio=RepositorioConfiguracoesExternasSQLAlchemy(session),
            prontidao_credenciais=ProntidaoCredenciaisSQLAlchemy(session, store),
            auditoria=RepositorioAuditoriaEmMemoria(),
        )
        configuracao = servico_config.configurar(
            contexto=contexto,
            configuracao_id=config_id,
            servico=servico,
            provedor=provedor,
            conta_externa="principal",
            ambiente=AmbienteIntegracao.HOMOLOGACAO,
            parametros_publicos=parametros,
            finalidades_credenciais=finalidades,
            habilitada=True,
            versao_esperada=0,
        )

        persistida = servico_config.obter(
            contexto=contexto, configuracao_id=config_id
        )
        assert persistida == configuracao
        assert (
            servico_config.avaliar(contexto=contexto, configuracao_id=config_id).estado
            is EstadoProntidaoServico.CONFIGURADO
        )

        homologada = servico_config.registrar_homologacao(
            contexto=contexto,
            configuracao_id=config_id,
            evidencia_ref=f"evidence://{provedor}/{servico}/healthcheck",
            versao_esperada=1,
        )
        assert homologada.homologada is True
        assert (
            servico_config.avaliar(contexto=contexto, configuracao_id=config_id).estado
            is EstadoProntidaoServico.PRONTO
        )
