"""Contexto comercial governado do Delivery Próprio V1.

Este boundary substitui o escopo demo por identidade autenticada, cliente CRM
persistido, endereço cifrado previamente validado, catálogo da unidade e política
real de entrega. Não abre nem encerra transações.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from core.crm.modelos import ClienteCRM
from core.delivery.erros import ErroDelivery
from core.delivery.modelos import AreaEntrega, OrigemEntrega, ProdutoDelivery
from core.seguranca.autenticacao import IdentidadeUsuario
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.erros import UsuarioInativo
from infra.crm.clientes_sqlalchemy import LeitorClientesCRMSQLAlchemy
from infra.crm.enderecos_sqlalchemy import (
    EncryptedSQLAlchemyAddressStore,
    EnderecoClienteResolvido,
)
from infra.delivery.catalogo_sqlalchemy import CatalogoDeliverySQLAlchemy
from infra.delivery.politica_sqlalchemy import RepositorioPoliticaEntregaSQLAlchemy


@dataclass(frozen=True)
class ContextoDeliveryComercialV1:
    contexto: ContextoExecucao
    cliente: ClienteCRM
    endereco: EnderecoClienteResolvido
    catalogo: tuple[ProdutoDelivery, ...]
    origem_entrega: OrigemEntrega
    areas_entrega: tuple[AreaEntrega, ...]


def resolver_contexto_delivery_comercial(
    *,
    session: Session,
    identidade: IdentidadeUsuario,
    cliente_id: str,
    endereco_ref: str | None = None,
    master_key: str | None = None,
) -> ContextoDeliveryComercialV1:
    """Resolve somente recursos pertencentes ao escopo autenticado.

    ``cliente_id`` nunca define tenant/unidade. Esses valores vêm exclusivamente da
    identidade autenticada; leituras de cliente, endereço, catálogo e política são
    então filtradas pelo mesmo escopo.
    """

    if not identidade.ativo:
        raise UsuarioInativo("usuario indisponivel")
    cliente_ref = cliente_id.strip()
    if not cliente_ref:
        raise ErroDelivery("cliente_delivery_obrigatorio")

    contexto = identidade.contexto(origem="delivery-proprio-commercial-v1")
    clientes = LeitorClientesCRMSQLAlchemy(session)
    cliente = clientes.obter(
        tenant_id=contexto.tenant_id,
        unidade_id=contexto.unidade_id,
        cliente_id=cliente_ref,
    )
    if cliente is None:
        raise ErroDelivery("cliente_delivery_indisponivel")

    enderecos = EncryptedSQLAlchemyAddressStore(session, master_key=master_key)
    referencia = endereco_ref
    if referencia is None:
        referencia = enderecos.ultimo_ref(
            contexto=contexto,
            cliente_id=cliente.cliente_id,
        )
    if not referencia:
        raise ErroDelivery("endereco_delivery_indisponivel")
    try:
        endereco = enderecos.resolver(
            contexto=contexto,
            cliente_id=cliente.cliente_id,
            referencia=referencia,
        )
    except LookupError as exc:
        raise ErroDelivery("endereco_delivery_indisponivel") from exc

    politica = RepositorioPoliticaEntregaSQLAlchemy(session)
    origem = politica.obter_origem(
        tenant_id=contexto.tenant_id,
        unidade_id=contexto.unidade_id,
    )
    if origem is None:
        raise ErroDelivery("origem_delivery_indisponivel")
    areas = politica.listar_areas(
        tenant_id=contexto.tenant_id,
        unidade_id=contexto.unidade_id,
    )
    if not areas:
        raise ErroDelivery("politica_delivery_indisponivel")

    catalogo = CatalogoDeliverySQLAlchemy(session).listar(
        tenant_id=contexto.tenant_id,
        unidade_id=contexto.unidade_id,
    )
    return ContextoDeliveryComercialV1(
        contexto=contexto,
        cliente=cliente,
        endereco=endereco,
        catalogo=catalogo,
        origem_entrega=origem,
        areas_entrega=areas,
    )
