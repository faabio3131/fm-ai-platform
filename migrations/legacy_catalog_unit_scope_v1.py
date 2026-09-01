"""Migration 0027 — escopo de loja do catálogo operacional legado.

``insumos`` contém saldo e custo. Cada linha precisa pertencer a uma única loja
legada, cuja relação com tenant/unidade continua pertencendo ao mapping canônico
``fm_unidade_loja_legacy_v1``. O backfill só aceita evidência determinística e
aborta a transação diante de qualquer ambiguidade.

``fichas_tecnicas`` não recebe uma nova coluna de autoridade: seu escopo deriva
do produto e do insumo, que precisam apontar para a mesma loja.
"""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

_INSUMOS = "insumos"
_PRODUTOS = "produtos"
_FICHAS = "fichas_tecnicas"
_LOJAS = "lojas"
_MAPPING = "fm_unidade_loja_legacy_v1"
_COLUMN = "loja_id"
_INDEX = "ix_insumos_loja_id_v1"
_TRIGGER_INSERT = "trg_insumos_loja_id_nn_insert_v1"
_TRIGGER_UPDATE = "trg_insumos_loja_id_nn_update_v1"


def _exigir_schema_base(connection: Connection) -> None:
    inspector = inspect(connection)
    tabelas = set(inspector.get_table_names())
    ausentes = {
        _INSUMOS,
        _PRODUTOS,
        _FICHAS,
        _LOJAS,
        _MAPPING,
    } - tabelas
    if ausentes:
        raise RuntimeError(
            "schema base ausente antes da migration 0027: "
            + ", ".join(sorted(ausentes))
        )

    obrigatorias = {
        _INSUMOS: {"id"},
        _PRODUTOS: {"id", _COLUMN},
        _FICHAS: {"id", "produto_id", "insumo_id"},
        _LOJAS: {"id"},
        _MAPPING: {"tenant_id", "unidade_id", _COLUMN},
    }
    for tabela, colunas_esperadas in obrigatorias.items():
        colunas = {
            coluna["name"]
            for coluna in inspect(connection).get_columns(tabela)
        }
        faltantes = colunas_esperadas - colunas
        if faltantes:
            raise RuntimeError(
                f"tabela {tabela} divergente antes da migration 0027: "
                + ", ".join(sorted(faltantes))
            )


def _adicionar_coluna(connection: Connection) -> None:
    colunas = {
        coluna["name"]
        for coluna in inspect(connection).get_columns(_INSUMOS)
    }
    if _COLUMN not in colunas:
        connection.execute(
            text(
                "ALTER TABLE insumos "
                "ADD COLUMN loja_id INTEGER NULL REFERENCES lojas(id)"
            )
        )


def _exigir_fk_loja(connection: Connection) -> None:
    foreign_keys = inspect(connection).get_foreign_keys(_INSUMOS)
    possui_fk = any(
        tuple(foreign_key.get("constrained_columns") or ()) == (_COLUMN,)
        and foreign_key.get("referred_table") == _LOJAS
        and tuple(foreign_key.get("referred_columns") or ()) == ("id",)
        for foreign_key in foreign_keys
    )
    if possui_fk:
        return

    if connection.dialect.name == "postgresql":
        connection.execute(
            text(
                "ALTER TABLE insumos "
                "ADD CONSTRAINT fk_insumos_loja_v1 "
                "FOREIGN KEY (loja_id) REFERENCES lojas(id)"
            )
        )
        return

    raise RuntimeError(
        "insumos.loja_id existente sem FK para lojas; "
        "reconciliação estrutural explícita necessária"
    )


def _ids_lojas(connection: Connection) -> frozenset[int]:
    return frozenset(
        int(loja_id)
        for loja_id in connection.execute(
            text("SELECT id FROM lojas ORDER BY id")
        ).scalars()
    )


def _normalizar_loja(
    valor: object,
    *,
    contexto: str,
) -> int:
    try:
        return int(str(valor).strip())
    except (TypeError, ValueError) as exc:
        raise RuntimeError(
            f"loja_id inválido em {contexto}"
        ) from exc


def _candidatas_por_ficha(
    connection: Connection,
    *,
    insumo_id: int,
) -> tuple[int, ...]:
    referencias = connection.execute(
        text(
            """
            SELECT p.id AS produto_id, p.loja_id AS loja_id
            FROM fichas_tecnicas AS ft
            LEFT JOIN produtos AS p ON p.id = ft.produto_id
            WHERE ft.insumo_id = :insumo_id
            ORDER BY p.id
            """
        ),
        {"insumo_id": insumo_id},
    ).all()

    candidatas: set[int] = set()
    for referencia in referencias:
        if referencia.produto_id is None:
            raise RuntimeError(
                "ficha técnica referencia produto inexistente"
            )
        if referencia.loja_id is None:
            raise RuntimeError(
                "produto de ficha técnica sem loja determinística"
            )
        candidatas.add(
            _normalizar_loja(
                referencia.loja_id,
                contexto=f"produto {referencia.produto_id}",
            )
        )

    return tuple(sorted(candidatas))


def _validar_referencias_de_insumo(connection: Connection) -> None:
    orfas = connection.execute(
        text(
            """
            SELECT ft.id
            FROM fichas_tecnicas AS ft
            LEFT JOIN insumos AS i ON i.id = ft.insumo_id
            WHERE i.id IS NULL
            ORDER BY ft.id
            """
        )
    ).scalars().all()
    if orfas:
        raise RuntimeError(
            "ficha técnica referencia insumo inexistente"
        )


def _backfill_deterministico(connection: Connection) -> None:
    lojas = _ids_lojas(connection)
    _validar_referencias_de_insumo(connection)

    insumos = connection.execute(
        text("SELECT id, loja_id FROM insumos ORDER BY id")
    ).all()

    for insumo in insumos:
        insumo_id = int(insumo.id)
        candidatas = _candidatas_por_ficha(
            connection,
            insumo_id=insumo_id,
        )

        desconhecidas = set(candidatas) - lojas
        if desconhecidas:
            raise RuntimeError(
                "produto de ficha técnica aponta para loja inexistente"
            )
        if len(candidatas) > 1:
            raise RuntimeError(
                "insumo vinculado a produtos de lojas diferentes"
            )

        existente = (
            None
            if insumo.loja_id is None
            else _normalizar_loja(
                insumo.loja_id,
                contexto=f"insumo {insumo_id}",
            )
        )

        if existente is not None:
            if existente not in lojas:
                raise RuntimeError(
                    "insumo aponta para loja inexistente"
                )
            if candidatas and candidatas[0] != existente:
                raise RuntimeError(
                    "produto e insumo de ficha técnica pertencem a lojas diferentes"
                )
            continue

        if len(candidatas) == 1:
            loja_id = candidatas[0]
        elif len(lojas) == 1:
            loja_id = next(iter(lojas))
        elif not lojas:
            raise RuntimeError(
                "insumo sem loja determinística: nenhuma loja histórica cadastrada; "
                "execute a reconciliação explícita antes da migration 0027"
            )
        else:
            raise RuntimeError(
                "insumo sem loja determinística em ambiente multi-loja"
            )

        connection.execute(
            text(
                "UPDATE insumos SET loja_id = :loja_id "
                "WHERE id = :insumo_id AND loja_id IS NULL"
            ),
            {"loja_id": loja_id, "insumo_id": insumo_id},
        )


def _exigir_sem_nulos(connection: Connection) -> None:
    pendentes = connection.execute(
        text("SELECT id FROM insumos WHERE loja_id IS NULL ORDER BY id")
    ).scalars().all()
    if pendentes:
        raise RuntimeError(
            "insumo operacional permaneceu sem loja após backfill"
        )


def _criar_indice(connection: Connection) -> None:
    indices = {
        indice["name"]
        for indice in inspect(connection).get_indexes(_INSUMOS)
    }
    if _INDEX not in indices:
        connection.execute(
            text("CREATE INDEX ix_insumos_loja_id_v1 ON insumos (loja_id)")
        )


def _endurecer_nullability(connection: Connection) -> None:
    if connection.dialect.name == "postgresql":
        coluna = next(
            coluna
            for coluna in inspect(connection).get_columns(_INSUMOS)
            if coluna["name"] == _COLUMN
        )
        if coluna["nullable"]:
            connection.execute(
                text(
                    "ALTER TABLE insumos "
                    "ALTER COLUMN loja_id SET NOT NULL"
                )
            )
        return

    if connection.dialect.name != "sqlite":
        raise RuntimeError(
            "dialeto não homologado para hardening de insumos.loja_id"
        )

    connection.execute(
        text(
            f"""
            CREATE TRIGGER IF NOT EXISTS {_TRIGGER_INSERT}
            BEFORE INSERT ON insumos
            FOR EACH ROW
            WHEN NEW.loja_id IS NULL
            BEGIN
                SELECT RAISE(ABORT, 'insumos.loja_id obrigatório');
            END
            """
        )
    )
    connection.execute(
        text(
            f"""
            CREATE TRIGGER IF NOT EXISTS {_TRIGGER_UPDATE}
            BEFORE UPDATE OF loja_id ON insumos
            FOR EACH ROW
            WHEN NEW.loja_id IS NULL
            BEGIN
                SELECT RAISE(ABORT, 'insumos.loja_id obrigatório');
            END
            """
        )
    )


def _validar_estado_final(connection: Connection) -> None:
    _exigir_fk_loja(connection)
    _exigir_sem_nulos(connection)
    indices = {
        indice["name"]
        for indice in inspect(connection).get_indexes(_INSUMOS)
    }
    if _INDEX not in indices:
        raise RuntimeError("índice de escopo de insumos ausente")


def upgrade_legacy_catalog_unit_scope_v1(connection: Connection) -> None:
    """Materializa o escopo operacional sem inventar vínculo de loja."""

    _exigir_schema_base(connection)
    _adicionar_coluna(connection)
    _exigir_fk_loja(connection)
    _backfill_deterministico(connection)
    _exigir_sem_nulos(connection)
    _criar_indice(connection)
    _endurecer_nullability(connection)
    _validar_estado_final(connection)


def sqlite_hardening_objects() -> tuple[str, ...]:
    """Objetos determinísticos expostos somente para fitness tests."""

    return (_TRIGGER_INSERT, _TRIGGER_UPDATE)
