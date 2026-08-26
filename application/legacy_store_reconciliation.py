"""Reconciliação operacional explícita entre unidade V1 e loja legada."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import Engine, insert, inspect, text
from sqlalchemy.engine import Connection

from core.seguranca.autenticacao import IdentidadeUsuario
from core.seguranca.erros import (
    ErroSeguranca,
    PermissaoInsuficiente,
    TenantNaoAutorizado,
    UnidadeNaoAutorizada,
    UsuarioInativo,
)
from core.seguranca.permissoes import Papel, Permissao
from infra.seguranca.modelos_orm import EventoAuditoriaORM
from migrations.runner import DEFAULT_MIGRATIONS, applied_versions

_BASELINE = "0020b_legacy_store_baseline_v1"
_MAPPING = "0021_unit_legacy_store_mapping_v1"
_CATALOG = "0027_legacy_catalog_unit_scope_v1"
_EXPIRATION = "0028_legacy_expiration_alert_integrity_v1"
_REQUIRED_TABLES = frozenset(
    {"lojas", "fm_unidade_loja_legacy_v1", "fm_schema_migrations", "fm_auditoria_v1"}
)


class ErroReconciliacaoLojaLegada(RuntimeError):
    """O estado não permite reconciliar ownership com segurança."""


def _normalizar_identificador(valor: str, *, campo: str, limite: int = 64) -> str:
    normalizado = valor.strip() if isinstance(valor, str) else ""
    if not normalizado:
        raise ErroReconciliacaoLojaLegada(f"{campo} explícito é obrigatório")
    if any(caractere.isspace() for caractere in normalizado):
        raise ErroReconciliacaoLojaLegada(f"{campo} não pode conter whitespace")
    if len(normalizado) > limite:
        raise ErroReconciliacaoLojaLegada(f"{campo} excede o limite de {limite}")
    return normalizado


def _normalizar_nome(valor: str, *, campo: str = "loja_nome") -> str:
    normalizado = " ".join(valor.split()) if isinstance(valor, str) else ""
    if not normalizado:
        raise ErroReconciliacaoLojaLegada(f"{campo} não pode ser vazio")
    if len(normalizado) > 255:
        raise ErroReconciliacaoLojaLegada(f"{campo} excede o limite de 255")
    return normalizado


@dataclass(frozen=True)
class SolicitacaoReconciliacaoLoja:
    tenant_id: str
    unidade_id: str
    loja_id: int
    loja_nome: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "tenant_id",
            _normalizar_identificador(self.tenant_id, campo="tenant_id"),
        )
        object.__setattr__(
            self,
            "unidade_id",
            _normalizar_identificador(self.unidade_id, campo="unidade_id"),
        )
        if self.loja_id <= 0:
            raise ErroReconciliacaoLojaLegada("loja_id explícita deve ser positiva")
        if self.loja_nome is not None:
            object.__setattr__(self, "loja_nome", _normalizar_nome(self.loja_nome))


@dataclass(frozen=True)
class ResultadoReconciliacaoLoja:
    estado: str
    loja_criada: bool
    mapping_criado: bool
    correlation_id: str


def _exigir_estrutura(connection: Connection) -> None:
    tabelas = set(inspect(connection).get_table_names())
    ausentes = _REQUIRED_TABLES - tabelas
    if ausentes:
        raise ErroReconciliacaoLojaLegada(
            "estrutura de reconciliação ausente: " + ", ".join(sorted(ausentes))
        )


def _exigir_estado_migrations(connection: Connection) -> None:
    aplicadas = applied_versions(connection)
    indice_catalogo = next(
        index for index, item in enumerate(DEFAULT_MIGRATIONS) if item.version == _CATALOG
    )
    anteriores = tuple(
        migration.version for migration in DEFAULT_MIGRATIONS[:indice_catalogo]
    )
    if set(anteriores) - aplicadas:
        raise ErroReconciliacaoLojaLegada(
            "estado de migrations incompatível; pendências anteriores à 0027"
        )
    if _BASELINE not in aplicadas or _MAPPING not in aplicadas:
        raise ErroReconciliacaoLojaLegada(
            "migrations estruturais 0020b e 0021 são obrigatórias"
        )
    if {_CATALOG, _EXPIRATION} & aplicadas:
        raise ErroReconciliacaoLojaLegada(
            "reconciliação deve ocorrer antes de 0027/0028"
        )


def _papel_efetivo(identidade: IdentidadeUsuario) -> Papel | None:
    if Papel.ADMINISTRADOR in identidade.papeis:
        return Papel.ADMINISTRADOR
    return next(iter(sorted(identidade.papeis, key=lambda papel: papel.value)), None)


def _auditar(
    connection: Connection,
    *,
    identidade: IdentidadeUsuario,
    solicitacao: SolicitacaoReconciliacaoLoja,
    correlation_id: str,
    resultado: str,
    motivo: str,
) -> None:
    escopo_permitido = resultado == "permitido"
    papel = _papel_efetivo(identidade)
    stmt: Any = insert(EventoAuditoriaORM).values(
        {
            "audit_id": str(uuid4()),
            "tenant_id": (
                solicitacao.tenant_id if escopo_permitido else identidade.tenant_id
            ),
            "unidade_id": (
                solicitacao.unidade_id if escopo_permitido else identidade.unidade_id
            ),
            "usuario_id": identidade.usuario_id,
            "papel_efetivo": papel.value if papel else None,
            "acao": "loja_legada.reconciliar",
            "recurso_tipo": "loja_legada",
            "recurso_id": str(solicitacao.loja_id),
            "resultado": resultado,
            "motivo": motivo,
            "correlation_id": correlation_id,
            "timestamp": datetime.now(timezone.utc),
            "origem": "cli-reconcile-legacy-store-v1",
            "politica": Permissao.LOJA_LEGADA_RECONCILIAR.value,
            "versao": 1,
            "causation_id": None,
            "antes_resumido": {},
            "depois_resumido": {},
            "metadata_segura": {},
        }
    )
    connection.execute(stmt)


def _autorizar(
    identidade: IdentidadeUsuario,
    solicitacao: SolicitacaoReconciliacaoLoja,
) -> IdentidadeUsuario:
    if not identidade.ativo:
        raise UsuarioInativo("usuario indisponivel")
    if identidade.tenant_id != solicitacao.tenant_id:
        raise TenantNaoAutorizado("recurso indisponivel")
    if solicitacao.unidade_id not in identidade.unidades_permitidas:
        raise UnidadeNaoAutorizada("recurso indisponivel")
    if (
        Papel.ADMINISTRADOR not in identidade.papeis
        or not identidade.acesso_admin_sensivel
        or Permissao.LOJA_LEGADA_RECONCILIAR not in identidade.permissoes
    ):
        raise PermissaoInsuficiente("permissao insuficiente")
    return identidade.no_escopo_ativo(
        tenant_id=solicitacao.tenant_id,
        unidade_id=solicitacao.unidade_id,
    )


def _reconciliar_autorizada(
    connection: Connection,
    solicitacao: SolicitacaoReconciliacaoLoja,
    identidade: IdentidadeUsuario,
) -> ResultadoReconciliacaoLoja:
    _exigir_estrutura(connection)
    _exigir_estado_migrations(connection)

    mappings_escopo = connection.execute(
        text(
            "SELECT m.loja_id, m.ativo, l.nome_fantasia "
            "FROM fm_unidade_loja_legacy_v1 AS m "
            "LEFT JOIN lojas AS l ON l.id = m.loja_id "
            "WHERE m.tenant_id = :tenant AND m.unidade_id = :unidade"
        ),
        {"tenant": solicitacao.tenant_id, "unidade": solicitacao.unidade_id},
    ).all()
    if len(mappings_escopo) > 1:
        raise ErroReconciliacaoLojaLegada("mapping ambíguo para tenant/unidade")
    if mappings_escopo:
        existente = mappings_escopo[0]
        if int(existente.loja_id) != solicitacao.loja_id or not bool(existente.ativo):
            raise ErroReconciliacaoLojaLegada(
                "tenant/unidade já apontam para outra loja ou mapping inativo"
            )
        if existente.nome_fantasia is None:
            raise ErroReconciliacaoLojaLegada("mapping existente aponta para loja ausente")
        nome_existente = _normalizar_nome(existente.nome_fantasia)
        if solicitacao.loja_nome is not None and solicitacao.loja_nome != nome_existente:
            raise ErroReconciliacaoLojaLegada("nome da loja diverge do estado canônico")
        correlation_id = str(uuid4())
        _auditar(
            connection,
            identidade=identidade,
            solicitacao=solicitacao,
            correlation_id=correlation_id,
            resultado="permitido",
            motivo="mapping_idempotente",
        )
        return ResultadoReconciliacaoLoja(
            "mapping_idempotente", False, False, correlation_id
        )

    outro_escopo = connection.execute(
        text(
            "SELECT tenant_id, unidade_id FROM fm_unidade_loja_legacy_v1 "
            "WHERE loja_id = :loja"
        ),
        {"loja": solicitacao.loja_id},
    ).first()
    if outro_escopo is not None:
        raise ErroReconciliacaoLojaLegada("loja já vinculada a outro escopo")

    lojas = connection.execute(
        text("SELECT id, nome_fantasia FROM lojas ORDER BY id")
    ).all()
    lojas_por_id = {int(item.id): _normalizar_nome(item.nome_fantasia) for item in lojas}
    loja_criada = False
    if not lojas:
        if solicitacao.loja_nome is None:
            raise ErroReconciliacaoLojaLegada(
                "zero lojas: loja_nome explícito é obrigatório para criar a loja"
            )
        connection.execute(
            text("INSERT INTO lojas (id, nome_fantasia) VALUES (:id, :nome)"),
            {"id": solicitacao.loja_id, "nome": solicitacao.loja_nome},
        )
        loja_criada = True
    elif solicitacao.loja_id not in lojas_por_id:
        cardinalidade = "uma loja" if len(lojas) == 1 else "múltiplas lojas"
        raise ErroReconciliacaoLojaLegada(
            f"{cardinalidade}: loja_id selecionada não existe"
        )
    elif (
        solicitacao.loja_nome is not None
        and solicitacao.loja_nome != lojas_por_id[solicitacao.loja_id]
    ):
        raise ErroReconciliacaoLojaLegada("nome da loja diverge do estado canônico")

    connection.execute(
        text(
            "INSERT INTO fm_unidade_loja_legacy_v1 "
            "(tenant_id, unidade_id, loja_id, ativo) "
            "VALUES (:tenant, :unidade, :loja, TRUE)"
        ),
        {
            "tenant": solicitacao.tenant_id,
            "unidade": solicitacao.unidade_id,
            "loja": solicitacao.loja_id,
        },
    )
    correlation_id = str(uuid4())
    estado = "loja_e_mapping_criados" if loja_criada else "mapping_criado"
    _auditar(
        connection,
        identidade=identidade,
        solicitacao=solicitacao,
        correlation_id=correlation_id,
        resultado="permitido",
        motivo=estado,
    )
    return ResultadoReconciliacaoLoja(estado, loja_criada, True, correlation_id)


def reconciliar_loja_legada(
    engine: Engine,
    solicitacao: SolicitacaoReconciliacaoLoja,
    *,
    identidade: IdentidadeUsuario,
) -> ResultadoReconciliacaoLoja:
    """Autoriza e reconcilia loja/mapping sob transações explícitas."""

    try:
        identidade_ativa = _autorizar(identidade, solicitacao)
    except ErroSeguranca as exc:
        with engine.begin() as connection:
            _exigir_estrutura(connection)
            _auditar(
                connection,
                identidade=identidade,
                solicitacao=solicitacao,
                correlation_id=str(uuid4()),
                resultado="negado",
                motivo=exc.codigo,
            )
        raise

    with engine.begin() as connection:
        return _reconciliar_autorizada(connection, solicitacao, identidade_ativa)
