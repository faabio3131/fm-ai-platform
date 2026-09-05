"""Fixture de staging F11-F para um benefício já resolvido antes do Checkout.

A UI comercial não fabrica cupom/cashback. Este helper representa a saída já
resolvida de uma autoridade promocional e injeta somente o snapshot do benefício
no carrinho persistido, via adapter comercial + CAS. O Checkout F11-D continua
sendo a autoridade que decide se o benefício atravessa a fronteira econômica.
"""

from __future__ import annotations

import os
from dataclasses import replace
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from core.delivery.carrinho_orm import CarrinhoDeliveryORM
from core.delivery.modelos import StatusCarrinhoDelivery
from infra.delivery.carrinhos_sqlalchemy import RepositorioCarrinhosDeliverySQLAlchemy

TENANT = "tenant-f11f-a"
UNIDADE = "unidade-f11f-a"
CLIENTE = "cliente-f11f-a"
CUPOM = "F11F5"
DESCONTO = Decimal("5.00")


def main() -> None:
    if os.getenv("FM_AI_TEST_MODE") == "1":
        raise RuntimeError("fixture F11-F recusa FM_AI_TEST_MODE=1")
    if os.getenv("FM_AI_ENV", "").strip().lower() != "staging":
        raise RuntimeError("fixture F11-F permitido somente em staging descartavel")
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL obrigatoria no F11-F")

    engine = create_engine(database_url, future=True)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with factory.begin() as session:
        _aplicar(session)


def _aplicar(session: Session) -> None:
    row = session.scalar(
        select(CarrinhoDeliveryORM)
        .where(
            CarrinhoDeliveryORM.tenant_id == TENANT,
            CarrinhoDeliveryORM.unidade_id == UNIDADE,
            CarrinhoDeliveryORM.cliente_ref == CLIENTE,
            CarrinhoDeliveryORM.status == StatusCarrinhoDelivery.ABERTO.value,
        )
        .order_by(CarrinhoDeliveryORM.atualizado_em.desc())
        .limit(1)
    )
    if row is None:
        raise RuntimeError("carrinho aberto F11-F nao encontrado")

    repo = RepositorioCarrinhosDeliverySQLAlchemy(session)
    carrinho = repo.obter_do_cliente(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        cliente_ref=CLIENTE,
        carrinho_id=row.carrinho_id,
    )
    if carrinho is None:
        raise RuntimeError("carrinho F11-F desapareceu durante fixture")
    if carrinho.cotacao is None or not carrinho.itens:
        raise RuntimeError("beneficio F11-F exige carrinho cotado e com item")

    if carrinho.cupom_codigo == CUPOM and carrinho.desconto_cupom == DESCONTO:
        print(f"F11-F resolved benefit already present: {carrinho.carrinho_id}")
        return
    if carrinho.cupom_codigo is not None or carrinho.desconto_cupom != Decimal("0.00"):
        raise RuntimeError("carrinho F11-F ja possui outro beneficio")

    atualizado = replace(
        carrinho,
        cupom_codigo=CUPOM,
        desconto_cupom=DESCONTO,
        versao=carrinho.versao + 1,
    )
    repo.salvar_cas(atualizado, expected_version=carrinho.versao)
    print(f"F11-F resolved benefit attached via CAS: {carrinho.carrinho_id}")


if __name__ == "__main__":
    main()
