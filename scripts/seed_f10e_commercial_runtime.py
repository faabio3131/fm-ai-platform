"""Seed comercial determinístico do F10-E — KDS → Expedição → Entregador.

Executa somente em CI/staging descartável, sem FM_AI_TEST_MODE. Reaproveita a
fundação comercial F8-E (Pedido, pagamento, estoque, KDS e identidades) e
acrescenta a Entrega canônica e as identidades reais de EXPEDICAO/ENTREGADOR.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.entrega import (
    Entrega,
    ModalidadeEntrega,
    RepositorioEntregaSQLAlchemy,
    ServicoEntrega,
    StatusEntrega,
)
from core.entrega.integracoes_sqlalchemy import (
    financeiro_resolvido_sqlalchemy,
    pedido_cancelado_sqlalchemy,
)
from core.seguranca import ContextoExecucao, Papel
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy
from scripts import seed_f8e_commercial_runtime as f8e

TENANT = "tenant-f8e"
UNIDADE = "unidade-f8e"
PEDIDO_ID = "pedido-f8e"
ENTREGA_ID = "entrega-f10e"
AGORA = datetime(2026, 9, 4, 18, 45, tzinfo=UTC)

EXPEDICAO_EMAIL = os.environ["F10E_EXPEDICAO_EMAIL"]
EXPEDICAO_PASSWORD = os.environ["F10E_EXPEDICAO_PASSWORD"]
ENTREGADOR_EMAIL = os.environ["F10E_ENTREGADOR_EMAIL"]
ENTREGADOR_PASSWORD = os.environ["F10E_ENTREGADOR_PASSWORD"]


def _garantir_identidades(session) -> None:
    repo = RepositorioIdentidadesSQLAlchemy(session)
    if repo.obter_por_email(EXPEDICAO_EMAIL) is None:
        repo.criar_usuario(
            email=EXPEDICAO_EMAIL,
            password=EXPEDICAO_PASSWORD,
            tenant_id=TENANT,
            unidade_padrao_id=UNIDADE,
            papeis=(Papel.EXPEDICAO,),
            unidades_permitidas=(UNIDADE,),
            usuario_id="expedicao-f10e",
        )
    if repo.obter_por_email(ENTREGADOR_EMAIL) is None:
        repo.criar_usuario(
            email=ENTREGADOR_EMAIL,
            password=ENTREGADOR_PASSWORD,
            tenant_id=TENANT,
            unidade_padrao_id=UNIDADE,
            papeis=(Papel.ENTREGADOR,),
            unidades_permitidas=(UNIDADE,),
            usuario_id="entregador-f10e",
        )


def _garantir_entrega(session) -> None:
    repo = RepositorioEntregaSQLAlchemy(session)
    existente = repo.buscar_por_pedido(TENANT, UNIDADE, PEDIDO_ID)
    if existente is not None:
        return

    contexto = ContextoExecucao.sistema(
        identidade="seed-f10e",
        motivo="seed comercial da Entrega antes do KDS ficar pronto",
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        correlation_id="corr-seed-f10e",
        solicitado_em=AGORA,
    )
    ServicoEntrega(
        repo,
        financeiro_resolvido=lambda tenant, unidade, pedido: financeiro_resolvido_sqlalchemy(
            session, tenant, unidade, pedido
        ),
        pedido_cancelado=lambda tenant, unidade, pedido: pedido_cancelado_sqlalchemy(
            session, tenant, unidade, pedido
        ),
        agora=lambda: AGORA,
    ).criar(
        Entrega(
            entrega_id=ENTREGA_ID,
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            pedido_id=PEDIDO_ID,
            endereco_id="endereco-f10e",
            modalidade=ModalidadeEntrega.PROPRIA,
            status=StatusEntrega.AGUARDANDO_PRODUCAO,
            versao=1,
        ),
        contexto=contexto,
        idempotency_key="seed:entrega:f10e",
    )


def main() -> None:
    if os.getenv("FM_AI_TEST_MODE") == "1":
        raise RuntimeError("F10-E nao pode executar com FM_AI_TEST_MODE=1")

    # Fundação comercial já validada: Pedido confirmado, pagamento resolvido,
    # estoque reservado, setor KDS e logins COZINHA/GARCOM reais.
    f8e.main()

    engine = create_engine(os.environ["DATABASE_URL"], future=True)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with factory.begin() as session:
        _garantir_identidades(session)
        _garantir_entrega(session)

    print("F10-E commercial seed ready; Entrega aguarda producao KDS real")


if __name__ == "__main__":
    main()
