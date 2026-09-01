"""Ponte governada entre Ficha Técnica legada e o estoque canônico V1.

A ficha existente continua sendo a fonte funcional durante o cutover. Este módulo
somente captura um snapshot imutável, ancora uma única vez o saldo legado no
ledger canônico e delega reserva/Pedido/Pagamento ao checkout autoritativo.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from application.checkout import (
    ComandoCheckoutV1,
    ResultadoCheckoutV1,
    executar_checkout_em_transacao,
)
from core.dominio.pedidos import Pedido
from core.estoque.modelos import ItemSnapshotFicha, SnapshotFichaEstoque, TipoMovimento
from core.estoque.servicos import registrar_movimento
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Permissao
from infra.legacy_product_scope import (
    listar_fichas_produto_legadas,
    obter_insumo_por_id_legado,
)
from infra.transacoes.uow import RecursosTransacionaisV1, UnitOfWorkV1


class ErroCatalogoEstoqueCutover(RuntimeError):
    """Ficha/saldo legado não pode ser promovido de forma determinística."""


def _produto_id_legado(valor: str) -> int:
    bruto = str(valor).strip()
    prefixo = "legacy:produto:"
    bruto = bruto.removeprefix(prefixo)
    try:
        produto_id = int(bruto)
    except (TypeError, ValueError) as exc:
        raise ErroCatalogoEstoqueCutover(
            "produto_sem_referencia_legada_deterministica"
        ) from exc
    if produto_id <= 0:
        raise ErroCatalogoEstoqueCutover(
            "produto_sem_referencia_legada_deterministica"
        )
    return produto_id


def _decimal_positivo(valor: object, *, codigo: str) -> Decimal:
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ErroCatalogoEstoqueCutover(codigo) from exc
    if not numero.is_finite() or numero <= 0:
        raise ErroCatalogoEstoqueCutover(codigo)
    return numero


def _saldo_legado(valor: object) -> Decimal:
    if valor is None:
        raise ErroCatalogoEstoqueCutover("saldo_legado_ausente")
    try:
        saldo = Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ErroCatalogoEstoqueCutover("saldo_legado_invalido") from exc
    if not saldo.is_finite() or saldo < 0:
        raise ErroCatalogoEstoqueCutover("saldo_legado_invalido")
    return saldo


def _unidade_medida(insumo: object) -> str:
    unidade = str(getattr(insumo, "unidade_medida", "") or "").strip()
    if not unidade:
        raise ErroCatalogoEstoqueCutover("unidade_medida_insumo_ausente")
    return unidade


def _contexto_estoque(
    contexto: ContextoExecucao,
    *,
    permissao: Permissao,
) -> ContextoExecucao:
    return replace(
        contexto,
        permissoes=frozenset({permissao}),
        unidades_permitidas=frozenset({contexto.unidade_id}),
        identidade_sistema=False,
        motivo_sistema=None,
    )


def _ancorar_saldo_legado(
    *,
    contexto: ContextoExecucao,
    recursos: RecursosTransacionaisV1,
    insumo: object,
) -> tuple[str, str]:
    insumo_legado_id = int(getattr(insumo, "id"))
    insumo_id = f"legacy:insumo:{insumo_legado_id}"
    unidade = _unidade_medida(insumo)
    esperado = _saldo_legado(getattr(insumo, "saldo_atual", None))
    saldo = recursos.estoque.consultar_saldo(
        contexto.tenant_id,
        contexto.unidade_id,
        insumo_id,
    )

    if saldo.versao == 0 and esperado > 0:
        bootstrap = registrar_movimento(
            contexto=_contexto_estoque(
                contexto,
                permissao=Permissao.ESTOQUE_AJUSTAR,
            ),
            repositorio=recursos.estoque,
            insumo_id=insumo_id,
            tipo=TipoMovimento.ENTRADA,
            quantidade_movimento=esperado,
            unidade_medida=unidade,
            origem_tipo="catalogo_cutover",
            origem_id=f"bootstrap:{insumo_id}",
            origem_versao=1,
            idempotency_key=f"catalogo:cutover:bootstrap:{insumo_id}",
            motivo="bootstrap controlado do saldo legado para o ledger canônico",
        )
        if not bootstrap.idempotente:
            recursos.registrar_efeitos(
                eventos=bootstrap.eventos,
                auditorias=bootstrap.auditorias,
            )
        saldo = recursos.estoque.consultar_saldo(
            contexto.tenant_id,
            contexto.unidade_id,
            insumo_id,
        )

    if saldo.saldo_fisico != esperado:
        raise ErroCatalogoEstoqueCutover(
            "estoque_legado_divergente_do_ledger:"
            f"{insumo_id}:canonico={saldo.saldo_fisico}:legado={esperado}"
        )

    return insumo_id, unidade


def preparar_snapshot_ficha_estoque_v1(
    *,
    session: Session,
    contexto: ContextoExecucao,
    pedido: Pedido,
    recursos: RecursosTransacionaisV1,
) -> SnapshotFichaEstoque | None:
    """Captura a ficha vigente e ancora os insumos no ledger sem criar nova ficha."""

    if (
        str(pedido.tenant_id) != contexto.tenant_id
        or str(pedido.unidade_id) != contexto.unidade_id
    ):
        raise ErroCatalogoEstoqueCutover("pedido_fora_do_escopo_da_ficha")

    itens_snapshot: list[ItemSnapshotFicha] = []
    definicoes_ficha: set[tuple[int, int, int, str, str]] = set()

    for item in pedido.itens:
        produto_legado_id = _produto_id_legado(str(item.produto_id))
        fichas = listar_fichas_produto_legadas(
            session,
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
            produto_id=produto_legado_id,
        )

        for ficha in fichas:
            ficha_id = int(ficha.id)
            insumo_legado_id = int(ficha.insumo_id)
            quantidade_unidade = _decimal_positivo(
                getattr(ficha, "quantidade_utilizada", None),
                codigo="quantidade_ficha_invalida",
            )
            insumo = obter_insumo_por_id_legado(
                session,
                tenant_id=contexto.tenant_id,
                unidade_id=contexto.unidade_id,
                insumo_id=insumo_legado_id,
                for_update=True,
            )
            if insumo is None:
                raise ErroCatalogoEstoqueCutover(
                    "insumo_ficha_fora_do_escopo"
                )
            insumo_id, unidade = _ancorar_saldo_legado(
                contexto=contexto,
                recursos=recursos,
                insumo=insumo,
            )
            quantidade_total = quantidade_unidade * Decimal(item.quantidade.valor)
            itens_snapshot.append(
                ItemSnapshotFicha(
                    produto_id=str(item.produto_id),
                    item_pedido_id=str(item.id),
                    insumo_id=insumo_id,
                    quantidade_por_unidade=quantidade_unidade,
                    quantidade_total=quantidade_total,
                    unidade_medida=unidade,
                )
            )
            definicoes_ficha.add(
                (
                    produto_legado_id,
                    ficha_id,
                    insumo_legado_id,
                    str(quantidade_unidade),
                    unidade,
                )
            )

    if not itens_snapshot:
        return None

    payload = sorted(definicoes_ficha)
    versao = hashlib.sha256(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()

    return SnapshotFichaEstoque(
        pedido_id=str(pedido.id),
        versao_ficha=f"legacy-ficha-sha256:{versao}",
        capturado_em=pedido.criado_em,
        itens=tuple(itens_snapshot),
    )


def executar_checkout_com_ficha_estoque_em_transacao(
    *,
    comando: ComandoCheckoutV1,
    contexto: ContextoExecucao,
    recursos: RecursosTransacionaisV1,
) -> ResultadoCheckoutV1:
    """Captura ficha + reserva usando a UoW já pertencente ao chamador."""

    if comando.snapshot_estoque is not None:
        raise ErroCatalogoEstoqueCutover(
            "snapshot_estoque_preexistente_nao_permitido_no_cutover"
        )

    snapshot = preparar_snapshot_ficha_estoque_v1(
        session=recursos.session,
        contexto=contexto,
        pedido=comando.pedido,
        recursos=recursos,
    )
    efetivo = replace(comando, snapshot_estoque=snapshot)
    return executar_checkout_em_transacao(
        comando=efetivo,
        contexto=contexto,
        recursos=recursos,
    )


def executar_checkout_com_ficha_estoque_v1(
    *,
    comando: ComandoCheckoutV1,
    contexto: ContextoExecucao,
    session_factory,
) -> ResultadoCheckoutV1:
    """Executa captura da ficha, bootstrap controlado e checkout em uma UoW."""

    with UnitOfWorkV1(session_factory) as uow:
        resultado = executar_checkout_com_ficha_estoque_em_transacao(
            comando=comando,
            contexto=contexto,
            recursos=uow.recursos,
        )
        uow.commit()
        return resultado
