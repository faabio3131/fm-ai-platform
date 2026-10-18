"""Composition root provider-specific do AI Model Router.

O Core e seus consumidores recebem somente contratos provider-neutral.
SDK, credenciais e adapters concretos permanecem na borda de infraestrutura.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from application.ai_pricing_runtime import montar_catalogo_precos_ia
from core.ai_pricing import CatalogoPrecosIA, ErroPricingCatalog
from core.ai_router import (
    AIModelRouter,
    AIUsageEvent,
    CapabilityIA,
    FalhaRotaDefinitiva,
    FalhaRotaTransitoria,
    GuardaConsumoIA,
    MedidorUsoIA,
    RespostaModeloIA,
    RotaIA,
    SolicitacaoIA,
)
from core.integracoes.modelos import ErroConfiguracaoServico
from core.integracoes.platform_scope import (
    FM_PLATFORM_TENANT_ID,
    FM_PLATFORM_UNIT_ID,
)
from core.integracoes.provedores import (
    ErroProvedorExterno,
    ErroProvedorTransitorio,
    PortaGeminiTenant,
    PortaOpenAITenant,
)
from core.seguranca.auditoria import EventoAuditoria, sanitizar_metadata
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.segredos import ReferenceSecretStore, SecretStore
from infra.ai_budget_guard import AIFranchiseBudgetGuard
from infra.ai_budget_policy_resolver import ResolverPoliticaFranquiaLocal
from infra.ai_budget_sqlalchemy import LedgerFranquiasIASQLAlchemy, OrcamentoIndisponivelIA
from infra.ai_metering import AIUsageDurableMetering
from infra.integracoes.fabrica_adapters import FabricaAdaptersExternos
from infra.integracoes.repositorio_sqlalchemy import (
    RepositorioConfiguracoesExternasSQLAlchemy,
)
from infra.seguranca.auditoria_sqlalchemy import RepositorioAuditoriaSQLAlchemy

LEGACY_UNPRICED_SNAPSHOT = "legacy-unpriced-v1"


def _inteiro_opcional(valor: Any) -> int | None:
    if valor is None:
        return None

    try:
        resultado = int(valor)
    except (TypeError, ValueError):
        return None

    return resultado if resultado >= 0 else None


def _usage_metadata(
    resposta: Any,
) -> tuple[int | None, int | None, int | None]:
    usage = getattr(resposta, "usage_metadata", None)

    if usage is None and isinstance(resposta, dict):
        usage = resposta.get("usage_metadata")

    if usage is None:
        return None, None, None

    def obter(nome: str) -> Any:
        if isinstance(usage, dict):
            return usage.get(nome)
        return getattr(usage, nome, None)

    return (
        _inteiro_opcional(obter("prompt_token_count")),
        _inteiro_opcional(obter("candidates_token_count")),
        _inteiro_opcional(obter("cached_content_token_count")),
    )


def _conteudo_neutro(resposta: Any) -> Any:
    if isinstance(resposta, dict):
        texto_dict = resposta.get("text")
        if isinstance(texto_dict, str):
            return texto_dict
        return resposta

    if isinstance(
        resposta,
        (str, list, int, float, bool, type(None)),
    ):
        return resposta

    texto = getattr(resposta, "text", None)

    if isinstance(texto, str):
        return texto

    raise FalhaRotaDefinitiva(
        "ai_router.resposta_provider_invalida"
    )


class ExecutorControlPlaneIA:
    """Executa uma rota canônica usando o adapter homologado do provider."""

    def __init__(
        self,
        *,
        session: Session,
        contexto: ContextoExecucao,
        secret_store: SecretStore,
        session_factory: Callable[[], Session] | None = None,
        gemini_gateway: PortaGeminiTenant | None = None,
        openai_gateway: PortaOpenAITenant | None = None,
    ) -> None:
        self._session = session
        self._session_factory = session_factory
        self._contexto = contexto
        self._secret_store = secret_store
        self._gemini_gateway = gemini_gateway
        self._openai_gateway = openai_gateway

    def _preparar_adapter(self, *, session: Session, rota: RotaIA):
        # Vault e configuração devem usar a MESMA sessão curta.
        store = self._secret_store
        for_session = getattr(store, "for_session", None)
        if callable(for_session):
            store = for_session(session)
        factory = FabricaAdaptersExternos(
            session=session,
            secret_store=store,
        )
        if rota.provider == "openai":
            return factory.openai(
                contexto=self._contexto,
                configuracao_id=rota.configuracao_id,
                gateway=self._openai_gateway,
            )
        if rota.provider == "gemini":
            return factory.gemini(
                contexto=self._contexto,
                configuracao_id=rota.configuracao_id,
                gateway=self._gemini_gateway,
            )
        raise FalhaRotaDefinitiva(
            "ai_router.provider_adapter_indisponivel"
        )

    def executar(
        self,
        *,
        rota: RotaIA,
        solicitacao: SolicitacaoIA,
    ) -> RespostaModeloIA:
        try:
            # Os adapters resolvem configuração e credencial no banco, mas a
            # chamada de rede ocorre SOMENTE depois de devolver a conexão.
            if self._session_factory is None:
                adapter = self._preparar_adapter(
                    session=self._session,
                    rota=rota,
                )
                resposta = adapter.gerar(solicitacao.conteudo)
            else:
                with self._session_factory() as session:
                    adapter = self._preparar_adapter(
                        session=session,
                        rota=rota,
                    )
                resposta = adapter.gerar(solicitacao.conteudo)

        except ErroProvedorTransitorio as exc:
            raise FalhaRotaTransitoria(
                "ai_router.provider_transient_failure"
            ) from exc

        except (ErroConfiguracaoServico, ErroProvedorExterno) as exc:
            raise FalhaRotaDefinitiva(
                "ai_router.provider_definitive_failure"
            ) from exc

        input_tokens, output_tokens, cached_tokens = _usage_metadata(
            resposta
        )

        return RespostaModeloIA(
            conteudo=_conteudo_neutro(resposta),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
        )


class AIUsageAuditMetering:
    """Sink provisório estruturado até o read model dedicado do AI FinOps."""

    def __init__(
        self,
        *,
        session: Session,
        contexto: ContextoExecucao,
    ) -> None:
        self._repo = RepositorioAuditoriaSQLAlchemy(session)
        self._contexto = contexto

    def registrar(self, evento: AIUsageEvent) -> None:
        papel = (
            min(
                self._contexto.papeis,
                key=lambda item: item.value,
            )
            if self._contexto.papeis
            else None
        )

        metadata = sanitizar_metadata(
            {
                "provider": evento.provider,
                "model": evento.model,
                "capability": evento.capability.value,
                "latency_ms": evento.latency_ms,
                "fallback_used": evento.fallback_used,
                "fallback_reason": evento.fallback_reason,
                "input_units": evento.input_tokens,
                "output_units": evento.output_tokens,
                "cached_units": evento.cached_tokens,
                "usage_unit": "tokens",
                "price_snapshot_id": evento.price_snapshot_id,
            },
            rejeitar=True,
        )

        self._repo.adicionar(
            EventoAuditoria(
                audit_id=str(uuid4()),
                tenant_id=evento.tenant_id,
                unidade_id=evento.unidade_id,
                usuario_id=self._contexto.usuario_id,
                papel_efetivo=papel,
                acao="ai.route.attempt",
                recurso_tipo="ai_model_route",
                recurso_id=evento.request_id,
                resultado=evento.outcome.value,
                motivo=evento.route_reason,
                correlation_id=evento.correlation_id,
                timestamp=evento.timestamp,
                origem="ai_model_router",
                politica="sd1f_ai_model_router_v1",
                causation_id=self._contexto.causation_id,
                metadata=metadata,
            )
        )


def _capabilities(
    *,
    provider: str,
    parametros: dict[str, Any],
) -> tuple[CapabilityIA, ...]:
    raw = parametros.get("capability")

    if raw is None and provider == "openai":
        # GPT-5.6 Luna assume as capacidades textuais de maior volume.
        # Áudio não é anunciado aqui porque o modelo não aceita áudio como entrada.
        return (
            CapabilityIA.TOOL_PLANNING,
            CapabilityIA.ATENDIMENTO_INTERPRETACAO,
        )

    if raw is None and provider == "gemini":
        # Compatibilidade/fallback: Gemini continua cobrindo texto e áudio enquanto
        # a transcrição dedicada não for migrada para um modelo OpenAI de áudio.
        return (
            CapabilityIA.TOOL_PLANNING,
            CapabilityIA.ATENDIMENTO_INTERPRETACAO,
            CapabilityIA.ATENDIMENTO_TRANSCRICAO,
            CapabilityIA.ESTOQUE_LEITURA_DOCUMENTAL,
            CapabilityIA.ATENDIMENTO_DIAGNOSTICO_GEMINI,
        )

    try:
        return (CapabilityIA(str(raw)),)
    except ValueError as exc:
        raise ErroConfiguracaoServico(
            "ai_route_capability_invalida"
        ) from exc


def _prioridade(*, provider: str, parametros: dict[str, Any]) -> int:
    default = 200 if provider == "openai" else 100
    raw = parametros.get("route_priority", default)

    if isinstance(raw, bool):
        raise ErroConfiguracaoServico(
            "ai_route_priority_invalida"
        )

    try:
        valor = int(raw)
    except (TypeError, ValueError) as exc:
        raise ErroConfiguracaoServico(
            "ai_route_priority_invalida"
        ) from exc

    if not 0 <= valor <= 10_000:
        raise ErroConfiguracaoServico(
            "ai_route_priority_invalida"
        )

    return valor


def _configs_ia_resolvidas(
    *,
    repo: RepositorioConfiguracoesExternasSQLAlchemy,
    contexto: ContextoExecucao,
    provider: str,
):
    """Resolve autoridade central preservando IDs legados por tenant."""

    configuracao_id_canonico = f"ia.generativa--{provider}"
    central = repo.obter(
        tenant_id=FM_PLATFORM_TENANT_ID,
        unidade_id=FM_PLATFORM_UNIT_ID,
        configuracao_id=configuracao_id_canonico,
    )
    if central is not None:
        # A existência da autoridade central encerra o fallback legado,
        # mesmo se estiver desabilitada ou ainda não homologada.
        return (central,)

    locais = tuple(
        config
        for config in repo.listar(
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
        )
        if config.servico == "ia.generativa"
        and config.provedor == provider
    )
    if locais:
        return locais

    candidatos = tuple(
        config
        for config in repo.listar_homologadas_por_configuracao_id(
            configuracao_id=configuracao_id_canonico,
        )
        if not (
            config.tenant_id == FM_PLATFORM_TENANT_ID
            and config.unidade_id == FM_PLATFORM_UNIT_ID
        )
    )
    if not candidatos:
        return ()
    if len(candidatos) != 1:
        raise ErroConfiguracaoServico(
            "configuracao_plataforma_legada_ambigua"
        )
    return candidatos


def _rotas_homologadas(
    *,
    session: Session,
    contexto: ContextoExecucao,
) -> tuple[RotaIA, ...]:
    repo = RepositorioConfiguracoesExternasSQLAlchemy(session)
    configs = tuple(
        config
        for provider in ("openai", "gemini")
        for config in _configs_ia_resolvidas(
            repo=repo,
            contexto=contexto,
            provider=provider,
        )
    )

    rotas: list[RotaIA] = []

    for config in configs:
        if config.servico != "ia.generativa":
            continue

        # A presença de uma configuração canônica desabilitada/não homologada
        # bloqueia a rota; não fazemos fallback silencioso para credencial antiga.
        if not config.habilitada or not config.homologada:
            continue

        if config.provedor not in {"openai", "gemini"}:
            continue

        parametros = config.parametros
        model = str(parametros.get("model") or "").strip()

        if not model:
            raise ErroConfiguracaoServico(
                "ai_route_model_ausente"
            )

        snapshot = str(
            parametros.get("price_snapshot_id")
            or LEGACY_UNPRICED_SNAPSHOT
        ).strip()

        for capability in _capabilities(
            provider=config.provedor,
            parametros=parametros,
        ):
            rotas.append(
                RotaIA(
                    configuracao_id=config.configuracao_id,
                    provider=config.provedor,
                    model=model,
                    capability=capability,
                    prioridade=_prioridade(
                        provider=config.provedor,
                        parametros=parametros,
                    ),
                    price_snapshot_id=snapshot,
                )
            )

    return tuple(rotas)



def _metering_session_factory(session: Session) -> Callable[[], Session]:
    """Cria UoW exclusiva do metering; nunca reutiliza a transação de negócio."""

    bind = session.get_bind()
    if not isinstance(bind, Engine):
        raise TypeError("ai_metering.engine_independente_obrigatorio")

    factory = sessionmaker(
        bind=bind,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )
    return factory


def construir_ai_model_router(
    *,
    session: Session,
    contexto: ContextoExecucao,
    secret_store: SecretStore | None = None,
    gemini_gateway: PortaGeminiTenant | None = None,
    openai_gateway: PortaOpenAITenant | None = None,
    metering: MedidorUsoIA | None = None,
    pricing_catalog: CatalogoPrecosIA | None = None,
    budget_guard: GuardaConsumoIA | None = None,
    require_budget_guard: bool = False,
) -> AIModelRouter:
    store = secret_store or ReferenceSecretStore()
    isolated_session_factory = _metering_session_factory(session)
    rotas = _rotas_homologadas(session=session, contexto=contexto)

    # Os rate cards são fornecidos pelo Command na configuração do provider
    # e materializados em memória. Nenhum preço é fixo no código.
    catalog = pricing_catalog
    if catalog is None:
        repo = RepositorioConfiguracoesExternasSQLAlchemy(session)
        configs = tuple(
            config
            for provider in ("openai", "gemini")
            for config in _configs_ia_resolvidas(
                repo=repo, contexto=contexto, provider=provider,
            )
        )
        catalog = montar_catalogo_precos_ia(
            rotas=rotas, configuracoes=configs,
        )

    enforce = require_budget_guard or (
        os.environ.get("FM_AI_FRANCHISE_ENFORCEMENT_ENABLED", "") == "1"
    )
    resolved_guard = budget_guard
    if enforce:
        if catalog is None:
            raise OrcamentoIndisponivelIA("ai_catalogo_precos_obrigatorio")
        # Se uma rota/fallback não tiver rate card vigente, não podemos
        # garantir o limite financeiro; não iniciamos nenhum gasto.
        def validar_tarifa(solicitacao: SolicitacaoIA, rota: RotaIA):
            assert catalog is not None
            try:
                snap = catalog.obter_snapshot(
                    price_snapshot_id=rota.price_snapshot_id
                )
                if (
                    snap.provider != rota.provider
                    or snap.model != rota.model
                    or snap.moeda != "USD"
                    or snap.modalidade != "text_tokens"
                    or not snap.vigente_em(datetime.now(timezone.utc))
                ):
                    raise OrcamentoIndisponivelIA(
                        "ai_tarifa_incompativel_ou_vencida"
                    )
            except ErroPricingCatalog as exc:
                raise OrcamentoIndisponivelIA(
                    "ai_tarifa_nao_configurada"
                ) from exc
            return ResolverPoliticaFranquiaLocal(
                isolated_session_factory
            )(solicitacao, rota)

        if resolved_guard is None:
            resolved_guard = AIFranchiseBudgetGuard(
                ledger=LedgerFranquiasIASQLAlchemy(isolated_session_factory),
                resolver_politica_local=validar_tarifa,
            )

    return AIModelRouter(
        pricing_catalog=catalog,
        budget_guard=resolved_guard,
        require_budget_guard=enforce,
        rotas=rotas,
        executor=ExecutorControlPlaneIA(
            session=session,
            contexto=contexto,
            secret_store=store,
            session_factory=isolated_session_factory,
            gemini_gateway=gemini_gateway,
            openai_gateway=openai_gateway,
        ),
        metering=(
            metering
            or AIUsageDurableMetering(
                isolated_session_factory
            )
        ),
    )
