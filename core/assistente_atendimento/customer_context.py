"""Contexto autorizado e minimizado do cliente para o Assistente V1.

Não é uma nova autoridade de CRM. É uma projeção de leitura derivada de ClienteCRM,
consentimentos históricos, pedidos canônicos e referências de endereço cifradas.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class ItemHistoricoAtendimento:
    produto_id: str
    nome_produto: str
    quantidade: int

    def __post_init__(self) -> None:
        if not self.produto_id.strip() or not self.nome_produto.strip():
            raise ValueError("item_historico_invalido")
        if self.quantidade < 1:
            raise ValueError("quantidade_historico_invalida")


@dataclass(frozen=True)
class PedidoHistoricoAtendimento:
    pedido_id: str
    status: str
    criado_em: datetime
    total: Decimal
    itens: tuple[ItemHistoricoAtendimento, ...]

    def __post_init__(self) -> None:
        if not self.pedido_id.strip() or not self.status.strip():
            raise ValueError("pedido_historico_invalido")
        if self.criado_em.tzinfo is None or self.criado_em.utcoffset() is None:
            raise ValueError("pedido_historico_sem_timezone")
        if self.total < 0 or not self.itens:
            raise ValueError("pedido_historico_inconsistente")


@dataclass(frozen=True)
class ConsentimentoContextoAtendimento:
    canal: str
    finalidade: str
    status: str
    ocorrido_em: datetime

    def __post_init__(self) -> None:
        if any(not item.strip() for item in (self.canal, self.finalidade, self.status)):
            raise ValueError("consentimento_contexto_invalido")
        if self.ocorrido_em.tzinfo is None or self.ocorrido_em.utcoffset() is None:
            raise ValueError("consentimento_contexto_sem_timezone")


@dataclass(frozen=True)
class ContextoClienteAutorizado:
    cliente_ref: str
    finalidade: str = "atendimento"
    historico: tuple[PedidoHistoricoAtendimento, ...] = ()
    consentimentos: tuple[ConsentimentoContextoAtendimento, ...] = ()
    ultimo_endereco_ref: str | None = None

    def __post_init__(self) -> None:
        if not self.cliente_ref.strip():
            raise ValueError("cliente_contexto_sem_referencia")
        if self.finalidade != "atendimento":
            raise ValueError("finalidade_contexto_nao_autorizada")
        if self.ultimo_endereco_ref is not None and not self.ultimo_endereco_ref.startswith(
            "address://"
        ):
            raise ValueError("referencia_endereco_invalida")

    @property
    def possui_historico(self) -> bool:
        return bool(self.historico)

    @property
    def possui_endereco_salvo(self) -> bool:
        return self.ultimo_endereco_ref is not None
