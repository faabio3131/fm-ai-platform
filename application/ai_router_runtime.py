"""Composition root provider-specific do AI Model Router.

O Core e seus consumidores recebem somente contratos provider-neutral.
SDK, credenciais e adapters concretos permanecem na borda de infraestrutura.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from core.ai_router import (
    AIModelRouter,
    AIUsageEvent,
    CapabilityIA,
    FalhaRotaDefinitiva,
    FalhaRotaTransitoria,
    MedidorUsoIA,
    RespostaModeloIA,
    RotaIA,
    SolicitacaoIA,
)
from core.integracoes.modelos import ErroConfiguracaoServico
from core.integracoes.provedores import (
    ErroProvedorExterno,
    ErroProvedorTransitorio,
    PortaGeminiTenant,
)
from core.seguranca.auditoria import EventoAuditoria, sanitizar_metadata
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.segredos import ReferenceSecretStore, SecretStore
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
    if isinstance(
        resposta,
        (str, dict, list, int, float, bool, type(None)),
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
        gemini_gateway: PortaGeminiTenant | None = None,
    ) -> None:
        self._session = session
        self._contexto = contexto
        self._secret_store = secret_store
        self._gemini_gateway = gemini_gateway

    def executar(
        self,
        *,
        rota: RotaIA,
        solicitacao: SolicitacaoIA,
    ) -> RespostaModeloIA:
        if rota.provider != "gemini":
            raise FalhaRotaDefinitiva(
                "ai_router.provider_adapter_indisponivel"
            )

        try:
            adapter = FabricaAdaptersExternos(
                session=self._session,
                secret_store=self._secret_store,
            ).gemini(
                contexto=self._contexto,
                configuracao_id=rota.configuracao_id,
                gateway=self._gemini_gateway,
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


def _capability(
    *,
    provider: str,
    parametros: dict[str, Any],
) -> CapabilityIA:
    raw = parametros.get("capability")

    if raw is None and provider == "gemini":
        # Compatibilidade explícita do primeiro cutover.
        return CapabilityIA.TOOL_PLANNING

    try:
        return CapabilityIA(str(raw))
    except ValueError as exc:
        raise ErroConfiguracaoServico(
            "ai_route_capability_invalida"
        ) from exc


def _prioridade(parametros: dict[str, Any]) -> int:
    raw = parametros.get("route_priority", 100)

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


def _rotas_homologadas(
    *,
    session: Session,
    contexto: ContextoExecucao,
) -> tuple[RotaIA, ...]:
    configs = RepositorioConfiguracoesExternasSQLAlchemy(
        session
    ).listar(
        tenant_id=contexto.tenant_id,
        unidade_id=contexto.unidade_id,
    )

    rotas: list[RotaIA] = []

    for config in configs:
        if config.servico != "ia.generativa":
            continue

        if not config.habilitada or not config.homologada:
            continue

        # SD-1F.1B possui adapter produtivo somente Gemini.
        if config.provedor != "gemini":
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

        rotas.append(
            RotaIA(
                configuracao_id=config.configuracao_id,
                provider=config.provedor,
                model=model,
                capability=_capability(
                    provider=config.provedor,
                    parametros=parametros,
                ),
                prioridade=_prioridade(parametros),
                price_snapshot_id=snapshot,
            )
        )

    return tuple(rotas)


def construir_ai_model_router(
    *,
    session: Session,
    contexto: ContextoExecucao,
    secret_store: SecretStore | None = None,
    gemini_gateway: PortaGeminiTenant | None = None,
    metering: MedidorUsoIA | None = None,
) -> AIModelRouter:
    store = secret_store or ReferenceSecretStore()

    return AIModelRouter(
        rotas=_rotas_homologadas(
            session=session,
            contexto=contexto,
        ),
        executor=ExecutorControlPlaneIA(
            session=session,
            contexto=contexto,
            secret_store=store,
            gemini_gateway=gemini_gateway,
        ),
        metering=(
            metering
            or AIUsageAuditMetering(
                session=session,
                contexto=contexto,
            )
        ),
    )
