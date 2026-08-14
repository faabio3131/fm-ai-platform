"""Smoke test real do PagBank sandbox sem expor token ou gravar PII no banco.

Fluxo:
    python -m scripts.pagbank_sandbox_smoke_v1 create --amount 1.00 --admin-email dono@empresa.com
    python -m scripts.pagbank_sandbox_smoke_v1 consult --order-id ORDE_xxx --admin-email dono@empresa.com

O token é resolvido pela referência ativa do SecretStore. Nome/e-mail/CPF do cliente
de teste são lidos interativamente e usados apenas na requisição ao sandbox.
"""

from __future__ import annotations

import argparse
import getpass
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from core.dominio.dinheiro import Dinheiro
from core.pagamentos.pagbank import ClientePagBank
from core.runtime import build_engine, check_database_health, load_runtime_settings
from core.seguranca.autenticacao import ServicoAutenticacao
from core.seguranca.permissoes import Permissao
from infra.pagamentos.pagbank_runtime import PagBankAdapterFactory
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy
from infra.seguranca.session_guard import build_session_factory
from migrations.runner import run_migrations


def _valor(raw: str) -> Dinheiro:
    try:
        valor = Decimal(raw.replace(",", "."))
    except InvalidOperation as exc:
        raise RuntimeError("valor invalido") from exc
    if valor <= 0:
        raise RuntimeError("valor deve ser positivo")
    return Dinheiro(valor)


def _autenticar(session, *, email: str, tenant_id: str, unidade_id: str) -> None:
    password = getpass.getpass("Senha do administrador: ")
    identidade = ServicoAutenticacao(
        RepositorioIdentidadesSQLAlchemy(session)
    ).autenticar(email=email, password=password)
    if identidade.tenant_id != tenant_id or unidade_id not in identidade.unidades_permitidas:
        raise RuntimeError("administrador fora do escopo tenant/unidade do runtime")
    if Permissao.INTEGRACAO_GERENCIAR not in identidade.permissoes:
        raise RuntimeError("usuario autenticado nao pode gerenciar integracoes")


def _cliente_interativo() -> ClientePagBank:
    nome = input("Nome do cliente de teste: ").strip()
    email = input("E-mail do cliente de teste: ").strip()
    tax_id = getpass.getpass("CPF/CNPJ do cliente de teste (não será exibido): ").strip()
    return ClientePagBank(nome=nome, email=email, tax_id=tax_id)


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test real PagBank sandbox.")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create")
    create.add_argument("--amount", required=True)
    create.add_argument("--admin-email", required=True)

    consult = sub.add_parser("consult")
    consult.add_argument("--order-id", required=True)
    consult.add_argument("--admin-email", required=True)

    args = parser.parse_args()
    settings = load_runtime_settings()
    engine = build_engine(settings)
    health = check_database_health(engine)
    if not health.ok:
        raise RuntimeError(health.detail)
    run_migrations(engine)
    factory = build_session_factory(engine=engine, commercial=settings.commercial)

    with factory() as session:
        _autenticar(
            session,
            email=args.admin_email,
            tenant_id=settings.tenant_id,
            unidade_id=settings.unidade_id,
        )
        adapter = PagBankAdapterFactory().construir(
            session=session,
            tenant_id=settings.tenant_id,
            unidade_id=settings.unidade_id,
        )

        if args.command == "create":
            # Mantém a chave enviada ao PagBank estritamente alfanumérica.
            referencia = f"smoke{uuid4().hex}"
            cobranca = adapter.criar_pix(
                pagamento_id=referencia,
                valor=_valor(args.amount),
                idempotency_key=referencia,
                cliente=_cliente_interativo(),
                descricao="Homologacao Gerente AI",
            )
            exibicao = dict(cobranca.payload_exibicao)
            print(f"PagBank order_id={cobranca.id_externo} | status={cobranca.status}")
            if exibicao.get("pix_copia_cola"):
                print(f"PIX copia e cola: {exibicao['pix_copia_cola']}")
            if exibicao.get("qr_code_png_url"):
                print(f"QR PNG disponível: {exibicao['qr_code_png_url']}")
            return 0

        cobranca = adapter.consultar_transacao(args.order_id)
        if cobranca is None:
            print("Cobrança não encontrada.")
            return 2
        print(
            f"PagBank order_id={cobranca.id_externo} | status={cobranca.status} | "
            f"valor=R$ {cobranca.valor.valor:.2f}"
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
