"""Application administrativa Web do Assistente de Atendimento V1.

Mantém o adaptador HTTP fino e concentra consultas/mutações administrativas
sobre as autoridades canônicas já existentes do Assistente de Atendimento.
"""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from application.assistente_handoff_transacoes import HandoffAssistenteTransacionalV1
from core.assistente_atendimento.atendimento_modelos import EstadoAtendimento
from core.assistente_atendimento.modelos import ConfiguracaoIdentidadeAssistente
from core.assistente_atendimento.servicos import ServicoIdentidadeAssistente
from core.seguranca.autorizacao import AutorizarAcao
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Permissao
from infra.assistente_atendimento.canal_estado_sqlalchemy import (
    EncryptedSQLAlchemyChannelStateStore,
    EstadoCanalPersistido,
)
from infra.assistente_atendimento.canal_schema import assistente_canal_conversas_v1
from infra.gerente_ia.persistencia_sqlalchemy import (
    RepositorioIdentidadeAssistenteSQLAlchemy,
)
from infra.seguranca.auditoria_sqlalchemy import RepositorioAuditoriaSQLAlchemy
from infra.transacoes.uow import UnitOfWorkV1

SessionFactory = Callable[[], Session]


@dataclass(frozen=True)
class ConversaResumoAdmin:
    conversa_id: str
    estado: str
    pedido_id: str | None
    pagamento_id: str | None
    entrega_id: str | None
    versao: int
    atualizado_em: datetime


@dataclass(frozen=True)
class ConversaDetalheAdmin:
    conversa_id: str
    estado: str
    pedido_id: str | None
    pagamento_id: str | None
    entrega_id: str | None
    ultimo_inbound_id: str | None
    ultimo_outbound_id: str | None
    versao: int
    handoff_contexto: dict[str, str | int | bool] | None


def _utc(valor: datetime) -> datetime:
    if valor.tzinfo is None:
        return valor.replace(tzinfo=timezone.utc)
    return valor.astimezone(timezone.utc)


def _normalizar_motivo(motivo: str) -> str:
    normalizado = " ".join(motivo.split())
    if len(normalizado) < 3 or len(normalizado) > 240:
        raise ValueError("motivo_handoff_invalido")
    return normalizado


def _estado_runtime_handoff(
    state: dict[str, Any] | None,
    *,
    motivo: str,
) -> dict[str, Any]:
    if state is None:
        raise RuntimeError("estado_canal_sem_runtime_para_handoff")

    payload = deepcopy(state)
    resultado = payload.get("resultado")
    if not isinstance(resultado, dict):
        raise TypeError("estado_canal_sem_resultado_para_handoff")

    resultado["estado"] = EstadoAtendimento.HANDOFF_HUMANO.value
    resultado["handoff_motivo"] = motivo
    resultado["mensagem"] = (
        "Este atendimento foi encaminhado para uma pessoa da equipe. "
        "O assistente automático permanecerá pausado nesta conversa."
    )

    auditoria = resultado.get("auditoria")
    if isinstance(auditoria, list):
        auditoria.append(["handoff", motivo])
    else:
        resultado["auditoria"] = [["handoff", motivo]]

    return payload


class AplicacaoAssistenteAtendimentoAdminV1:
    """Fronteira administrativa do Assistente de Atendimento para a Web."""

    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        master_key: str | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._master_key = master_key
        self._handoff = HandoffAssistenteTransacionalV1(session_factory)
        self._autorizador = AutorizarAcao()

    def _autorizar(
        self,
        *,
        contexto: ContextoExecucao,
        permissao: Permissao,
        recurso: str,
    ) -> None:
        decisao = self._autorizador.executar(
            contexto=contexto,
            permissao=permissao,
            recurso=recurso,
            tenant_recurso=contexto.tenant_id,
            unidade_recurso=contexto.unidade_id,
        )
        if not decisao.autorizado:
            raise PermissionError(decisao.codigo)

    def _store(self, session: Session) -> EncryptedSQLAlchemyChannelStateStore:
        return EncryptedSQLAlchemyChannelStateStore(
            session,
            master_key=self._master_key,
        )

    def obter_identidade(
        self,
        *,
        contexto: ContextoExecucao,
    ) -> ConfiguracaoIdentidadeAssistente:
        self._autorizar(
            contexto=contexto,
            permissao=Permissao.ATENDIMENTO_VISUALIZAR,
            recurso="identidade_assistente_atendimento",
        )
        with self._session_factory() as session:
            servico = ServicoIdentidadeAssistente(
                RepositorioIdentidadeAssistenteSQLAlchemy(session)
            )
            return servico.obter(contexto=contexto)

    def configurar_identidade(
        self,
        *,
        contexto: ContextoExecucao,
        nome_publico: str,
        atributos: dict[str, Any],
        versao_esperada: int | None,
    ) -> ConfiguracaoIdentidadeAssistente:
        self._autorizar(
            contexto=contexto,
            permissao=Permissao.ATENDIMENTO_GERENCIAR,
            recurso="identidade_assistente_atendimento",
        )
        session = self._session_factory()
        uow = UnitOfWorkV1.adotar_session(session)
        try:
            repositorio = RepositorioIdentidadeAssistenteSQLAlchemy(session)
            existente = repositorio.obter(
                tenant_id=contexto.tenant_id,
                unidade_id=contexto.unidade_id,
            )
            # A leitura canônica devolve fallback v1 antes da primeira persistência.
            # Aceitamos essa versão somente no bootstrap e convertemos para criação.
            versao_persistida = versao_esperada
            if existente is None and versao_esperada in (None, 1):
                versao_persistida = None

            servico = ServicoIdentidadeAssistente(
                repositorio,
                RepositorioAuditoriaSQLAlchemy(session),
            )
            configuracao = servico.configurar(
                contexto=contexto,
                nome_publico=nome_publico,
                atributos=atributos,
                versao_esperada=versao_persistida,
            )
            uow.commit()
            return configuracao
        except Exception:
            uow.rollback()
            raise
        finally:
            session.close()

    def listar_conversas(
        self,
        *,
        contexto: ContextoExecucao,
        limite: int = 100,
    ) -> tuple[ConversaResumoAdmin, ...]:
        self._autorizar(
            contexto=contexto,
            permissao=Permissao.ATENDIMENTO_VISUALIZAR,
            recurso="conversa_atendimento",
        )
        if limite < 1 or limite > 500:
            raise ValueError("limite_conversas_invalido")

        tabela = assistente_canal_conversas_v1
        with self._session_factory() as session:
            rows = session.execute(
                select(
                    tabela.c.conversa_id,
                    tabela.c.estado,
                    tabela.c.pedido_id,
                    tabela.c.pagamento_id,
                    tabela.c.entrega_id,
                    tabela.c.versao,
                    tabela.c.atualizado_em,
                )
                .where(
                    tabela.c.tenant_id == contexto.tenant_id,
                    tabela.c.unidade_id == contexto.unidade_id,
                )
                .order_by(tabela.c.atualizado_em.desc(), tabela.c.conversa_id)
                .limit(limite)
            ).mappings().all()

        return tuple(
            ConversaResumoAdmin(
                conversa_id=str(row["conversa_id"]),
                estado=str(row["estado"]),
                pedido_id=str(row["pedido_id"]) if row["pedido_id"] else None,
                pagamento_id=(
                    str(row["pagamento_id"]) if row["pagamento_id"] else None
                ),
                entrega_id=str(row["entrega_id"]) if row["entrega_id"] else None,
                versao=int(row["versao"]),
                atualizado_em=_utc(row["atualizado_em"]),
            )
            for row in rows
        )

    def obter_conversa(
        self,
        *,
        contexto: ContextoExecucao,
        conversa_id: str,
    ) -> ConversaDetalheAdmin:
        self._autorizar(
            contexto=contexto,
            permissao=Permissao.ATENDIMENTO_VISUALIZAR,
            recurso="conversa_atendimento",
        )
        with self._session_factory() as session:
            estado = self._store(session).obter_por_conversa(
                contexto=contexto,
                conversa_id=conversa_id,
            )
        if estado is None:
            raise LookupError("conversa_nao_encontrada")

        return self._detalhe(
            estado,
            handoff_contexto=self._handoff.ultimo_contexto(
                contexto=contexto,
                conversa_id=conversa_id,
            ),
        )

    def forcar_handoff(
        self,
        *,
        contexto: ContextoExecucao,
        conversa_id: str,
        motivo: str,
    ) -> None:
        self._autorizar(
            contexto=contexto,
            permissao=Permissao.ATENDIMENTO_GERENCIAR,
            recurso="conversa_atendimento",
        )
        motivo_normalizado = _normalizar_motivo(motivo)

        with self._session_factory() as session:
            atual = self._store(session).obter_por_conversa(
                contexto=contexto,
                conversa_id=conversa_id,
            )
        if atual is None:
            raise LookupError("conversa_nao_encontrada")
        if atual.estado == EstadoAtendimento.HANDOFF_HUMANO.value:
            return
        # Valida o payload antes de registrar o handoff auditável.
        _estado_runtime_handoff(atual.state, motivo=motivo_normalizado)

        self._handoff.registrar(
            contexto=contexto,
            conversa_id=conversa_id,
            motivo=motivo_normalizado,
        )

        session = self._session_factory()
        uow = UnitOfWorkV1.adotar_session(session)
        try:
            store = self._store(session)
            atual = store.obter_por_conversa(
                contexto=contexto,
                conversa_id=conversa_id,
            )
            if atual is None:
                raise LookupError("conversa_nao_encontrada")
            if atual.estado != EstadoAtendimento.HANDOFF_HUMANO.value:
                state_handoff = _estado_runtime_handoff(
                    atual.state,
                    motivo=motivo_normalizado,
                )
                store.salvar(
                    contexto=contexto,
                    canal="whatsapp",
                    recipient=atual.recipient,
                    conversa_id=atual.conversa_id,
                    estado=EstadoAtendimento.HANDOFF_HUMANO.value,
                    state=state_handoff,
                    pedido_id=atual.pedido_id,
                    pagamento_id=atual.pagamento_id,
                    entrega_id=atual.entrega_id,
                    ultimo_inbound_id=atual.ultimo_inbound_id,
                    ultimo_outbound_id=atual.ultimo_outbound_id,
                    ultimo_status_hash=atual.ultimo_status_hash,
                    versao_esperada=atual.versao,
                )
            uow.commit()
        except Exception:
            uow.rollback()
            raise
        finally:
            session.close()

    @staticmethod
    def _detalhe(
        estado: EstadoCanalPersistido,
        *,
        handoff_contexto: dict[str, str | int | bool] | None,
    ) -> ConversaDetalheAdmin:
        return ConversaDetalheAdmin(
            conversa_id=estado.conversa_id,
            estado=estado.estado,
            pedido_id=estado.pedido_id,
            pagamento_id=estado.pagamento_id,
            entrega_id=estado.entrega_id,
            ultimo_inbound_id=estado.ultimo_inbound_id,
            ultimo_outbound_id=estado.ultimo_outbound_id,
            versao=estado.versao,
            handoff_contexto=handoff_contexto,
        )
