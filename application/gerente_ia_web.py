"""Fronteira transacional session-aware do Gerente IA para a Web V1.

Não autentica novamente nem recria regras do domínio: recebe o ContextoExecucao já
resolvido pela sessão assinada e delega ao runtime/canonical Core existente.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from application.ai_router_runtime import construir_ai_model_router
from application.gerente_ia_runtime import compor_runtime_gerente_ia
from core.ai_router import CapabilityIA, ConteudoAudioIA, SolicitacaoIA
from core.gerente_ia.erros import ErroGerenteIA
from core.gerente_ia.modelos import ChamadaTool
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.segredos import ReferenceSecretStore, SecretStore
from infra.seguranca.segredos_sqlalchemy import EncryptedSQLAlchemySecretStore
from infra.transacoes.uow import UnitOfWorkV1


class _RuntimeProviderSecretStore:
    """Resolve vault only on demand, preserving env refs in test and legacy flows."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._environment = ReferenceSecretStore()

    def resolve(self, reference: str):
        if reference.startswith("vault:"):
            return EncryptedSQLAlchemySecretStore(self._session).resolve(reference)
        return self._environment.resolve(reference)


class AplicacaoGerenteIAWebV1:
    def __init__(
        self,
        session_factory: Callable[[], Session],
        *,
        secret_store: SecretStore | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._secret_store = secret_store

    @staticmethod
    def _session(uow: UnitOfWorkV1) -> Session:
        if uow.session is None:
            raise RuntimeError("UnitOfWorkV1 sem Session ativa")
        return uow.session

    def executar_tool(
        self,
        *,
        contexto: ContextoExecucao,
        chamada: ChamadaTool,
    ) -> Any:
        with UnitOfWorkV1(self._session_factory) as uow:
            runtime = compor_runtime_gerente_ia(
                session=self._session(uow),
                secret_store=self._secret_store or _RuntimeProviderSecretStore(self._session(uow)),
            )
            resultado = runtime.executar_tool(contexto=contexto, chamada=chamada)
            uow.commit()
            return resultado

    def perguntar(
        self,
        *,
        contexto: ContextoExecucao,
        pergunta: str,
    ) -> tuple[Any, ChamadaTool, Any]:
        with UnitOfWorkV1(self._session_factory) as uow:
            runtime = compor_runtime_gerente_ia(
                session=self._session(uow),
                secret_store=self._secret_store or _RuntimeProviderSecretStore(self._session(uow)),
            )
            identidade, chamada, resultado = runtime.perguntar(
                contexto=contexto,
                pergunta=pergunta,
            )
            uow.commit()
            return identidade, chamada, resultado

    def transcrever_audio(
        self,
        *,
        contexto: ContextoExecucao,
        audio: bytes,
        mime_type: str,
        request_id: str,
    ) -> str:
        if not audio:
            raise ValueError("gerente_ia.audio_vazio")
        if not mime_type.strip():
            raise ValueError("gerente_ia.audio_mime_ausente")
        with UnitOfWorkV1(self._session_factory) as uow:
            session = self._session(uow)
            router = construir_ai_model_router(
                session=session,
                contexto=contexto,
                secret_store=self._secret_store or _RuntimeProviderSecretStore(self._session(uow)),
            )
            resposta = router.executar(
                SolicitacaoIA(
                    tenant_id=contexto.tenant_id,
                    unidade_id=contexto.unidade_id,
                    request_id=request_id,
                    correlation_id=contexto.correlation_id,
                    capability=CapabilityIA.ATENDIMENTO_TRANSCRICAO,
                    conteudo=ConteudoAudioIA(
                        audio=audio,
                        mime_type=mime_type,
                        instrucao=(
                            "Transcreva fielmente esta pergunta falada ao Gerente IA "
                            "em português. Retorne somente a transcrição, sem resumo, "
                            "sem resposta e sem adicionar informações."
                        ),
                    ),
                )
            )
            texto = str(resposta.conteudo).strip()
            if not texto:
                raise ErroGerenteIA("transcricao_audio_vazia")
            uow.commit()
            return texto

    def confirmar_acao(
        self,
        *,
        contexto: ContextoExecucao,
        preview_id: str,
        fingerprint: str,
        idempotency_key: str,
    ) -> Any:
        with UnitOfWorkV1(self._session_factory) as uow:
            runtime = compor_runtime_gerente_ia(
                session=self._session(uow),
                secret_store=self._secret_store or _RuntimeProviderSecretStore(self._session(uow)),
            )
            resultado = runtime.confirmar_acao(
                contexto=contexto,
                preview_id=preview_id,
                fingerprint=fingerprint,
                idempotency_key=idempotency_key,
            )
            uow.commit()
            return resultado
