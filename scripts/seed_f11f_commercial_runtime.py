"""Seed comercial descartável do gate F11-F — Delivery Próprio no app.py real.

Executa em CI/staging PostgreSQL, sem FM_AI_TEST_MODE. Cria somente dados de
entrada do cenário comercial: identidade/RBAC, escopo legado governado, CRM,
endereço validado e política de entrega. Pedido, Pagamento, Reserva e Entrega
são criados exclusivamente pela jornada browser + application canônica.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from core.delivery.modelos import AreaEntrega
from core.seguranca import Papel
from core.seguranca.autenticacao import IdentidadeUsuario
from infra.crm.enderecos_sqlalchemy import EncryptedSQLAlchemyAddressStore
from infra.delivery.politica_sqlalchemy import RepositorioPoliticaEntregaSQLAlchemy
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy
from migrations.runner import run_migrations

TENANT_A = "tenant-f11f-a"
UNIDADE_A = "unidade-f11f-a"
TENANT_B = "tenant-f11f-b"
UNIDADE_B = "unidade-f11f-b"
LOJA_A = 11001
LOJA_B = 11002
PRODUTO_ID = 11001
INSUMO_ID = 11001
FICHA_ID = 11001
CLIENTE_A = "cliente-f11f-a"
CLIENTE_FORA = "cliente-f11f-out"
CLIENTE_B = "cliente-f11f-x"
AGORA = datetime(2026, 9, 5, 18, 0, tzinfo=UTC)


def _env(nome: str) -> str:
    valor = os.environ.get(nome, "").strip()
    if not valor:
        raise RuntimeError(f"{nome} obrigatorio no F11-F")
    return valor


def _identidade(*, tenant_id: str, unidade_id: str, usuario_id: str, email: str) -> IdentidadeUsuario:
    return IdentidadeUsuario(
        usuario_id=usuario_id,
        email=email,
        senha_hash="seed-f11f-context-only",
        tenant_id=tenant_id,
        unidade_id=unidade_id,
        papeis=frozenset({Papel.GERENTE}),
        unidades_permitidas=frozenset({unidade_id}),
        ativo=True,
    )


def _seed_legacy_scope(session: Session) -> None:
    session.execute(
        text(
            "INSERT INTO lojas (id, nome_fantasia) VALUES "
            "(:a, 'Loja F11-F A'), (:b, 'Loja F11-F B') "
            "ON CONFLICT (id) DO NOTHING"
        ),
        {"a": LOJA_A, "b": LOJA_B},
    )
    session.execute(
        text(
            "INSERT INTO fm_unidade_loja_legacy_v1 "
            "(tenant_id, unidade_id, loja_id, ativo) VALUES "
            "(:ta, :ua, :la, TRUE), (:tb, :ub, :lb, TRUE) "
            "ON CONFLICT (tenant_id, unidade_id) DO NOTHING"
        ),
        {
            "ta": TENANT_A,
            "ua": UNIDADE_A,
            "la": LOJA_A,
            "tb": TENANT_B,
            "ub": UNIDADE_B,
            "lb": LOJA_B,
        },
    )
    session.execute(
        text(
            "INSERT INTO produtos "
            "(id, nome, categoria, descricao_bruta, descricao_ai, preco_venda, "
            "custo_total_cmv, margem_exibicao, imagem_path, loja_id) VALUES "
            "(:id, 'Burger Delivery F11-F', 'Lanches', '', '', 32.00, 12.00, '', NULL, :loja) "
            "ON CONFLICT (id) DO NOTHING"
        ),
        {"id": PRODUTO_ID, "loja": LOJA_A},
    )
    session.execute(
        text(
            "INSERT INTO insumos "
            "(id, nome, unidade_medida, saldo_atual, estoque_minimo, custo_unitario, "
            "data_fabricacao, data_validade, dias_alerta_vencimento, loja_id) VALUES "
            "(:id, 'Burger Base F11-F', 'un', 30, 2, 12.00, NULL, NULL, 15, :loja) "
            "ON CONFLICT (id) DO NOTHING"
        ),
        {"id": INSUMO_ID, "loja": LOJA_A},
    )
    session.execute(
        text(
            "INSERT INTO fichas_tecnicas "
            "(id, produto_id, insumo_id, quantidade_utilizada) "
            "VALUES (:id, :produto, :insumo, 1) ON CONFLICT (id) DO NOTHING"
        ),
        {"id": FICHA_ID, "produto": PRODUTO_ID, "insumo": INSUMO_ID},
    )


def _seed_clientes(session: Session) -> None:
    clientes = (
        (TENANT_A, UNIDADE_A, CLIENTE_A, "01001000", "Rua Cliente A, 10 - Centro - Sao Paulo/SP"),
        (TENANT_A, UNIDADE_A, CLIENTE_FORA, "99999999", "Rua Fora da Area, 20 - Sao Paulo/SP"),
        (TENANT_B, UNIDADE_B, CLIENTE_B, "02001000", "Rua Cliente B, 30 - Centro - Sao Paulo/SP"),
    )
    for indice, (tenant, unidade, cliente_id, _cep, _endereco) in enumerate(clientes, start=1):
        session.execute(
            text(
                "INSERT INTO crm_clientes_v1 "
                "(tenant_id, unidade_id, cliente_id, origem, marketplace_origem, criado_em, versao) "
                "VALUES (:tenant, :unidade, :cliente, 'delivery_proprio', NULL, :agora, 1) "
                "ON CONFLICT (tenant_id, unidade_id, cliente_id) DO NOTHING"
            ),
            {
                "tenant": tenant,
                "unidade": unidade,
                "cliente": cliente_id,
                "agora": AGORA.replace(microsecond=indice),
            },
        )
        session.execute(
            text(
                "INSERT INTO crm_cliente_contatos_v1 "
                "(tenant_id, unidade_id, cliente_id, canal, referencia) "
                "VALUES (:tenant, :unidade, :cliente, 'whatsapp', :ref) "
                "ON CONFLICT DO NOTHING"
            ),
            {
                "tenant": tenant,
                "unidade": unidade,
                "cliente": cliente_id,
                "ref": f"contact://{cliente_id}",
            },
        )

    gerente_a = _identidade(
        tenant_id=TENANT_A,
        unidade_id=UNIDADE_A,
        usuario_id="gerente-f11f-a",
        email=_env("F11F_GERENTE_EMAIL"),
    )
    gerente_b = _identidade(
        tenant_id=TENANT_B,
        unidade_id=UNIDADE_B,
        usuario_id="gerente-f11f-b",
        email=_env("F11F_OTHER_GERENTE_EMAIL"),
    )
    enderecos = EncryptedSQLAlchemyAddressStore(session)
    for identidade, cliente_id, cep, endereco, indice in (
        (gerente_a, CLIENTE_A, "01001000", "Rua Cliente A, 10 - Centro - Sao Paulo/SP", 1),
        (gerente_a, CLIENTE_FORA, "99999999", "Rua Fora da Area, 20 - Sao Paulo/SP", 2),
        (gerente_b, CLIENTE_B, "02001000", "Rua Cliente B, 30 - Centro - Sao Paulo/SP", 3),
    ):
        contexto = identidade.contexto(
            origem="scripts.seed_f11f_commercial_runtime",
            correlation_id=f"corr-f11f-address-{indice}",
            solicitado_em=AGORA,
        )
        enderecos.armazenar_validado(
            contexto=contexto,
            cliente_id=cliente_id,
            endereco_formatado=endereco,
            cep=cep,
            place_id=f"place-f11f-{indice}",
            latitude=Decimal("-23.5505") + Decimal(indice) / Decimal(10000),
            longitude=Decimal("-46.6333") - Decimal(indice) / Decimal(10000),
            agora=AGORA.replace(microsecond=100 + indice),
        )


def _seed_politicas(session: Session) -> None:
    repo = RepositorioPoliticaEntregaSQLAlchemy(session)
    repo.configurar_origem(
        tenant_id=TENANT_A,
        unidade_id=UNIDADE_A,
        endereco_texto="Rua Unidade A, 100 - Centro - Sao Paulo/SP",
    )
    repo.configurar_area(
        area=AreaEntrega(
            area_id="centro-f11f-a",
            tenant_id=TENANT_A,
            unidade_id=UNIDADE_A,
            nome="Centro F11-F",
            prefixos_cep=("010",),
            taxa=Decimal("7.00"),
            sla_minutos=25,
            sla_maxutos=45,
            versao=1,
        )
    )
    repo.configurar_origem(
        tenant_id=TENANT_B,
        unidade_id=UNIDADE_B,
        endereco_texto="Rua Unidade B, 200 - Centro - Sao Paulo/SP",
    )
    repo.configurar_area(
        area=AreaEntrega(
            area_id="centro-f11f-b",
            tenant_id=TENANT_B,
            unidade_id=UNIDADE_B,
            nome="Centro Tenant B",
            prefixos_cep=("020",),
            taxa=Decimal("8.00"),
            sla_minutos=30,
            sla_maxutos=50,
            versao=1,
        )
    )


def _seed_identidades(session: Session) -> None:
    repo = RepositorioIdentidadesSQLAlchemy(session)
    usuarios = (
        (
            _env("F11F_GERENTE_EMAIL"),
            _env("F11F_GERENTE_PASSWORD"),
            TENANT_A,
            UNIDADE_A,
            Papel.GERENTE,
            "gerente-f11f-a",
        ),
        (
            _env("F11F_GARCOM_EMAIL"),
            _env("F11F_GARCOM_PASSWORD"),
            TENANT_A,
            UNIDADE_A,
            Papel.GARCOM,
            "garcom-f11f-a",
        ),
        (
            _env("F11F_OTHER_GERENTE_EMAIL"),
            _env("F11F_OTHER_GERENTE_PASSWORD"),
            TENANT_B,
            UNIDADE_B,
            Papel.GERENTE,
            "gerente-f11f-b",
        ),
    )
    for email, password, tenant, unidade, papel, usuario_id in usuarios:
        if repo.obter_por_email(email) is None:
            repo.criar_usuario(
                email=email,
                password=password,
                tenant_id=tenant,
                unidade_padrao_id=unidade,
                papeis=(papel,),
                unidades_permitidas=(unidade,),
                usuario_id=usuario_id,
            )


def main() -> None:
    if os.getenv("FM_AI_TEST_MODE") == "1":
        raise RuntimeError("F11-F recusa FM_AI_TEST_MODE=1")
    if os.getenv("FM_AI_ENV", "").strip().lower() != "staging":
        raise RuntimeError("F11-F seed permitido somente em staging descartavel")

    engine = create_engine(_env("DATABASE_URL"), future=True)
    run_migrations(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with factory.begin() as session:
        _seed_legacy_scope(session)
        _seed_identidades(session)
        _seed_clientes(session)
        _seed_politicas(session)

    print("F11-F commercial PostgreSQL seed ready")


if __name__ == "__main__":
    main()
