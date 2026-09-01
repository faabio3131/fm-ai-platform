"""Runtime comercial do canal WhatsApp para o Assistente de Atendimento V1.

O webhook só transporta entrada autenticada. Estado multi-turno é cifrado,
deduplicação usa Inbox persistente e efeitos comerciais continuam nos serviços
canônicos já existentes.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from application.assistente_atendimento_runtime import (
    ResultadoRuntimeAssistente,
    RuntimeAssistenteAtendimentoV1,
    _contexto_agente,
)
from core.assistente_atendimento.atendimento_modelos import (
    CarrinhoAtendimento,
    CotacaoEntregaAtendimento,
    EstadoAtendimento,
    ItemCarrinhoAtendimento,
    ModalidadePedidoAtendimento,
    PreferenciaPagamentoAtendimento,
    ResultadoAtendimento,
    ResultadoCheckoutAssistente,
)
from core.assistente_atendimento.contexto import (
    ClienteAtendimento,
    ContextoAtendimento,
    TipoClienteAtendimento,
)
from core.dominio.enums import PagamentoStatus
from core.dominio.ids import (
    CorrelationId,
    EventoId,
    IdempotencyKey,
    TenantId,
    UnidadeId,
)
from core.eventos.modelos import EnvelopeMensagem
from core.integracoes.provedores import (
    ErroProvedorExterno,
    MensagemWhatsAppEntrada,
    MetaAdapter,
)
from core.kds.modelos_orm import ProducaoItemORM
from core.pagamentos.modelos import MetodoPagamento
from core.pagamentos.modelos_orm import PagamentoORM
from core.pedidos.modelos_orm import PedidoORM
from core.seguranca.auditoria import EventoAuditoria
from core.seguranca.contexto import ContextoExecucao
from core.entrega.modelos_orm import EntregaORM, EventoEntregaORM
from infra.assistente_atendimento.canal_estado_sqlalchemy import (
    EncryptedSQLAlchemyChannelStateStore,
    EstadoCanalPersistido,
)
from infra.assistente_atendimento.contexto_cliente_sqlalchemy import (
    ContextoClienteAtendimentoSQLAlchemy,
)
from infra.assistente_atendimento.handoff_sqlalchemy import (
    HandoffAssistenteAuditSQLAlchemy,
)
from infra.eventos.adaptador_sqlalchemy import RepositorioInboxSQLAlchemy
from infra.eventos.modelos_orm import InboxEventoORM
from infra.gerente_ia.persistencia_sqlalchemy import (
    RepositorioIdentidadeAssistenteSQLAlchemy,
)
from infra.seguranca.auditoria_sqlalchemy import RepositorioAuditoriaSQLAlchemy

SessionFactory = Callable[[], Session]


@dataclass(frozen=True)
class SnapshotOperacionalAssistente:
    pedido_id: str
    pedido_status: str
    pagamento_id: str | None
    pagamento_status: str | None
    producao_status: tuple[str, ...]
    entrega_id: str | None
    entrega_status: str | None
    entrega_evento: str | None

    @property
    def fingerprint(self) -> str:
        payload = {
            "pedido_id": self.pedido_id,
            "pedido_status": self.pedido_status,
            "pagamento_id": self.pagamento_id,
            "pagamento_status": self.pagamento_status,
            "producao_status": self.producao_status,
            "entrega_id": self.entrega_id,
            "entrega_status": self.entrega_status,
            "entrega_evento": self.entrega_evento,
        }
        return hashlib.sha256(
            json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()


@dataclass(frozen=True)
class ResultadoMensagemCanal:
    mensagem_id: str
    duplicada: bool
    outbound_id: str | None
    estado: str | None
    handoff: bool = False


def _decimal(valor: object) -> Decimal:
    return Decimal(str(valor))


def _serializar_carrinho(carrinho: CarrinhoAtendimento | None):
    if carrinho is None:
        return None
    entrega = None
    if carrinho.entrega is not None:
        e = carrinho.entrega
        entrega = {
            "endereco_formatado": e.endereco_formatado,
            "cep": e.cep,
            "place_id": e.place_id,
            "latitude": e.latitude,
            "longitude": e.longitude,
            "distancia_metros": e.distancia_metros,
            "eta_rota_minutos": e.eta_rota_minutos,
            "area_id": e.area_id,
            "nome_area": e.nome_area,
            "taxa": str(e.taxa),
            "sla_minutos": e.sla_minutos,
            "sla_maxutos": e.sla_maxutos,
            "versao_area": e.versao_area,
        }
    pagamento = None
    if carrinho.pagamento is not None:
        pagamento = {
            "metodo": carrinho.pagamento.metodo.value,
            "valor_para_troco": (
                str(carrinho.pagamento.valor_para_troco)
                if carrinho.pagamento.valor_para_troco is not None
                else None
            ),
        }
    return {
        "tenant_id": carrinho.tenant_id,
        "unidade_id": carrinho.unidade_id,
        "conversa_id": carrinho.conversa_id,
        "mensagem_id": carrinho.mensagem_id,
        "itens": [
            {
                "produto_id": item.produto_id,
                "nome_produto": item.nome_produto,
                "quantidade": item.quantidade,
                "preco_unitario": str(item.preco_unitario),
            }
            for item in carrinho.itens
        ],
        "fingerprint": carrinho.fingerprint,
        "modalidade": carrinho.modalidade.value,
        "endereco_solicitado": carrinho.endereco_solicitado,
        "entrega": entrega,
        "pagamento": pagamento,
    }


def _desserializar_carrinho(payload) -> CarrinhoAtendimento | None:
    if payload is None:
        return None
    entrega_payload = payload.get("entrega")
    entrega = None
    if isinstance(entrega_payload, dict):
        entrega = CotacaoEntregaAtendimento(
            endereco_formatado=str(entrega_payload["endereco_formatado"]),
            cep=str(entrega_payload["cep"]),
            place_id=str(entrega_payload["place_id"]),
            latitude=float(entrega_payload["latitude"]),
            longitude=float(entrega_payload["longitude"]),
            distancia_metros=int(entrega_payload["distancia_metros"]),
            eta_rota_minutos=int(entrega_payload["eta_rota_minutos"]),
            area_id=str(entrega_payload["area_id"]),
            nome_area=str(entrega_payload["nome_area"]),
            taxa=_decimal(entrega_payload["taxa"]),
            sla_minutos=int(entrega_payload["sla_minutos"]),
            sla_maxutos=int(entrega_payload["sla_maxutos"]),
            versao_area=int(entrega_payload["versao_area"]),
        )
    pagamento_payload = payload.get("pagamento")
    pagamento = None
    if isinstance(pagamento_payload, dict):
        troco = pagamento_payload.get("valor_para_troco")
        pagamento = PreferenciaPagamentoAtendimento(
            metodo=MetodoPagamento(str(pagamento_payload["metodo"])),
            valor_para_troco=_decimal(troco) if troco is not None else None,
        )
    return CarrinhoAtendimento(
        tenant_id=str(payload["tenant_id"]),
        unidade_id=str(payload["unidade_id"]),
        conversa_id=str(payload["conversa_id"]),
        mensagem_id=str(payload["mensagem_id"]),
        itens=tuple(
            ItemCarrinhoAtendimento(
                produto_id=str(item["produto_id"]),
                nome_produto=str(item["nome_produto"]),
                quantidade=int(item["quantidade"]),
                preco_unitario=_decimal(item["preco_unitario"]),
            )
            for item in payload.get("itens", [])
            if isinstance(item, dict)
        ),
        fingerprint=str(payload["fingerprint"]),
        modalidade=ModalidadePedidoAtendimento(str(payload["modalidade"])),
        endereco_solicitado=(
            str(payload["endereco_solicitado"])
            if payload.get("endereco_solicitado") is not None
            else None
        ),
        entrega=entrega,
        pagamento=pagamento,
    )


def _serializar_checkout(checkout: ResultadoCheckoutAssistente | None):
    if checkout is None:
        return None
    return {
        "pedido_id": checkout.pedido_id,
        "pedido_status": checkout.pedido_status,
        "pagamento_id": checkout.pagamento_id,
        "pagamento_status": (
            checkout.pagamento_status.value
            if checkout.pagamento_status is not None
            else None
        ),
        "metodo_pagamento": (
            checkout.metodo_pagamento.value
            if checkout.metodo_pagamento is not None
            else None
        ),
        "estoque_reservado": checkout.estoque_reservado,
        "estoque_idempotente": checkout.estoque_idempotente,
        "entrega_id": checkout.entrega_id,
        "entrega_status": checkout.entrega_status,
        "idempotente": checkout.idempotente,
    }


def _desserializar_checkout(payload) -> ResultadoCheckoutAssistente | None:
    if payload is None:
        return None
    return ResultadoCheckoutAssistente(
        pedido_id=str(payload["pedido_id"]),
        pedido_status=str(payload["pedido_status"]),
        pagamento_id=(
            str(payload["pagamento_id"]) if payload.get("pagamento_id") else None
        ),
        pagamento_status=(
            PagamentoStatus(str(payload["pagamento_status"]))
            if payload.get("pagamento_status")
            else None
        ),
        metodo_pagamento=(
            MetodoPagamento(str(payload["metodo_pagamento"]))
            if payload.get("metodo_pagamento")
            else None
        ),
        estoque_reservado=bool(payload.get("estoque_reservado", False)),
        estoque_idempotente=payload.get("estoque_idempotente"),
        entrega_id=str(payload["entrega_id"]) if payload.get("entrega_id") else None,
        entrega_status=(
            str(payload["entrega_status"]) if payload.get("entrega_status") else None
        ),
        idempotente=bool(payload.get("idempotente", False)),
    )


def _serializar_runtime(runtime: ResultadoRuntimeAssistente) -> dict[str, object]:
    resultado = runtime.resultado
    return {
        "cliente_tipo": runtime.contexto.cliente.tipo.value,
        "cliente_ref": runtime.contexto.cliente.cliente_ref,
        "cliente_nome": runtime.contexto.cliente.nome,
        "resultado": {
            "estado": resultado.estado.value,
            "mensagem": resultado.mensagem,
            "carrinho": _serializar_carrinho(resultado.carrinho),
            "checkout": _serializar_checkout(resultado.checkout),
            "handoff_motivo": resultado.handoff_motivo,
            "auditoria": list(resultado.auditoria),
        },
    }


def _restaurar_runtime(
    *,
    payload: dict[str, object],
    contexto_solicitante: ContextoExecucao,
    conversa_id: str,
    session: Session,
) -> ResultadoRuntimeAssistente:
    cliente = ClienteAtendimento(
        tipo=TipoClienteAtendimento(str(payload["cliente_tipo"])),
        cliente_ref=(
            str(payload["cliente_ref"]) if payload.get("cliente_ref") else None
        ),
        nome=str(payload["cliente_nome"]) if payload.get("cliente_nome") else None,
    )
    contexto_execucao = _contexto_agente(contexto_solicitante)
    customer_context = None
    if cliente.cliente_ref is not None:
        customer_context = ContextoClienteAtendimentoSQLAlchemy(session).resolver(
            contexto=contexto_execucao,
            cliente_ref=cliente.cliente_ref,
        )
    contexto = ContextoAtendimento(
        contexto_execucao=contexto_execucao,
        conversa_id=conversa_id,
        canal="whatsapp",
        cliente=cliente,
        customer_context=customer_context,
    )
    resultado_payload = payload.get("resultado")
    if not isinstance(resultado_payload, dict):
        raise LookupError("estado_canal_sem_resultado")
    resultado = ResultadoAtendimento(
        estado=EstadoAtendimento(str(resultado_payload["estado"])),
        mensagem=str(resultado_payload["mensagem"]),
        carrinho=_desserializar_carrinho(resultado_payload.get("carrinho")),
        checkout=_desserializar_checkout(resultado_payload.get("checkout")),
        handoff_motivo=(
            str(resultado_payload["handoff_motivo"])
            if resultado_payload.get("handoff_motivo")
            else None
        ),
        auditoria=tuple(
            (str(item[0]), str(item[1]))
            for item in resultado_payload.get("auditoria", [])
            if isinstance(item, (list, tuple)) and len(item) == 2
        ),
    )
    return ResultadoRuntimeAssistente(contexto=contexto, resultado=resultado)


def _afirmativo(texto: str) -> bool:
    normalizado = " ".join(texto.casefold().strip().split())
    return normalizado in {
        "sim",
        "confirmo",
        "confirmado",
        "pode confirmar",
        "pode seguir",
        "continuar",
        "pode continuar",
    }


def _pede_humano(texto: str) -> bool:
    normalizado = texto.casefold()
    return any(
        termo in normalizado
        for termo in ("atendente", "humano", "reclamação", "reclamacao")
    )


def _modalidade(texto: str) -> ModalidadePedidoAtendimento | None:
    normalizado = texto.casefold()
    entrega = "entrega" in normalizado or "delivery" in normalizado
    retirada = "retirada" in normalizado or "retirar" in normalizado
    if entrega == retirada:
        return None
    return (
        ModalidadePedidoAtendimento.ENTREGA
        if entrega
        else ModalidadePedidoAtendimento.RETIRADA
    )


def _metodo_pagamento(texto: str) -> MetodoPagamento | None:
    normalizado = texto.casefold()
    candidatos: list[MetodoPagamento] = []
    if "pix" in normalizado:
        candidatos.append(MetodoPagamento.PIX)
    if "dinheiro" in normalizado:
        candidatos.append(MetodoPagamento.DINHEIRO)
    if "crédito" in normalizado or "credito" in normalizado:
        candidatos.append(MetodoPagamento.CARTAO_CREDITO)
    if "débito" in normalizado or "debito" in normalizado:
        candidatos.append(MetodoPagamento.CARTAO_DEBITO)
    if "pagamento na entrega" in normalizado or "pagar na entrega" in normalizado:
        candidatos.append(MetodoPagamento.PAGAMENTO_NA_ENTREGA)
    unicos = tuple(dict.fromkeys(candidatos))
    return unicos[0] if len(unicos) == 1 else None


def _troco_para(texto: str) -> Decimal | None:
    match = re.search(
        r"troco(?:\s+para)?\s+(?:r\$\s*)?(\d+(?:[.,]\d{1,2})?)",
        texto.casefold(),
    )
    if match is None:
        return None
    return Decimal(match.group(1).replace(",", "."))


def _cep(texto: str) -> str | None:
    encontrados = re.findall(r"(?<!\d)(\d{5})[-\s]?(\d{3})(?!\d)", texto)
    if len(encontrados) != 1:
        return None
    return "".join(encontrados[0])


def _mensagem_snapshot(snapshot: SnapshotOperacionalAssistente) -> str:
    partes = [
        f"Pedido {snapshot.pedido_id}: {snapshot.pedido_status}.",
    ]
    if snapshot.pagamento_status is not None:
        partes.append(f"Pagamento: {snapshot.pagamento_status}.")
    if snapshot.producao_status:
        partes.append(
            "Produção/KDS: " + ", ".join(snapshot.producao_status) + "."
        )
    if snapshot.entrega_status is not None:
        partes.append(f"Entrega: {snapshot.entrega_status}.")
        if snapshot.entrega_evento is not None:
            partes.append(f"Último evento logístico: {snapshot.entrega_evento}.")
    partes.append(
        "Não vou estimar prazo novo sem uma fonte operacional que o confirme."
    )
    return " ".join(partes)


class RuntimeCanalWhatsAppV1:
    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        runtime: RuntimeAssistenteAtendimentoV1 | None = None,
        handoff: HandoffAssistenteAuditSQLAlchemy | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._runtime = runtime or RuntimeAssistenteAtendimentoV1(session_factory)
        self._handoff = handoff or HandoffAssistenteAuditSQLAlchemy(session_factory)

    def _contexto(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        mensagem_id: str,
    ) -> ContextoExecucao:
        return ContextoExecucao.sistema(
            identidade="meta-whatsapp-ingress-v1",
            motivo="webhook WhatsApp autenticado para atendimento",
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            correlation_id=f"wa:{mensagem_id}",
            solicitado_em=datetime.now(timezone.utc),
        )

    def _nome_publico(self, session: Session, contexto: ContextoExecucao) -> str:
        identidade = RepositorioIdentidadeAssistenteSQLAlchemy(session).obter(
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
        )
        return identidade.nome_publico if identidade is not None else "Assistente de Atendimento"

    def consultar_status(
        self,
        *,
        session: Session,
        contexto: ContextoExecucao,
        pedido_id: str,
        pagamento_id: str | None = None,
    ) -> SnapshotOperacionalAssistente:
        pedido = session.scalar(
            select(PedidoORM).where(
                PedidoORM.tenant_id == contexto.tenant_id,
                PedidoORM.unidade_id == contexto.unidade_id,
                PedidoORM.id == pedido_id,
            )
        )
        if pedido is None:
            raise LookupError("pedido_indisponivel_no_escopo")
        pagamento = None
        if pagamento_id is not None:
            pagamento = session.scalar(
                select(PagamentoORM).where(
                    PagamentoORM.tenant_id == contexto.tenant_id,
                    PagamentoORM.unidade_id == contexto.unidade_id,
                    PagamentoORM.id == pagamento_id,
                    PagamentoORM.pedido_id == pedido_id,
                )
            )
        if pagamento is None:
            pagamento = session.scalar(
                select(PagamentoORM)
                .where(
                    PagamentoORM.tenant_id == contexto.tenant_id,
                    PagamentoORM.unidade_id == contexto.unidade_id,
                    PagamentoORM.pedido_id == pedido_id,
                )
                .order_by(PagamentoORM.atualizado_em.desc())
                .limit(1)
            )
        producao = tuple(
            sorted(
                {
                    str(status)
                    for status in session.scalars(
                        select(ProducaoItemORM.status).where(
                            ProducaoItemORM.tenant_id == contexto.tenant_id,
                            ProducaoItemORM.unidade_id == contexto.unidade_id,
                            ProducaoItemORM.pedido_id == pedido_id,
                        )
                    ).all()
                }
            )
        )
        entrega = session.scalar(
            select(EntregaORM).where(
                EntregaORM.tenant_id == contexto.tenant_id,
                EntregaORM.unidade_id == contexto.unidade_id,
                EntregaORM.pedido_id == pedido_id,
            )
        )
        evento_entrega = None
        if entrega is not None:
            evento_entrega = session.scalar(
                select(EventoEntregaORM.tipo)
                .where(
                    EventoEntregaORM.tenant_id == contexto.tenant_id,
                    EventoEntregaORM.unidade_id == contexto.unidade_id,
                    EventoEntregaORM.entrega_id == entrega.id,
                )
                .order_by(
                    EventoEntregaORM.ocorrido_em.desc(),
                    EventoEntregaORM.event_id.desc(),
                )
                .limit(1)
            )
        return SnapshotOperacionalAssistente(
            pedido_id=pedido_id,
            pedido_status=str(pedido.status),
            pagamento_id=str(pagamento.id) if pagamento is not None else None,
            pagamento_status=(
                str(pagamento.status) if pagamento is not None else None
            ),
            producao_status=producao,
            entrega_id=str(entrega.id) if entrega is not None else None,
            entrega_status=str(entrega.status) if entrega is not None else None,
            entrega_evento=str(evento_entrega) if evento_entrega else None,
        )

    def notificar_status_pedido(
        self,
        *,
        contexto: ContextoExecucao,
        pedido_id: str,
        adapter: MetaAdapter,
    ) -> int:
        """Envia snapshot somente quando o estado operacional realmente mudou."""

        if not pedido_id.strip():
            raise ValueError("pedido_id_obrigatorio")
        db = self._session_factory()
        try:
            store = EncryptedSQLAlchemyChannelStateStore(db)
            estados = store.obter_por_pedido(
                tenant_id=contexto.tenant_id,
                unidade_id=contexto.unidade_id,
                pedido_id=pedido_id,
            )
            enviados = 0
            for estado in estados:
                snapshot = self.consultar_status(
                    session=db,
                    contexto=contexto,
                    pedido_id=pedido_id,
                    pagamento_id=estado.pagamento_id,
                )
                fingerprint = snapshot.fingerprint
                if fingerprint == estado.ultimo_status_hash:
                    continue
                try:
                    outbound_id = adapter.enviar_whatsapp(
                        destinatario=estado.recipient,
                        texto=_mensagem_snapshot(snapshot),
                        idempotency_key=(
                            f"status:{pedido_id}:{fingerprint[:24]}"
                        ),
                    )
                except ErroProvedorExterno:
                    # POST Meta pode ter sido aceito antes de um timeout. Não repetir
                    # automaticamente evita mensagem duplicada; o próximo inbound
                    # consulta as fontes canônicas novamente.
                    store.salvar(
                        contexto=contexto,
                        canal="whatsapp",
                        recipient=estado.recipient,
                        conversa_id=estado.conversa_id,
                        estado=estado.estado,
                        state=estado.state,
                        pedido_id=estado.pedido_id,
                        pagamento_id=estado.pagamento_id,
                        entrega_id=estado.entrega_id,
                        ultimo_inbound_id=estado.ultimo_inbound_id,
                        ultimo_outbound_id=estado.ultimo_outbound_id,
                        ultimo_status_hash=fingerprint,
                        versao_esperada=estado.versao,
                    )
                    continue
                store.salvar(
                    contexto=contexto,
                    canal="whatsapp",
                    recipient=estado.recipient,
                    conversa_id=estado.conversa_id,
                    estado=estado.estado,
                    state=estado.state,
                    pedido_id=estado.pedido_id,
                    pagamento_id=estado.pagamento_id,
                    entrega_id=estado.entrega_id,
                    ultimo_inbound_id=estado.ultimo_inbound_id,
                    ultimo_outbound_id=outbound_id,
                    ultimo_status_hash=fingerprint,
                    versao_esperada=estado.versao,
                )
                enviados += 1
            db.commit()
            return enviados
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _handoff_resultado(
        self,
        *,
        runtime: ResultadoRuntimeAssistente,
        motivo: str,
        mensagem_contexto: str | None = None,
    ) -> ResultadoRuntimeAssistente:
        checkout = runtime.resultado.checkout
        metadata = {
            "estado": runtime.resultado.estado.value,
            "pedido_id": checkout.pedido_id if checkout is not None else "nao_criado",
        }
        self._handoff.registrar(
            contexto=runtime.contexto.contexto_execucao,
            conversa_id=runtime.contexto.conversa_id,
            motivo=motivo,
            metadata_segura=metadata,
        )
        return ResultadoRuntimeAssistente(
            contexto=runtime.contexto,
            resultado=ResultadoAtendimento(
                estado=EstadoAtendimento.HANDOFF_HUMANO,
                mensagem=(
                    (
                        f"{mensagem_contexto} "
                        if mensagem_contexto is not None
                        else ""
                    )
                    + "Encaminhei este atendimento para uma pessoa da equipe. "
                    "Não vou inventar uma resposta operacional."
                ),
                carrinho=runtime.resultado.carrinho,
                checkout=runtime.resultado.checkout,
                handoff_motivo=motivo,
                auditoria=(*runtime.resultado.auditoria, ("handoff", motivo)),
            ),
        )

    def _avancar(
        self,
        *,
        runtime: ResultadoRuntimeAssistente,
        texto: str,
        recipient: str,
        mensagem_id: str,
    ) -> ResultadoRuntimeAssistente:
        if _pede_humano(texto):
            if runtime.resultado.estado is EstadoAtendimento.CHECKOUT_REGISTRADO:
                checkout = runtime.resultado.checkout
                if checkout is not None:
                    db = self._session_factory()
                    try:
                        snapshot = self.consultar_status(
                            session=db,
                            contexto=runtime.contexto.contexto_execucao,
                            pedido_id=checkout.pedido_id,
                            pagamento_id=checkout.pagamento_id,
                        )
                    finally:
                        db.close()
                    runtime = ResultadoRuntimeAssistente(
                        contexto=runtime.contexto,
                        resultado=replace(
                            runtime.resultado,
                            mensagem=_mensagem_snapshot(snapshot),
                        ),
                    )
            return self._handoff_resultado(
                runtime=runtime,
                motivo="cliente_solicitou_atendimento_humano",
                mensagem_contexto=runtime.resultado.mensagem,
            )

        estado = runtime.resultado.estado
        if estado is EstadoAtendimento.AGUARDANDO_DADOS_CLIENTE:
            if not _afirmativo(texto):
                return ResultadoRuntimeAssistente(
                    contexto=runtime.contexto,
                    resultado=replace(
                        runtime.resultado,
                        mensagem=(
                            "Para continuar, preciso registrar o contato mínimo no CRM "
                            "desta unidade. Responda sim para continuar ou peça um atendente."
                        ),
                    ),
                )
            return self._runtime.registrar_cliente_minimo(
                runtime_anterior=runtime,
                identificador_cliente=recipient,
            )

        if estado is EstadoAtendimento.AGUARDANDO_MODALIDADE_ENTREGA:
            modalidade = _modalidade(texto)
            if modalidade is None:
                return ResultadoRuntimeAssistente(
                    contexto=runtime.contexto,
                    resultado=replace(
                        runtime.resultado,
                        mensagem="Você prefere retirada ou entrega?",
                    ),
                )
            return self._runtime.definir_modalidade(
                runtime_anterior=runtime,
                modalidade=modalidade,
            )

        if estado is EstadoAtendimento.AGUARDANDO_ENDERECO_ENTREGA:
            normalizado = texto.casefold()
            if "endereço salvo" in normalizado or "endereco salvo" in normalizado:
                return self._runtime.usar_ultimo_endereco_salvo(
                    runtime_anterior=runtime
                )
            cep = _cep(texto)
            if cep is None:
                return ResultadoRuntimeAssistente(
                    contexto=runtime.contexto,
                    resultado=replace(
                        runtime.resultado,
                        mensagem=(
                            "Envie o endereço completo com um único CEP para eu validar "
                            "área, taxa, rota e ETA nas fontes oficiais."
                        ),
                    ),
                )
            return self._runtime.cotar_entrega(
                runtime_anterior=runtime,
                endereco_texto=texto,
                cep=cep,
            )

        if estado is EstadoAtendimento.AGUARDANDO_FORMA_PAGAMENTO:
            metodo = _metodo_pagamento(texto)
            if metodo is None:
                return ResultadoRuntimeAssistente(
                    contexto=runtime.contexto,
                    resultado=replace(
                        runtime.resultado,
                        mensagem=(
                            "Informe uma única forma de pagamento: Pix, dinheiro, "
                            "cartão de crédito, cartão de débito ou pagamento na entrega."
                        ),
                    ),
                )
            return self._runtime.definir_pagamento(
                runtime_anterior=runtime,
                metodo=metodo,
                valor_para_troco=_troco_para(texto),
            )

        if estado is EstadoAtendimento.AGUARDANDO_CONFIRMACAO_CLIENTE:
            carrinho = runtime.resultado.carrinho
            if carrinho is None or carrinho.pagamento is None:
                return self._handoff_resultado(
                    runtime=runtime,
                    motivo="estado_confirmacao_inconsistente",
                )
            if not _afirmativo(texto):
                return ResultadoRuntimeAssistente(
                    contexto=runtime.contexto,
                    resultado=replace(
                        runtime.resultado,
                        mensagem=(
                            "Nada foi confirmado. Para concluir, responda confirmo. "
                            "Para alterar o pedido, peça um atendente ou envie um novo pedido completo."
                        ),
                    ),
                )
            final = self._runtime.confirmar(
                runtime_anterior=runtime,
                confirmacao_cliente=True,
                fingerprint_confirmado=carrinho.fingerprint,
                metodo=carrinho.pagamento.metodo,
                idempotency_key=f"wa:{mensagem_id}:checkout",
            )
            return ResultadoRuntimeAssistente(
                contexto=runtime.contexto,
                resultado=final,
            )

        if estado is EstadoAtendimento.CHECKOUT_REGISTRADO:
            checkout = runtime.resultado.checkout
            if checkout is None:
                return self._handoff_resultado(
                    runtime=runtime,
                    motivo="checkout_ausente_no_acompanhamento",
                )
            db = self._session_factory()
            try:
                snapshot = self.consultar_status(
                    session=db,
                    contexto=runtime.contexto.contexto_execucao,
                    pedido_id=checkout.pedido_id,
                    pagamento_id=checkout.pagamento_id,
                )
            finally:
                db.close()
            return ResultadoRuntimeAssistente(
                contexto=runtime.contexto,
                resultado=replace(
                    runtime.resultado,
                    mensagem=_mensagem_snapshot(snapshot),
                ),
            )

        return runtime

    def _envelope(
        self,
        *,
        contexto: ContextoExecucao,
        mensagem: MensagemWhatsAppEntrada,
        sender_hash: str,
    ) -> EnvelopeMensagem:
        event_uuid = uuid5(
            NAMESPACE_URL,
            f"{contexto.tenant_id}:{contexto.unidade_id}:wa:{mensagem.mensagem_id}",
        )
        return EnvelopeMensagem(
            event_id=EventoId(str(event_uuid)),
            event_type="assistente.whatsapp.mensagem_recebida",
            aggregate_id=mensagem.mensagem_id,
            aggregate_type="mensagem_canal",
            tenant_id=TenantId(contexto.tenant_id),
            unidade_id=UnidadeId(contexto.unidade_id),
            correlation_id=CorrelationId(contexto.correlation_id),
            causation_id=None,
            idempotency_key=IdempotencyKey(f"meta:message:{mensagem.mensagem_id}"),
            occurred_at=datetime.now(timezone.utc),
            payload={
                "canal": "whatsapp",
                "tipo": mensagem.tipo,
                "sender_hash": sender_hash,
            },
            version=1,
        )

    def _auditar(
        self,
        *,
        session: Session,
        contexto: ContextoExecucao,
        mensagem_id: str,
        resultado: str,
        estado: str,
    ) -> None:
        RepositorioAuditoriaSQLAlchemy(session).adicionar(
            EventoAuditoria(
                audit_id=str(uuid5(NAMESPACE_URL, f"audit:{contexto.correlation_id}:{resultado}")),
                tenant_id=contexto.tenant_id,
                unidade_id=contexto.unidade_id,
                usuario_id=contexto.usuario_id,
                papel_efetivo=None,
                acao="assistente_atendimento.canal_whatsapp",
                recurso_tipo="mensagem_canal",
                recurso_id=mensagem_id,
                resultado=resultado,
                motivo="runtime de canal governado",
                correlation_id=contexto.correlation_id,
                timestamp=datetime.now(timezone.utc),
                origem="meta_whatsapp_webhook_v1",
                politica="assistente_channel_runtime_v1",
                causation_id=contexto.causation_id,
                metadata=(("estado", estado), ("canal", "whatsapp")),
            )
        )

    def processar_mensagem(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        mensagem: MensagemWhatsAppEntrada,
        adapter: MetaAdapter,
    ) -> ResultadoMensagemCanal:
        contexto = self._contexto(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            mensagem_id=mensagem.mensagem_id,
        )
        db = self._session_factory()
        try:
            store = EncryptedSQLAlchemyChannelStateStore(db)
            sender_hash = store.sender_hash(
                tenant_id=tenant_id,
                unidade_id=unidade_id,
                canal="whatsapp",
                recipient=mensagem.remetente,
            )
            existente = store.obter(
                contexto=contexto,
                canal="whatsapp",
                recipient=mensagem.remetente,
            )
            if existente is not None and existente.ultimo_inbound_id == mensagem.mensagem_id:
                return ResultadoMensagemCanal(
                    mensagem_id=mensagem.mensagem_id,
                    duplicada=True,
                    outbound_id=existente.ultimo_outbound_id,
                    estado=existente.estado,
                    handoff=existente.estado == EstadoAtendimento.HANDOFF_HUMANO.value,
                )
            envelope = self._envelope(
                contexto=contexto, mensagem=mensagem, sender_hash=sender_hash
            )
            inbox = RepositorioInboxSQLAlchemy(db)
            if inbox.ja_processada(
                envelope.tenant_id,
                envelope.unidade_id,
                envelope.idempotency_key,
            ):
                return ResultadoMensagemCanal(
                    mensagem_id=mensagem.mensagem_id,
                    duplicada=True,
                    outbound_id=existente.ultimo_outbound_id if existente else None,
                    estado=existente.estado if existente else None,
                    handoff=bool(
                        existente
                        and existente.estado == EstadoAtendimento.HANDOFF_HUMANO.value
                    ),
                )

            conversa_id = (
                existente.conversa_id
                if existente is not None
                else str(
                    uuid5(
                        NAMESPACE_URL,
                        f"{tenant_id}:{unidade_id}:whatsapp:{sender_hash}",
                    )
                )
            )
            nome_publico = self._nome_publico(db, contexto)
            previous = None
            if existente is not None and existente.state is not None:
                previous = _restaurar_runtime(
                    payload=existente.state,
                    contexto_solicitante=contexto,
                    conversa_id=conversa_id,
                    session=db,
                )
        finally:
            db.close()

        if mensagem.tipo == "text":
            texto = (mensagem.texto or "").strip()
            if not texto:
                raise ValueError("mensagem_whatsapp_texto_vazio")
            if previous is None:
                runtime_atual = self._runtime.interpretar_texto(
                    contexto_solicitante=contexto,
                    conversa_id=conversa_id,
                    mensagem_id=mensagem.mensagem_id,
                    identificador_cliente=mensagem.remetente,
                    mensagem=texto,
                    nome_publico=nome_publico,
                )
            else:
                runtime_atual = self._avancar(
                    runtime=previous,
                    texto=texto,
                    recipient=mensagem.remetente,
                    mensagem_id=mensagem.mensagem_id,
                )
        elif mensagem.tipo == "audio":
            if mensagem.media_id is None:
                raise ValueError("mensagem_whatsapp_audio_sem_midia")
            audio, mime_type = adapter.baixar_audio_whatsapp(
                media_id=mensagem.media_id,
                mime_type_declarado=mensagem.mime_type,
            )
            if previous is None:
                runtime_atual = self._runtime.interpretar_audio(
                    contexto_solicitante=contexto,
                    conversa_id=conversa_id,
                    mensagem_id=mensagem.mensagem_id,
                    identificador_cliente=mensagem.remetente,
                    audio=audio,
                    mime_type=mime_type,
                    nome_publico=nome_publico,
                )
            else:
                texto = self._runtime.transcrever_audio(
                    contexto_solicitante=contexto,
                    mensagem_id=mensagem.mensagem_id,
                    audio=audio,
                    mime_type=mime_type,
                )
                runtime_atual = self._avancar(
                    runtime=previous,
                    texto=texto,
                    recipient=mensagem.remetente,
                    mensagem_id=mensagem.mensagem_id,
                )
        else:
            if previous is None:
                cliente = ClienteAtendimento(
                    tipo=TipoClienteAtendimento.NOVO,
                    cliente_ref=None,
                )
                previous = ResultadoRuntimeAssistente(
                    contexto=ContextoAtendimento(
                        contexto_execucao=_contexto_agente(contexto),
                        conversa_id=conversa_id,
                        canal="whatsapp",
                        cliente=cliente,
                    ),
                    resultado=ResultadoAtendimento(
                        estado=EstadoAtendimento.HANDOFF_HUMANO,
                        mensagem="Este tipo de mensagem precisa de atendimento humano.",
                    ),
                )
            runtime_atual = self._handoff_resultado(
                runtime=previous,
                motivo=f"mensagem_whatsapp_nao_suportada:{mensagem.tipo}",
            )

        checkout = runtime_atual.resultado.checkout
        db = self._session_factory()
        try:
            store = EncryptedSQLAlchemyChannelStateStore(db)
            estado_anterior = store.obter(
                contexto=contexto,
                canal="whatsapp",
                recipient=mensagem.remetente,
            )
            salvo = store.salvar(
                contexto=contexto,
                canal="whatsapp",
                recipient=mensagem.remetente,
                conversa_id=conversa_id,
                estado=runtime_atual.resultado.estado.value,
                state=_serializar_runtime(runtime_atual),
                pedido_id=checkout.pedido_id if checkout is not None else None,
                pagamento_id=checkout.pagamento_id if checkout is not None else None,
                entrega_id=checkout.entrega_id if checkout is not None else None,
                ultimo_inbound_id=mensagem.mensagem_id,
                ultimo_outbound_id=(
                    estado_anterior.ultimo_outbound_id
                    if estado_anterior is not None
                    else None
                ),
                ultimo_status_hash=(
                    estado_anterior.ultimo_status_hash
                    if estado_anterior is not None
                    else None
                ),
                versao_esperada=(
                    estado_anterior.versao if estado_anterior is not None else 0
                ),
            )
            envelope = self._envelope(
                contexto=contexto,
                mensagem=mensagem,
                sender_hash=store.sender_hash(
                    tenant_id=tenant_id,
                    unidade_id=unidade_id,
                    canal="whatsapp",
                    recipient=mensagem.remetente,
                ),
            )
            inbox = RepositorioInboxSQLAlchemy(db)
            if not inbox.ja_processada(
                envelope.tenant_id,
                envelope.unidade_id,
                envelope.idempotency_key,
            ):
                if db.get(
                    InboxEventoORM,
                    (tenant_id, unidade_id, str(envelope.idempotency_key)),
                ) is None:
                    inbox.registrar(envelope)
                inbox.marcar_processada(
                    envelope.tenant_id,
                    envelope.unidade_id,
                    envelope.idempotency_key,
                )
            self._auditar(
                session=db,
                contexto=contexto,
                mensagem_id=mensagem.mensagem_id,
                resultado="processado",
                estado=salvo.estado,
            )
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        try:
            outbound_id = adapter.enviar_whatsapp(
                destinatario=mensagem.remetente,
                texto=runtime_atual.resultado.mensagem,
                idempotency_key=f"reply:{mensagem.mensagem_id}",
            )
        except ErroProvedorExterno:
            handoff_runtime = self._handoff_resultado(
                runtime=runtime_atual,
                motivo="falha_envio_whatsapp_reconciliacao_obrigatoria",
            )
            db = self._session_factory()
            try:
                store = EncryptedSQLAlchemyChannelStateStore(db)
                atual = store.obter(
                    contexto=contexto,
                    canal="whatsapp",
                    recipient=mensagem.remetente,
                )
                if atual is not None:
                    store.salvar(
                        contexto=contexto,
                        canal="whatsapp",
                        recipient=mensagem.remetente,
                        conversa_id=atual.conversa_id,
                        estado=EstadoAtendimento.HANDOFF_HUMANO.value,
                        state=_serializar_runtime(handoff_runtime),
                        pedido_id=atual.pedido_id,
                        pagamento_id=atual.pagamento_id,
                        entrega_id=atual.entrega_id,
                        ultimo_inbound_id=atual.ultimo_inbound_id,
                        ultimo_outbound_id=atual.ultimo_outbound_id,
                        ultimo_status_hash=atual.ultimo_status_hash,
                        versao_esperada=atual.versao,
                    )
                self._auditar(
                    session=db,
                    contexto=contexto,
                    mensagem_id=mensagem.mensagem_id,
                    resultado="falha_canal_handoff",
                    estado=EstadoAtendimento.HANDOFF_HUMANO.value,
                )
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()
            return ResultadoMensagemCanal(
                mensagem_id=mensagem.mensagem_id,
                duplicada=False,
                outbound_id=None,
                estado=EstadoAtendimento.HANDOFF_HUMANO.value,
                handoff=True,
            )

        db = self._session_factory()
        try:
            store = EncryptedSQLAlchemyChannelStateStore(db)
            store.registrar_outbound(
                contexto=contexto,
                canal="whatsapp",
                recipient=mensagem.remetente,
                outbound_id=outbound_id,
            )
            self._auditar(
                session=db,
                contexto=contexto,
                mensagem_id=mensagem.mensagem_id,
                resultado="resposta_enviada",
                estado=runtime_atual.resultado.estado.value,
            )
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
        return ResultadoMensagemCanal(
            mensagem_id=mensagem.mensagem_id,
            duplicada=False,
            outbound_id=outbound_id,
            estado=runtime_atual.resultado.estado.value,
            handoff=runtime_atual.resultado.estado is EstadoAtendimento.HANDOFF_HUMANO,
        )
