"""Adapter SQLAlchemy do carrinho comercial do Delivery Próprio V1."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, cast

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.delivery.carrinho_orm import CarrinhoDeliveryORM
from core.delivery.erros import ErroDelivery
from core.delivery.modelos import (
    CarrinhoDelivery,
    CotacaoEntrega,
    EnderecoDelivery,
    ItemCarrinhoDelivery,
    StatusCarrinhoDelivery,
)


def _payload(carrinho: CarrinhoDelivery) -> dict[str, object]:
    endereco: dict[str, object] | None = None
    if carrinho.endereco is not None:
        endereco = {
            "endereco_id": carrinho.endereco.endereco_id,
            "cliente_ref": carrinho.endereco.cliente_ref,
            "cep": carrinho.endereco.cep,
            "logradouro": carrinho.endereco.logradouro,
            "numero": carrinho.endereco.numero,
            "bairro": carrinho.endereco.bairro,
            "cidade": carrinho.endereco.cidade,
            "uf": carrinho.endereco.uf,
            "validado": carrinho.endereco.validado,
        }

    cotacao: dict[str, object] | None = None
    if carrinho.cotacao is not None:
        cotacao = {
            "area_id": carrinho.cotacao.area_id,
            "nome_area": carrinho.cotacao.nome_area,
            "taxa": str(carrinho.cotacao.taxa),
            "sla_minutos": carrinho.cotacao.sla_minutos,
            "sla_maxutos": carrinho.cotacao.sla_maxutos,
            "versao_area": carrinho.cotacao.versao_area,
        }

    itens = [
        {
            "produto_id": item.produto_id,
            "nome": item.nome,
            "quantidade": item.quantidade,
            "preco_unitario": str(item.preco_unitario),
            "custo_estimado_unitario": str(item.custo_estimado_unitario),
            "produto_versao": item.produto_versao,
        }
        for item in carrinho.itens
    ]

    return {
        "itens": itens,
        "endereco": endereco,
        "cotacao": cotacao,
        "cupom_codigo": carrinho.cupom_codigo,
        "desconto_cupom": str(carrinho.desconto_cupom),
        "cashback_reservado": str(carrinho.cashback_reservado),
        "pedido_id": carrinho.pedido_id,
        "idempotency_confirmacao": carrinho.idempotency_confirmacao,
    }


def _modelo(row: CarrinhoDeliveryORM) -> CarrinhoDelivery:
    payload = cast(dict[str, Any], row.payload)
    itens_payload = cast(list[dict[str, Any]], payload.get("itens", []))
    endereco_payload = cast(dict[str, Any] | None, payload.get("endereco"))
    cotacao_payload = cast(dict[str, Any] | None, payload.get("cotacao"))

    endereco = (
        None
        if endereco_payload is None
        else EnderecoDelivery(
            endereco_id=str(endereco_payload["endereco_id"]),
            cliente_ref=str(endereco_payload["cliente_ref"]),
            cep=str(endereco_payload["cep"]),
            logradouro=str(endereco_payload["logradouro"]),
            numero=str(endereco_payload["numero"]),
            bairro=str(endereco_payload["bairro"]),
            cidade=str(endereco_payload["cidade"]),
            uf=str(endereco_payload["uf"]),
            validado=bool(endereco_payload["validado"]),
        )
    )
    cotacao = (
        None
        if cotacao_payload is None
        else CotacaoEntrega(
            area_id=str(cotacao_payload["area_id"]),
            nome_area=str(cotacao_payload["nome_area"]),
            taxa=Decimal(str(cotacao_payload["taxa"])),
            sla_minutos=int(cotacao_payload["sla_minutos"]),
            sla_maxutos=int(cotacao_payload["sla_maxutos"]),
            versao_area=int(cotacao_payload["versao_area"]),
        )
    )
    itens = tuple(
        ItemCarrinhoDelivery(
            produto_id=str(item["produto_id"]),
            nome=str(item["nome"]),
            quantidade=int(item["quantidade"]),
            preco_unitario=Decimal(str(item["preco_unitario"])),
            custo_estimado_unitario=Decimal(
                str(item["custo_estimado_unitario"])
            ),
            produto_versao=int(item["produto_versao"]),
        )
        for item in itens_payload
    )

    return CarrinhoDelivery(
        carrinho_id=row.carrinho_id,
        tenant_id=row.tenant_id,
        unidade_id=row.unidade_id,
        cliente_ref=row.cliente_ref,
        versao=row.versao,
        status=StatusCarrinhoDelivery(row.status),
        itens=itens,
        endereco=endereco,
        cotacao=cotacao,
        cupom_codigo=cast(str | None, payload.get("cupom_codigo")),
        desconto_cupom=Decimal(str(payload.get("desconto_cupom", "0.00"))),
        cashback_reservado=Decimal(
            str(payload.get("cashback_reservado", "0.00"))
        ),
        pedido_id=cast(str | None, payload.get("pedido_id")),
        idempotency_confirmacao=cast(
            str | None, payload.get("idempotency_confirmacao")
        ),
    )


class RepositorioCarrinhosDeliverySQLAlchemy:
    """Persiste carrinhos com CAS; nunca controla commit/rollback da UoW."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def criar(self, carrinho: CarrinhoDelivery) -> CarrinhoDelivery:
        row = CarrinhoDeliveryORM(
            tenant_id=carrinho.tenant_id,
            unidade_id=carrinho.unidade_id,
            carrinho_id=carrinho.carrinho_id,
            cliente_ref=carrinho.cliente_ref,
            versao=carrinho.versao,
            status=carrinho.status.value,
            payload=_payload(carrinho),
        )
        self._session.add(row)
        try:
            self._session.flush()
        except IntegrityError as exc:
            raise ErroDelivery("carrinho_duplicado") from exc
        return carrinho

    def obter(
        self, *, tenant_id: str, unidade_id: str, carrinho_id: str
    ) -> CarrinhoDelivery | None:
        row = self._session.get(
            CarrinhoDeliveryORM,
            (tenant_id, unidade_id, carrinho_id),
        )
        return None if row is None else _modelo(row)

    def obter_do_cliente(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        cliente_ref: str,
        carrinho_id: str,
    ) -> CarrinhoDelivery | None:
        row = self._session.execute(
            select(CarrinhoDeliveryORM).where(
                CarrinhoDeliveryORM.tenant_id == tenant_id,
                CarrinhoDeliveryORM.unidade_id == unidade_id,
                CarrinhoDeliveryORM.cliente_ref == cliente_ref,
                CarrinhoDeliveryORM.carrinho_id == carrinho_id,
            )
        ).scalar_one_or_none()
        return None if row is None else _modelo(row)

    def salvar_cas(
        self, carrinho: CarrinhoDelivery, *, expected_version: int
    ) -> CarrinhoDelivery:
        if carrinho.versao != expected_version + 1:
            raise ErroDelivery("incremento_versao_invalido")

        updated = self._session.execute(
            update(CarrinhoDeliveryORM)
            .where(
                CarrinhoDeliveryORM.tenant_id == carrinho.tenant_id,
                CarrinhoDeliveryORM.unidade_id == carrinho.unidade_id,
                CarrinhoDeliveryORM.carrinho_id == carrinho.carrinho_id,
                CarrinhoDeliveryORM.versao == expected_version,
            )
            .values(
                cliente_ref=carrinho.cliente_ref,
                versao=carrinho.versao,
                status=carrinho.status.value,
                payload=_payload(carrinho),
            )
            .returning(CarrinhoDeliveryORM.carrinho_id)
        ).scalar_one_or_none()

        if updated is None:
            atual = self.obter(
                tenant_id=carrinho.tenant_id,
                unidade_id=carrinho.unidade_id,
                carrinho_id=carrinho.carrinho_id,
            )
            if atual is None:
                raise ErroDelivery("recurso_indisponivel")
            raise ErroDelivery("conflito_concorrencia")

        return carrinho
