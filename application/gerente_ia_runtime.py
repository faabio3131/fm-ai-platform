"""Composition root de produção do Core/Gerente IA V1."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.assistente_atendimento.servicos import ServicoIdentidadeAssistente
from core.eventos.modelos import EnvelopeMensagem
from core.gerente_ia.erros import ErroGerenteIA
from core.gerente_ia.modelos import ChamadaTool, ToolGerenteIA
from core.gerente_ia.servicos import ServicoGerenteIA
from core.integracoes.modelos import ErroConfiguracaoServico
from core.integracoes.provedores import PortaGeminiTenant
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.segredos import ReferenceSecretStore, SecretStore
from infra.gerente_ia.consultas_sqlalchemy import ConsultasGerenciaisSQLAlchemy
from infra.gerente_ia.persistencia_sqlalchemy import (
    AcoesGerenciaisSQLAlchemy,
    CampanhasGerenciaisSQLAlchemy,
    ConsumidorEventosCoreSQLAlchemy,
    RepositorioIdentidadeAssistenteSQLAlchemy,
    RepositorioPreviewsSQLAlchemy,
)
from infra.integracoes.fabrica_adapters import FabricaAdaptersExternos
from infra.integracoes.modelos_orm import ServicoExternoConfigORM
from infra.seguranca.auditoria_sqlalchemy import RepositorioAuditoriaSQLAlchemy


class PlanejadorLLM(Protocol):
    def planejar(self, *, pergunta: str, nome_assistente: str) -> ChamadaTool: ...


class PlanejadorGeminiCore:
    """LLM tenant-aware limitado a planejar tools; toda autoridade fica no Core."""

    def __init__(
        self,
        *,
        session: Session,
        contexto: ContextoExecucao,
        secret_store: SecretStore | None = None,
        gateway: PortaGeminiTenant | None = None,
    ) -> None:
        self._session = session
        self._contexto = contexto
        self._store = secret_store or ReferenceSecretStore()
        self._gateway = gateway

    def _configuracao_id(self) -> str:
        ids = self._session.scalars(
            select(ServicoExternoConfigORM.configuracao_id)
            .where(
                ServicoExternoConfigORM.tenant_id == self._contexto.tenant_id,
                ServicoExternoConfigORM.unidade_id == self._contexto.unidade_id,
                ServicoExternoConfigORM.servico == "ia.generativa",
                ServicoExternoConfigORM.provedor == "gemini",
                ServicoExternoConfigORM.habilitada.is_(True),
                ServicoExternoConfigORM.homologada.is_(True),
            )
            .order_by(ServicoExternoConfigORM.configuracao_id)
        ).all()
        if len(ids) != 1:
            raise ErroConfiguracaoServico("configuracao_gemini_padrao_ambigua_ou_ausente")
        return ids[0]

    def planejar(self, *, pergunta: str, nome_assistente: str) -> ChamadaTool:
        if not pergunta.strip() or len(pergunta) > 4000:
            raise ErroGerenteIA("pergunta_invalida")
        adapter = FabricaAdaptersExternos(
            session=self._session, secret_store=self._store
        ).gemini(
            contexto=self._contexto,
            configuracao_id=self._configuracao_id(),
            gateway=self._gateway,
        )
        resposta = adapter.gerar(
            {
                "system": (
                    "Você é o planejador do Assistente de Atendimento configurado como "
                    f"{nome_assistente!r}. Responda SOMENTE JSON com as chaves tool e "
                    "argumentos. Nunca inclua tenant_id, unidade_id, usuário, credencial, "
                    "SQL, confirmação ou autorização. Use apenas tools do catálogo V1."
                ),
                "user": pergunta,
                "tools": ", ".join(tool.value for tool in ToolGerenteIA),
            }
        )
        bruto: Any = resposta
        if not isinstance(bruto, (str, dict)):
            bruto = getattr(resposta, "text", None)
        if isinstance(bruto, str):
            texto = bruto.strip()
            if texto.startswith("```"):
                texto = texto.strip("`")
                if texto.startswith("json"):
                    texto = texto[4:].strip()
            try:
                bruto = json.loads(texto)
            except json.JSONDecodeError as exc:
                raise ErroGerenteIA("resposta_llm_invalida") from exc
        if not isinstance(bruto, dict):
            raise ErroGerenteIA("resposta_llm_invalida")
        argumentos = bruto.get("argumentos", {})
        if not isinstance(argumentos, dict):
            raise ErroGerenteIA("resposta_llm_invalida")
        return ChamadaTool.de_dict(str(bruto.get("tool", "")), argumentos)


@dataclass
class RuntimeGerenteIAV1:
    """Runtime real: somente adapters SQLAlchemy e integrações tenant-aware."""

    session: Session
    secret_store: SecretStore | None = None
    planejador_llm: PlanejadorLLM | None = None

    def __post_init__(self) -> None:
        repositorio_identidade = RepositorioIdentidadeAssistenteSQLAlchemy(self.session)
        auditoria = RepositorioAuditoriaSQLAlchemy(self.session)
        self.identidade_assistente = ServicoIdentidadeAssistente(
            repositorio_identidade, auditoria
        )
        self.consumidor_eventos = ConsumidorEventosCoreSQLAlchemy(self.session)
        self.core = ServicoGerenteIA(
            consultas=ConsultasGerenciaisSQLAlchemy(self.session),
            acoes=AcoesGerenciaisSQLAlchemy(self.session),
            campanhas=CampanhasGerenciaisSQLAlchemy(self.session),
            previews=RepositorioPreviewsSQLAlchemy(self.session),
            auditoria=auditoria,
        )

    def executar_tool(self, *, contexto: ContextoExecucao, chamada: ChamadaTool):
        return self.core.executar_tool(contexto=contexto, chamada=chamada)

    def confirmar_acao(self, *, contexto: ContextoExecucao, preview_id: str, fingerprint: str, idempotency_key: str):
        return self.core.confirmar_acao(
            contexto_humano=contexto,
            preview_id=preview_id,
            fingerprint=fingerprint,
            idempotency_key=idempotency_key,
        )

    def consumir_evento(self, mensagem: EnvelopeMensagem) -> bool:
        return self.consumidor_eventos.consumir(mensagem)

    def perguntar(self, *, contexto: ContextoExecucao, pergunta: str):
        identidade = self.identidade_assistente.obter(contexto=contexto)
        planejador = self.planejador_llm or PlanejadorGeminiCore(
            session=self.session,
            contexto=contexto,
            secret_store=self.secret_store,
        )
        chamada = planejador.planejar(
            pergunta=pergunta, nome_assistente=identidade.nome_publico
        )
        resultado = self.core.executar_tool(contexto=contexto, chamada=chamada)
        return identidade, chamada, resultado


def compor_runtime_gerente_ia(
    *,
    session: Session,
    secret_store: SecretStore | None = None,
    planejador_llm: PlanejadorLLM | None = None,
) -> RuntimeGerenteIAV1:
    return RuntimeGerenteIAV1(
        session=session, secret_store=secret_store, planejador_llm=planejador_llm
    )
