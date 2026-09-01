"""Convergência mínima do Assistente com a logística canônica de Entrega.

F4-E não homologa o Delivery Próprio completo. O único objetivo aqui é impedir
que o caminho comercial do Assistente feche em um Pedido/Entrega paralelo:
checkout, reserva e vínculo logístico pertencem à mesma UoW e ao mesmo Pedido.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from uuid import NAMESPACE_URL, uuid5

from application.catalogo_estoque_cutover import (
    executar_checkout_com_ficha_estoque_em_transacao,
)
from application.checkout import ComandoCheckoutV1, ResultadoCheckoutV1
from core.assistente_atendimento.atendimento_modelos import (
    ModalidadePedidoAtendimento,
)
from core.assistente_atendimento.erros import ErroAssistenteAtendimento
from core.entrega import (
    Entrega,
    ModalidadeEntrega,
    RepositorioEntregaSQLAlchemy,
    ServicoEntrega,
    StatusEntrega,
    financeiro_resolvido_sqlalchemy,
    pedido_cancelado_sqlalchemy,
)
from core.seguranca.contexto import ContextoExecucao
from infra.transacoes.uow import UnitOfWorkV1


@dataclass(frozen=True)
class ResultadoConvergenciaDeliveryAssistente:
    checkout: ResultadoCheckoutV1
    entrega: Entrega | None


def _id_deterministico(chave: str) -> str:
    return str(uuid5(NAMESPACE_URL, chave))


def executar_checkout_assistente_convergente_v1(
    *,
    comando: ComandoCheckoutV1,
    contexto: ContextoExecucao,
    modalidade: ModalidadePedidoAtendimento,
    endereco_ref: str | None,
    idempotency_key: str,
    session_factory,
) -> ResultadoConvergenciaDeliveryAssistente:
    """Executa checkout + vínculo logístico canônico sob uma única UoW."""

    if not idempotency_key.strip():
        raise ErroAssistenteAtendimento("idempotency_key_obrigatoria")

    if modalidade is ModalidadePedidoAtendimento.INDEFINIDA:
        raise ErroAssistenteAtendimento("modalidade_atendimento_invalida")

    if modalidade is ModalidadePedidoAtendimento.ENTREGA:
        if endereco_ref is None or not endereco_ref.startswith("address://"):
            raise ErroAssistenteAtendimento(
                "entrega_sem_referencia_endereco_autorizada"
            )
    elif endereco_ref is not None:
        raise ErroAssistenteAtendimento("endereco_sem_modalidade_entrega")

    with UnitOfWorkV1(session_factory) as uow:
        checkout = executar_checkout_com_ficha_estoque_em_transacao(
            comando=comando,
            contexto=contexto,
            recursos=uow.recursos,
        )
        pedido = checkout.aguardando_confirmacao.pedido
        entrega: Entrega | None = None

        if modalidade is ModalidadePedidoAtendimento.ENTREGA:
            if uow.session is None or endereco_ref is None:
                raise RuntimeError("uow_entrega_invalida")
            session = uow.session

            entrega_id = _id_deterministico(
                f"{contexto.tenant_id}:{contexto.unidade_id}:"
                f"{pedido.id}:entrega"
            )
            entrega_nova = Entrega(
                entrega_id=entrega_id,
                tenant_id=contexto.tenant_id,
                unidade_id=contexto.unidade_id,
                pedido_id=str(pedido.id),
                endereco_id=endereco_ref,
                modalidade=ModalidadeEntrega.PROPRIA,
                status=StatusEntrega.AGUARDANDO_PRODUCAO,
                versao=1,
            )
            contexto_sistema = ContextoExecucao.sistema(
                identidade="assistente-delivery-convergence-v1",
                motivo=(
                    "vincular logística canônica ao Pedido criado pelo Assistente"
                ),
                tenant_id=contexto.tenant_id,
                unidade_id=contexto.unidade_id,
                correlation_id=contexto.correlation_id,
                solicitado_em=comando.timestamp,
            )
            if contexto.causation_id is not None:
                contexto_sistema = replace(
                    contexto_sistema,
                    causation_id=contexto.causation_id,
                )

            servico = ServicoEntrega(
                RepositorioEntregaSQLAlchemy(session),
                financeiro_resolvido=(
                    lambda tenant_id, unidade_id, pedido_id:
                    financeiro_resolvido_sqlalchemy(
                        session,
                        tenant_id,
                        unidade_id,
                        pedido_id,
                    )
                ),
                pedido_cancelado=(
                    lambda tenant_id, unidade_id, pedido_id:
                    pedido_cancelado_sqlalchemy(
                        session,
                        tenant_id,
                        unidade_id,
                        pedido_id,
                    )
                ),
                agora=lambda: comando.timestamp,
            )
            entrega = servico.criar(
                entrega_nova,
                contexto=contexto_sistema,
                idempotency_key=(
                    "assistente:entrega:"
                    f"{_id_deterministico(idempotency_key)}"
                ),
            )

        uow.commit()
        return ResultadoConvergenciaDeliveryAssistente(
            checkout=checkout,
            entrega=entrega,
        )
