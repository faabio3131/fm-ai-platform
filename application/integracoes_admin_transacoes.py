"""Fronteira transacional da administração de integrações externas."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import TypeVar

from sqlalchemy.orm import Session

from core.integracoes.modelos import (
    AmbienteIntegracao,
    ConfiguracaoServicoExterno,
    ValorParametro,
)
from core.integracoes.servicos import ServicoConfiguracoesExternas
from core.seguranca.contexto import ContextoExecucao
from infra.integracoes.repositorio_sqlalchemy import (
    ProntidaoCredenciaisSQLAlchemy,
    RepositorioConfiguracoesExternasSQLAlchemy,
)
from infra.seguranca.auditoria_sqlalchemy import RepositorioAuditoriaSQLAlchemy
from infra.seguranca.credenciais import ServicoCredenciaisReferenciadas
from infra.seguranca.segredos_sqlalchemy import EncryptedSQLAlchemySecretStore
from infra.transacoes.uow import UnitOfWorkV1

T = TypeVar("T")

SessionFactory = Callable[[], Session]


def _session_ativa(uow: UnitOfWorkV1) -> Session:
    if uow.session is None:
        raise RuntimeError("UnitOfWorkV1 sem Session ativa")

    return uow.session


def _purpose(servico: str, role: str) -> str:
    prefix = servico.replace(".", "_").replace("-", "_")
    return f"{prefix}_{role}"


class AplicacaoIntegracoesAdminV1:
    """Executa writes do control plane de integrações em uma única UoW."""

    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        master_key: str | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._master_key = master_key

    def _executar(
        self,
        acao: Callable[
            [
                ServicoConfiguracoesExternas,
                ServicoCredenciaisReferenciadas,
                EncryptedSQLAlchemySecretStore,
            ],
            T,
        ],
    ) -> T:
        with UnitOfWorkV1(self._session_factory) as uow:
            session = _session_ativa(uow)

            vault = EncryptedSQLAlchemySecretStore(
                session,
                master_key=self._master_key,
            )

            service = ServicoConfiguracoesExternas(
                repositorio=RepositorioConfiguracoesExternasSQLAlchemy(
                    session
                ),
                prontidao_credenciais=ProntidaoCredenciaisSQLAlchemy(
                    session,
                    vault,
                ),
                auditoria=RepositorioAuditoriaSQLAlchemy(
                    session
                ),
            )

            credentials = ServicoCredenciaisReferenciadas(
                session,
                vault,
            )

            resultado = acao(
                service,
                credentials,
                vault,
            )

            uow.commit()

            return resultado

    def salvar_configuracao(
        self,
        contexto: ContextoExecucao,
        *,
        configuracao_id: str,
        servico: str,
        provedor: str,
        conta_externa: str,
        ambiente: AmbienteIntegracao,
        parametros_publicos: Mapping[
            str,
            ValorParametro,
        ],
        finalidades_atuais: Mapping[str, str],
        novos_segredos: Mapping[str, str],
        habilitada: bool,
        versao_esperada: int,
    ) -> tuple[
        ConfiguracaoServicoExterno,
        bool,
    ]:
        def acao(
            service: ServicoConfiguracoesExternas,
            credentials: ServicoCredenciaisReferenciadas,
            vault: EncryptedSQLAlchemySecretStore,
        ) -> tuple[
            ConfiguracaoServicoExterno,
            bool,
        ]:
            finalidades = dict(
                finalidades_atuais
            )

            credencial_rotacionada = False

            for role, value in novos_segredos.items():
                if not value.strip():
                    continue

                credencial_rotacionada = True

                purpose = _purpose(
                    servico,
                    role,
                )

                reference = vault.armazenar(
                    contexto=contexto,
                    provedor=provedor,
                    finalidade=purpose,
                    valor=value,
                )

                credentials.rotacionar(
                    contexto=contexto,
                    provedor=provedor,
                    finalidade=purpose,
                    nova_referencia=reference,
                )

                finalidades[role] = purpose

            configuracao = service.configurar(
                contexto=contexto,
                configuracao_id=configuracao_id,
                servico=servico,
                provedor=provedor,
                conta_externa=conta_externa,
                ambiente=ambiente,
                parametros_publicos=parametros_publicos,
                finalidades_credenciais=finalidades,
                habilitada=habilitada,
                versao_esperada=versao_esperada,
                forcar_rehomologacao=(
                    credencial_rotacionada
                ),
            )

            return (
                configuracao,
                credencial_rotacionada,
            )

        return self._executar(acao)

    def homologar(
        self,
        contexto: ContextoExecucao,
        *,
        configuracao_id: str,
        evidencia_ref: str,
    ) -> ConfiguracaoServicoExterno:
        def acao(
            service: ServicoConfiguracoesExternas,
            _credentials: ServicoCredenciaisReferenciadas,
            _vault: EncryptedSQLAlchemySecretStore,
        ) -> ConfiguracaoServicoExterno:
            atual = service.obter(
                contexto=contexto,
                configuracao_id=configuracao_id,
            )

            return service.registrar_homologacao(
                contexto=contexto,
                configuracao_id=configuracao_id,
                evidencia_ref=evidencia_ref,
                versao_esperada=atual.versao,
            )

        return self._executar(acao)
