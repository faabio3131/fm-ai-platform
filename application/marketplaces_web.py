"""Aplicação Web do WP-012: marketplaces desembocam no Pedido/Central canônicos."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.dominio.ids import TenantId, UnidadeId
from core.dominio.tempo import SystemClock
from core.eventos.modelos import DeadLetter, EnvelopeMensagem, ErroNormalizado
from core.eventos.observabilidade import ColetorMetricasEmMemoria
from core.eventos.repositorios import (
    RegistroInbox,
    RepositorioDLQ,
    RepositorioInbox,
    RepositorioOutboxEmMemoria,
)
from core.integracoes.modelos import ConfiguracaoServicoExterno
from core.marketplaces.adapters import (
    MarketplaceAdapter,
    RegistroAdaptersMarketplace,
)
from core.marketplaces.erros import ErroMarketplace
from core.marketplaces.ifood_http import CredencialIfood
from core.marketplaces.keeta_auth import CredencialKeeta
from core.marketplaces.modelos import (
    IntegracaoMarketplace,
    PlataformaMarketplace,
    ResultadoSincronizacao,
    StatusIntegracao,
)
from core.marketplaces.repositorios import (
    RepositorioIntegracoesMarketplaceEmMemoria,
)
from core.marketplaces.retry import PoliticaRetryMarketplace
from core.marketplaces.runtime import (
    compor_ifood_http_real,
    compor_keeta_opendelivery_real,
)
from core.marketplaces.servicos import ServicoMarketplaces
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.erros import SegredoAusente
from infra.eventos.adaptador_sqlalchemy import (
    RepositorioDLQSQLAlchemy,
    RepositorioInboxSQLAlchemy,
)
from infra.eventos.modelos_orm import InboxEventoORM
from infra.integracoes.repositorio_sqlalchemy import (
    RepositorioConfiguracoesExternasSQLAlchemy,
)
from infra.marketplaces.modelos_orm import PedidoExternoMarketplaceORM
from infra.marketplaces.repositorio_sqlalchemy import (
    PedidosInternosMarketplaceSQLAlchemy,
    RepositorioPedidosExternosSQLAlchemy,
)
from infra.seguranca.modelos_orm import CredencialReferenciaORM
from infra.seguranca.segredos_sqlalchemy import EncryptedSQLAlchemySecretStore

SessionFactory = Callable[[], Session]
SERVICO_MARKETPLACE = "marketplace.pedidos"


@dataclass(frozen=True)
class MarketplaceIntegracaoWeb:
    configuracao_id: str
    plataforma: str
    conta_externa: str
    ambiente: str
    habilitada: bool
    homologada: bool
    evidencia_homologacao_ref: str | None
    pedidos_sincronizados: int
    pronta_para_sincronizar: bool


class _SegredosIfood:
    def __init__(
        self,
        session: Session,
        config: ConfiguracaoServicoExterno,
        vault: EncryptedSQLAlchemySecretStore,
    ) -> None:
        self._session = session
        self._config = config
        self._vault = vault

    def _valor(self, role: str) -> str:
        purpose = self._config.credenciais.get(role)
        if not purpose:
            raise SegredoAusente(f"credencial marketplace ausente: {role}")
        row = self._session.scalar(
            select(CredencialReferenciaORM)
            .where(
                CredencialReferenciaORM.tenant_id == self._config.tenant_id,
                CredencialReferenciaORM.unidade_id == self._config.unidade_id,
                CredencialReferenciaORM.provedor == self._config.provedor,
                CredencialReferenciaORM.finalidade == purpose,
                CredencialReferenciaORM.ativa.is_(True),
            )
            .order_by(CredencialReferenciaORM.versao.desc())
            .limit(1)
        )
        if row is None:
            raise SegredoAusente(f"credencial marketplace ausente: {role}")
        return self._vault.resolve(row.referencia).reveal()

    def obter_ifood(self, segredo_ref: str) -> CredencialIfood:
        if segredo_ref != self._config.configuracao_id:
            raise SegredoAusente("referencia de configuracao marketplace divergente")
        return CredencialIfood(
            client_id=self._valor("client_id"),
            client_secret=self._valor("client_secret"),
        )


class _SegredosKeeta(_SegredosIfood):
    def obter_keeta(self, segredo_ref: str) -> CredencialKeeta:
        if segredo_ref != self._config.configuracao_id:
            raise SegredoAusente("referencia de configuracao marketplace divergente")
        return CredencialKeeta(
            client_id=self._valor("client_id"),
            client_secret=self._valor("client_secret"),
        )


class _InboxMarketplaceSQLAlchemy(RepositorioInbox):
    def __init__(
        self,
        session: Session,
        *,
        tenant_id: str,
        unidade_id: str,
    ) -> None:
        self._session = session
        self._tenant_id = tenant_id
        self._unidade_id = unidade_id
        self._tenant = TenantId(tenant_id)
        self._unidade = UnidadeId(unidade_id)
        self._repo = RepositorioInboxSQLAlchemy(session)
        self._registros: dict[str, RegistroInbox] = {}

    def registrar(
        self,
        mensagem: EnvelopeMensagem,
        recebido_em,
    ) -> RegistroInbox:
        if (
            str(mensagem.tenant_id) != self._tenant_id
            or str(mensagem.unidade_id) != self._unidade_id
        ):
            raise ErroMarketplace("evento_fora_do_escopo")
        self._repo.registrar(mensagem)
        key = str(mensagem.idempotency_key)
        row = self._session.get(
            InboxEventoORM,
            (self._tenant_id, self._unidade_id, key),
        )
        if row is None:
            raise ErroMarketplace("inbox_marketplace_indisponivel")
        registro = RegistroInbox(
            mensagem=mensagem,
            recebido_em=row.received_at,
            processado_em=row.processed_at,
            tentativas=row.attempts,
        )
        self._registros[key] = registro
        return registro

    def ja_processada(self, chave) -> bool:
        return self._repo.ja_processada(
            self._tenant,
            self._unidade,
            chave,
        )

    def marcar_processada(self, chave, instante) -> None:
        self._repo.marcar_processada(
            self._tenant,
            self._unidade,
            chave,
        )
        registro = self._registros.get(str(chave))
        if registro is not None:
            registro.processado_em = instante

    def marcar_falha(self, chave, erro: ErroNormalizado) -> None:
        row = self._session.get(
            InboxEventoORM,
            (self._tenant_id, self._unidade_id, str(chave)),
        )
        if row is None:
            raise KeyError(str(chave))
        row.attempts += 1
        self._session.flush()
        registro = self._registros.get(str(chave))
        if registro is not None:
            registro.tentativas = row.attempts
            registro.ultimo_erro = erro

    def historico(self) -> tuple[RegistroInbox, ...]:
        return tuple(self._registros.values())


class _DLQMarketplaceSQLAlchemy(RepositorioDLQ):
    def __init__(
        self,
        session: Session,
        *,
        tenant_id: str,
        unidade_id: str,
    ) -> None:
        self._repo = RepositorioDLQSQLAlchemy(session)
        self._tenant_id = tenant_id
        self._unidade_id = unidade_id
        self._tenant = TenantId(tenant_id)
        self._unidade = UnidadeId(unidade_id)

    def adicionar(self, item: DeadLetter) -> None:
        if (
            str(item.tenant_id) != self._tenant_id
            or str(item.unidade_id) != self._unidade_id
        ):
            raise ErroMarketplace("dlq_fora_do_escopo")
        self._repo.adicionar(item)

    def listar(self) -> tuple[DeadLetter, ...]:
        return self._repo.listar(self._tenant, self._unidade)


class _AdapterCommitAntesAck:
    """Garante durabilidade do inbox/Pedido antes do ACK ao parceiro."""

    def __init__(self, delegate: MarketplaceAdapter, session: Session) -> None:
        self._delegate = delegate
        self._session = session

    @property
    def plataforma(self):
        return self._delegate.plataforma

    @property
    def capacidades(self):
        return self._delegate.capacidades

    def receber_eventos(self, integracao: IntegracaoMarketplace, *, limite: int = 100):
        return self._delegate.receber_eventos(integracao, limite=limite)

    def reconhecer_eventos(
        self,
        integracao: IntegracaoMarketplace,
        evento_ids: tuple[str, ...],
    ) -> None:
        self._session.commit()
        self._delegate.reconhecer_eventos(integracao, evento_ids)

    def consultar_pedido(self, integracao: IntegracaoMarketplace, pedido_id_externo: str):
        return self._delegate.consultar_pedido(integracao, pedido_id_externo)

    def confirmar(
        self,
        integracao: IntegracaoMarketplace,
        pedido_id_externo: str,
        *,
        idempotency_key: str,
    ) -> None:
        self._delegate.confirmar(
            integracao,
            pedido_id_externo,
            idempotency_key=idempotency_key,
        )

    def rejeitar(
        self,
        integracao: IntegracaoMarketplace,
        pedido_id_externo: str,
        *,
        motivo: str,
        idempotency_key: str,
    ) -> None:
        self._delegate.rejeitar(
            integracao,
            pedido_id_externo,
            motivo=motivo,
            idempotency_key=idempotency_key,
        )

    def atualizar_status(
        self,
        integracao: IntegracaoMarketplace,
        pedido_id_externo: str,
        *,
        status,
        idempotency_key: str,
    ) -> None:
        self._delegate.atualizar_status(
            integracao,
            pedido_id_externo,
            status=status,
            idempotency_key=idempotency_key,
        )

    def cancelar(
        self,
        integracao: IntegracaoMarketplace,
        pedido_id_externo: str,
        *,
        motivo: str,
        idempotency_key: str,
    ) -> None:
        self._delegate.cancelar(
            integracao,
            pedido_id_externo,
            motivo=motivo,
            idempotency_key=idempotency_key,
        )


class AplicacaoMarketplacesWebV1:
    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        master_key: str | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._master_key = master_key

    @staticmethod
    def _configs(
        session: Session,
        contexto: ContextoExecucao,
    ) -> tuple[ConfiguracaoServicoExterno, ...]:
        return tuple(
            config
            for config in RepositorioConfiguracoesExternasSQLAlchemy(session).listar(
                tenant_id=contexto.tenant_id,
                unidade_id=contexto.unidade_id,
            )
            if config.servico == SERVICO_MARKETPLACE
            and config.provedor in {"ifood", "keeta"}
        )

    def listar(self, contexto: ContextoExecucao) -> tuple[MarketplaceIntegracaoWeb, ...]:
        with self._session_factory() as session:
            configs = self._configs(session, contexto)
            resultado: list[MarketplaceIntegracaoWeb] = []
            for config in configs:
                total = session.scalar(
                    select(func.count())
                    .select_from(PedidoExternoMarketplaceORM)
                    .where(
                        PedidoExternoMarketplaceORM.tenant_id == contexto.tenant_id,
                        PedidoExternoMarketplaceORM.unidade_id == contexto.unidade_id,
                        PedidoExternoMarketplaceORM.integracao_id
                        == config.configuracao_id,
                    )
                )
                resultado.append(
                    MarketplaceIntegracaoWeb(
                        configuracao_id=config.configuracao_id,
                        plataforma=config.provedor,
                        conta_externa=config.conta_externa,
                        ambiente=config.ambiente.value,
                        habilitada=config.habilitada,
                        homologada=config.homologada,
                        evidencia_homologacao_ref=config.evidencia_homologacao_ref,
                        pedidos_sincronizados=int(total or 0),
                        pronta_para_sincronizar=bool(
                            config.habilitada
                            and config.homologada
                            and config.evidencia_homologacao_ref
                        ),
                    )
                )
            return tuple(resultado)

    def _config(
        self,
        session: Session,
        contexto: ContextoExecucao,
        configuracao_id: str,
    ) -> ConfiguracaoServicoExterno:
        config = RepositorioConfiguracoesExternasSQLAlchemy(session).obter(
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
            configuracao_id=configuracao_id,
        )
        if (
            config is None
            or config.servico != SERVICO_MARKETPLACE
            or config.provedor not in {"ifood", "keeta"}
        ):
            raise ErroMarketplace("integracao_marketplace_indisponivel")
        if not config.habilitada:
            raise ErroMarketplace("integracao_inativa")
        if not config.homologada or not config.evidencia_homologacao_ref:
            raise ErroMarketplace("marketplace_nao_homologado")
        return config

    def sincronizar(
        self,
        contexto: ContextoExecucao,
        *,
        configuracao_id: str,
        limite: int = 100,
    ) -> ResultadoSincronizacao:
        if limite < 1 or limite > 100:
            raise ErroMarketplace("limite_polling_invalido")

        with self._session_factory() as session:
            config = self._config(session, contexto, configuracao_id)
            vault = EncryptedSQLAlchemySecretStore(
                session,
                master_key=self._master_key,
            )
            delegate: MarketplaceAdapter
            if config.provedor == "ifood":
                plataforma = PlataformaMarketplace.IFOOD
                delegate = compor_ifood_http_real(
                    segredos=_SegredosIfood(session, config, vault)
                )
            else:
                plataforma = PlataformaMarketplace.KEETA
                delegate = compor_keeta_opendelivery_real(
                    segredos=_SegredosKeeta(session, config, vault)
                )

            adapter = _AdapterCommitAntesAck(delegate, session)
            integracao = IntegracaoMarketplace(
                integracao_id=config.configuracao_id,
                tenant_id=contexto.tenant_id,
                unidade_id=contexto.unidade_id,
                plataforma=plataforma,
                conta_externa=config.conta_externa,
                segredo_ref=config.configuracao_id,
                capacidades=adapter.capacidades,
                status=StatusIntegracao.ATIVA,
            )
            integracoes = RepositorioIntegracoesMarketplaceEmMemoria()
            integracoes.adicionar(integracao)
            adapters = RegistroAdaptersMarketplace()
            adapters.registrar(adapter)

            servico = ServicoMarketplaces(
                integracoes=integracoes,
                pedidos_externos=RepositorioPedidosExternosSQLAlchemy(
                    session,
                    tenant_id=contexto.tenant_id,
                    unidade_id=contexto.unidade_id,
                ),
                pedidos_internos=PedidosInternosMarketplaceSQLAlchemy(
                    session,
                    plataforma=plataforma,
                ),
                adapters=adapters,
                inbox=_InboxMarketplaceSQLAlchemy(
                    session,
                    tenant_id=contexto.tenant_id,
                    unidade_id=contexto.unidade_id,
                ),
                outbox=RepositorioOutboxEmMemoria(),
                dlq=_DLQMarketplaceSQLAlchemy(
                    session,
                    tenant_id=contexto.tenant_id,
                    unidade_id=contexto.unidade_id,
                ),
                metricas=ColetorMetricasEmMemoria(),
                clock=SystemClock(),
                retry=PoliticaRetryMarketplace(
                    max_attempts=3,
                    backoff_base_seconds=1,
                    backoff_max_seconds=60,
                ),
            )
            resultado = servico.sincronizar(
                tenant_id=contexto.tenant_id,
                unidade_id=contexto.unidade_id,
                integracao_id=config.configuracao_id,
                limite=limite,
            )
            session.commit()
            return resultado
