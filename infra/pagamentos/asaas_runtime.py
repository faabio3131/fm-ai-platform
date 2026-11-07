"""Factory Asaas: configuration and credentials belong to tenant+unit Vault."""
from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.pagamentos.asaas import AdapterAsaas, ConfiguracaoAsaas, ErroAsaas
from infra.integracoes.repositorio_sqlalchemy import (
    RepositorioConfiguracoesExternasSQLAlchemy,
)
from infra.seguranca.modelos_orm import CredencialReferenciaORM
from infra.seguranca.segredos_orm import SegredoIntegracaoORM
from infra.seguranca.segredos_sqlalchemy import EncryptedSQLAlchemySecretStore


class AsaasAdapterFactory:
    def __init__(self, *, builder: Callable[[ConfiguracaoAsaas], AdapterAsaas] | None = None) -> None:
        self.builder = builder or AdapterAsaas

    def construir(
        self, *, session: Session, tenant_id: str, unidade_id: str,
        servico: str,
    ) -> AdapterAsaas:
        if servico not in {"pagamentos.pix", "pagamentos.cartao"}:
            raise ErroAsaas("asaas_servico_invalido")
        configs = [
            item for item in RepositorioConfiguracoesExternasSQLAlchemy(session).listar(
                tenant_id=tenant_id, unidade_id=unidade_id
            ) if item.servico == servico
            and item.provedor == "asaas" and item.habilitada
        ]
        if len(configs) != 1:
            raise ErroAsaas("asaas_configuracao_unica_necessaria")
        config = configs[0]
        if (
            config.ambiente.value == "producao"
            and (not config.homologada or not config.evidencia_homologacao_ref)
        ):
            raise ErroAsaas("asaas_producao_nao_homologada")
        env = "production" if config.ambiente.value == "producao" else "sandbox"
        references = dict(config.credenciais)
        vault = EncryptedSQLAlchemySecretStore(session)

        def segredo(role: str) -> str:
            finalidade = references.get(role)
            if not finalidade:
                raise ErroAsaas("asaas_credencial_ausente")
            registro = session.scalar(
                select(CredencialReferenciaORM).where(
                    CredencialReferenciaORM.tenant_id == tenant_id,
                    CredencialReferenciaORM.unidade_id == unidade_id,
                    CredencialReferenciaORM.provedor == "asaas",
                    CredencialReferenciaORM.finalidade == finalidade,
                    CredencialReferenciaORM.ativa.is_(True),
                ).order_by(CredencialReferenciaORM.versao.desc()).limit(1)
            )
            if registro is None or not registro.referencia.startswith("vault:"):
                raise ErroAsaas("asaas_credencial_ausente")
            # A reference stored in this tenant cannot borrow a vault key from another tenant.
            scoped_secret = session.scalar(
                select(SegredoIntegracaoORM).where(
                    SegredoIntegracaoORM.referencia == registro.referencia,
                    SegredoIntegracaoORM.tenant_id == tenant_id,
                    SegredoIntegracaoORM.unidade_id == unidade_id,
                    SegredoIntegracaoORM.provedor == "asaas",
                    SegredoIntegracaoORM.finalidade == finalidade,
                )
            )
            if scoped_secret is None:
                raise ErroAsaas("asaas_credencial_escopo_divergente")
            return vault.resolve(registro.referencia).reveal()

        return self.builder(ConfiguracaoAsaas(
            api_key=segredo("api_key"),
            webhook_token=segredo("webhook_token"),
            ambiente=env,
        ))
