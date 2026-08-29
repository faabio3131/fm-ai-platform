"""Composition root de produção do Core/Gerente IA V1."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy.orm import Session

from application.ai_router_runtime import construir_ai_model_router
from core.ai_router import AIModelRouter, CapabilityIA, SolicitacaoIA
from core.assistente_atendimento.servicos import ServicoIdentidadeAssistente
from core.eventos.modelos import EnvelopeMensagem
from core.gerente_ia.erros import ErroGerenteIA
from core.gerente_ia.modelos import ChamadaTool, ToolGerenteIA
from core.gerente_ia.servicos import ServicoGerenteIA
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.segredos import SecretStore
from infra.gerente_ia.campanhas_governadas_sqlalchemy import (
    CampanhasGovernadasSQLAlchemy,
)
from infra.gerente_ia.consultas_sqlalchemy import ConsultasGerenciaisSQLAlchemy
from infra.gerente_ia.persistencia_sqlalchemy import (
    AcoesGerenciaisSQLAlchemy,
    ConsumidorEventosCoreSQLAlchemy,
    RepositorioIdentidadeAssistenteSQLAlchemy,
    RepositorioPreviewsSQLAlchemy,
)
from infra.seguranca.auditoria_sqlalchemy import RepositorioAuditoriaSQLAlchemy


class PlanejadorLLM(Protocol):
    def planejar(
        self,
        *,
        pergunta: str,
        nome_assistente: str,
    ) -> ChamadaTool: ...


class PlanejadorAIRouterCore:
    """Consumidor cognitivo sem conhecimento de provider/modelo concreto."""

    def __init__(
        self,
        *,
        router: AIModelRouter,
        contexto: ContextoExecucao,
    ) -> None:
        self._router = router
        self._contexto = contexto

    def planejar(
        self,
        *,
        pergunta: str,
        nome_assistente: str,
    ) -> ChamadaTool:
        if not pergunta.strip() or len(pergunta) > 4000:
            raise ErroGerenteIA("pergunta_invalida")

        resultado = self._router.executar(
            SolicitacaoIA(
                tenant_id=self._contexto.tenant_id,
                unidade_id=self._contexto.unidade_id,
                request_id=(
                    self._contexto.request_id
                    or self._contexto.correlation_id
                ),
                correlation_id=self._contexto.correlation_id,
                capability=CapabilityIA.TOOL_PLANNING,
                conteudo={
                    "system": (
                        "Você é o planejador do Assistente de Atendimento "
                        f"configurado como {nome_assistente!r}. "
                        "Responda SOMENTE JSON com as chaves tool e argumentos. "
                        "Nunca inclua tenant_id, unidade_id, usuário, credencial, "
                        "SQL, confirmação ou autorização. "
                        "Use apenas tools do catálogo V1."
                    ),
                    "user": pergunta,
                    "tools": ", ".join(
                        tool.value for tool in ToolGerenteIA
                    ),
                },
            )
        )

        bruto: Any = resultado.conteudo

        if isinstance(bruto, str):
            texto = bruto.strip()

            if texto.startswith("```"):
                texto = texto.strip("`")

                if texto.startswith("json"):
                    texto = texto[4:].strip()

            try:
                bruto = json.loads(texto)
            except json.JSONDecodeError as exc:
                raise ErroGerenteIA(
                    "resposta_llm_invalida"
                ) from exc

        if not isinstance(bruto, dict):
            raise ErroGerenteIA("resposta_llm_invalida")

        argumentos = bruto.get("argumentos", {})

        if not isinstance(argumentos, dict):
            raise ErroGerenteIA("resposta_llm_invalida")

        return ChamadaTool.de_dict(
            str(bruto.get("tool", "")),
            argumentos,
        )


@dataclass
class RuntimeGerenteIAV1:
    """Runtime operacional com cognição roteada pelo AI Model Router."""

    session: Session
    secret_store: SecretStore | None = None
    planejador_llm: PlanejadorLLM | None = None
    ai_router: AIModelRouter | None = None

    def __post_init__(self) -> None:
        repositorio_identidade = RepositorioIdentidadeAssistenteSQLAlchemy(
            self.session
        )
        auditoria = RepositorioAuditoriaSQLAlchemy(self.session)

        self.identidade_assistente = ServicoIdentidadeAssistente(
            repositorio_identidade,
            auditoria,
        )

        self.consumidor_eventos = ConsumidorEventosCoreSQLAlchemy(
            self.session
        )

        self.core = ServicoGerenteIA(
            consultas=ConsultasGerenciaisSQLAlchemy(self.session),
            acoes=AcoesGerenciaisSQLAlchemy(self.session),
            campanhas=CampanhasGovernadasSQLAlchemy(self.session),
            previews=RepositorioPreviewsSQLAlchemy(self.session),
            auditoria=auditoria,
        )

    def executar_tool(
        self,
        *,
        contexto: ContextoExecucao,
        chamada: ChamadaTool,
    ):
        return self.core.executar_tool(
            contexto=contexto,
            chamada=chamada,
        )

    def confirmar_acao(
        self,
        *,
        contexto: ContextoExecucao,
        preview_id: str,
        fingerprint: str,
        idempotency_key: str,
    ):
        return self.core.confirmar_acao(
            contexto_humano=contexto,
            preview_id=preview_id,
            fingerprint=fingerprint,
            idempotency_key=idempotency_key,
        )

    def consumir_evento(
        self,
        mensagem: EnvelopeMensagem,
    ) -> bool:
        return self.consumidor_eventos.consumir(mensagem)

    def perguntar(
        self,
        *,
        contexto: ContextoExecucao,
        pergunta: str,
    ):
        identidade = self.identidade_assistente.obter(
            contexto=contexto
        )

        planejador = self.planejador_llm

        if planejador is None:
            router = self.ai_router or construir_ai_model_router(
                session=self.session,
                contexto=contexto,
                secret_store=self.secret_store,
            )

            planejador = PlanejadorAIRouterCore(
                router=router,
                contexto=contexto,
            )

        chamada = planejador.planejar(
            pergunta=pergunta,
            nome_assistente=identidade.nome_publico,
        )

        resultado = self.core.executar_tool(
            contexto=contexto,
            chamada=chamada,
        )

        return identidade, chamada, resultado


def compor_runtime_gerente_ia(
    *,
    session: Session,
    secret_store: SecretStore | None = None,
    planejador_llm: PlanejadorLLM | None = None,
    ai_router: AIModelRouter | None = None,
) -> RuntimeGerenteIAV1:
    return RuntimeGerenteIAV1(
        session=session,
        secret_store=secret_store,
        planejador_llm=planejador_llm,
        ai_router=ai_router,
    )
