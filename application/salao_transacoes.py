"""Fronteira transacional dos comandos da operação de Salão V1."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal
from typing import TypeVar

from sqlalchemy.orm import Session

from core.salao import (
    Comanda,
    MetodoFechamento,
    ParcelaFechamento,
    ParticipanteComanda,
    RepositorioSalaoSQLAlchemy,
    ServicoSalao,
)
from core.seguranca.contexto import ContextoExecucao
from infra.transacoes.uow import UnitOfWorkV1

T = TypeVar("T")


def _agora_utc() -> datetime:
    return datetime.now(timezone.utc)


def _session_ativa(uow: UnitOfWorkV1) -> Session:
    if uow.session is None:
        raise RuntimeError("UnitOfWorkV1 sem Session ativa")
    return uow.session


class AplicacaoSalaoV1:
    """Executa writes de Salão sob uma única autoridade transacional."""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        *,
        agora: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._agora = agora or _agora_utc

    def _executar(
        self,
        acao: Callable[[ServicoSalao, Session], T],
    ) -> T:
        with UnitOfWorkV1(self._session_factory) as uow:
            session = _session_ativa(uow)
            servico = ServicoSalao(
                RepositorioSalaoSQLAlchemy(session),
                agora=self._agora,
            )
            resultado = acao(servico, session)
            uow.commit()
            return resultado

    def abrir_comanda(
        self,
        contexto: ContextoExecucao,
        *,
        comanda_id: str,
        numero: str,
        mesa_id: str,
        expected_mesa_version: int,
        idempotency_key: str,
    ) -> Comanda:
        return self._executar(
            lambda servico, _session: servico.abrir_comanda(
                contexto,
                comanda_id=comanda_id,
                numero=numero,
                mesa_id=mesa_id,
                expected_mesa_version=expected_mesa_version,
                idempotency_key=idempotency_key,
            )
        )

    def cancelar_comanda(
        self,
        contexto: ContextoExecucao,
        *,
        comanda_id: str,
        expected_version: int,
        idempotency_key: str,
        pedidos_resolvidos: bool,
    ) -> Comanda:
        return self._executar(
            lambda servico, _session: servico.cancelar_comanda(
                contexto,
                comanda_id=comanda_id,
                expected_version=expected_version,
                idempotency_key=idempotency_key,
                pedidos_resolvidos=pedidos_resolvidos,
            )
        )

    def adicionar_participante(
        self,
        contexto: ContextoExecucao,
        *,
        comanda_id: str,
        participante_id: str,
        expected_version: int,
        idempotency_key: str,
        cliente_id: str | None = None,
        apelido: str | None = None,
    ) -> ParticipanteComanda:
        return self._executar(
            lambda servico, _session: servico.adicionar_participante(
                contexto,
                comanda_id=comanda_id,
                participante_id=participante_id,
                expected_version=expected_version,
                idempotency_key=idempotency_key,
                cliente_id=cliente_id,
                apelido=apelido,
            )
        )

    def vincular_pedido(
        self,
        contexto: ContextoExecucao,
        *,
        comanda_id: str,
        pedido_id: str,
        expected_version: int,
        idempotency_key: str,
        participante_id: str | None = None,
    ) -> Comanda:
        return self._executar(
            lambda servico, _session: servico.vincular_pedido(
                contexto,
                comanda_id=comanda_id,
                pedido_id=pedido_id,
                expected_version=expected_version,
                idempotency_key=idempotency_key,
                participante_id=participante_id,
            )
        )

    def transferir_comanda(
        self,
        contexto: ContextoExecucao,
        *,
        comanda_id: str,
        mesa_destino_id: str,
        expected_comanda_version: int,
        expected_origem_version: int,
        expected_destino_version: int,
        idempotency_key: str,
    ) -> Comanda:
        return self._executar(
            lambda servico, _session: servico.transferir_comanda(
                contexto,
                comanda_id=comanda_id,
                mesa_destino_id=mesa_destino_id,
                expected_comanda_version=expected_comanda_version,
                expected_origem_version=expected_origem_version,
                expected_destino_version=expected_destino_version,
                idempotency_key=idempotency_key,
            )
        )

    def separar_comanda(
        self,
        contexto: ContextoExecucao,
        *,
        origem_id: str,
        nova_comanda_id: str,
        novo_numero: str,
        pedido_ids: tuple[str, ...],
        expected_origem_version: int,
        idempotency_key: str,
        participante_ids: tuple[str, ...] = (),
    ) -> Comanda:
        return self._executar(
            lambda servico, _session: servico.separar_comanda(
                contexto,
                origem_id=origem_id,
                nova_comanda_id=nova_comanda_id,
                novo_numero=novo_numero,
                pedido_ids=pedido_ids,
                expected_origem_version=expected_origem_version,
                idempotency_key=idempotency_key,
                participante_ids=participante_ids,
            )
        )

    def juntar_comandas(
        self,
        contexto: ContextoExecucao,
        *,
        origem_id: str,
        destino_id: str,
        expected_origem_version: int,
        expected_destino_version: int,
        idempotency_key: str,
    ) -> Comanda:
        return self._executar(
            lambda servico, _session: servico.juntar_comandas(
                contexto,
                origem_id=origem_id,
                destino_id=destino_id,
                expected_origem_version=expected_origem_version,
                expected_destino_version=expected_destino_version,
                idempotency_key=idempotency_key,
            )
        )

    def solicitar_conta(
        self,
        contexto: ContextoExecucao,
        *,
        comanda_id: str,
        expected_version: int,
        idempotency_key: str,
    ) -> Comanda:
        return self._executar(
            lambda servico, _session: servico.solicitar_conta(
                contexto,
                comanda_id=comanda_id,
                expected_version=expected_version,
                idempotency_key=idempotency_key,
            )
        )

    def retomar_consumo(
        self,
        contexto: ContextoExecucao,
        *,
        comanda_id: str,
        expected_version: int,
        idempotency_key: str,
    ) -> Comanda:
        return self._executar(
            lambda servico, _session: servico.retomar_consumo(
                contexto,
                comanda_id=comanda_id,
                expected_version=expected_version,
                idempotency_key=idempotency_key,
            )
        )

    def definir_divisao_pagamento(
        self,
        contexto: ContextoExecucao,
        *,
        comanda_id: str,
        expected_version: int,
        idempotency_key: str,
        divisoes: tuple[
            tuple[MetodoFechamento, Decimal, str | None],
            ...,
        ],
    ) -> tuple[Comanda, tuple[ParcelaFechamento, ...]]:
        return self._executar(
            lambda servico, _session: servico.definir_divisao_pagamento(
                contexto,
                comanda_id=comanda_id,
                expected_version=expected_version,
                idempotency_key=idempotency_key,
                divisoes=divisoes,
            )
        )

    def registrar_pagamento_confirmado(
        self,
        contexto: ContextoExecucao,
        *,
        pagamento_id: str,
        comanda_id: str,
        metodo: MetodoFechamento,
        valor: Decimal,
        expected_version: int,
        idempotency_key: str,
    ) -> Comanda:
        """Projeta no Salão somente um Pagamento V1 já confirmado."""

        return self._executar(
            lambda servico, _session: servico.registrar_pagamento_confirmado(
                contexto,
                comanda_id=comanda_id,
                pagamento_id=pagamento_id,
                metodo=metodo,
                valor=valor,
                expected_version=expected_version,
                idempotency_key=idempotency_key,
            )
        )

    def registrar_pagamento_confirmado_teste_v1(
        self,
        contexto: ContextoExecucao,
        *,
        pagamento_id: str,
        pedido_id: str,
        comanda_id: str,
        metodo: MetodoFechamento,
        valor: Decimal,
        expected_version: int,
        idempotency_key: str,
        agora: datetime,
    ) -> Comanda:
        def acao(
            servico: ServicoSalao,
            session: Session,
        ) -> Comanda:
            from core.salao.runtime_teste import registrar_pagamento_confirmado_teste

            registrar_pagamento_confirmado_teste(
                session,
                pagamento_id=pagamento_id,
                pedido_id=pedido_id,
                comanda_id=comanda_id,
                metodo=metodo.value,
                valor=valor,
                agora=agora,
            )
            return servico.registrar_pagamento_confirmado(
                contexto,
                comanda_id=comanda_id,
                pagamento_id=pagamento_id,
                metodo=metodo,
                valor=valor,
                expected_version=expected_version,
                idempotency_key=idempotency_key,
            )

        return self._executar(acao)

    def fechar_comanda(
        self,
        contexto: ContextoExecucao,
        *,
        comanda_id: str,
        expected_version: int,
        idempotency_key: str,
        pedidos_resolvidos: bool,
    ) -> Comanda:
        return self._executar(
            lambda servico, _session: servico.fechar_comanda(
                contexto,
                comanda_id=comanda_id,
                expected_version=expected_version,
                idempotency_key=idempotency_key,
                pedidos_resolvidos=pedidos_resolvidos,
            )
        )
