"""Máquinas de estado V1 sem persistência ou efeitos externos."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from json import dumps
from typing import Any, Mapping
from uuid import uuid4

from core.dominio.decisoes import DecisaoCozinha
from core.seguranca import AutorizarAcao, ContextoExecucao, Permissao
from core.seguranca.auditoria import EventoAuditoria, sanitizar_metadata


@dataclass(frozen=True)
class DefinicaoMaquina:
    transicoes: Mapping[str, frozenset[str]]
    terminais: frozenset[str]
    permissao: Permissao


def _map(pares: list[tuple[str, str]]) -> dict[str, frozenset[str]]:
    origens: dict[str, set[str]] = {}
    for origem, destino in pares:
        origens.setdefault(origem, set()).add(destino)
    return {origem: frozenset(destinos) for origem, destinos in origens.items()}


_PEDIDO = [
    ("rascunho", "aguardando_confirmacao"),
    ("aguardando_confirmacao", "rascunho"),
    ("aguardando_confirmacao", "confirmado"),
    ("confirmado", "enviado_producao"),
    ("enviado_producao", "em_preparo"),
    ("em_preparo", "pronto"),
    ("pronto", "em_expedicao"),
    ("pronto", "servido"),
    ("pronto", "entregue"),
    ("em_expedicao", "saiu_entrega"),
    ("em_expedicao", "entregue"),
    ("saiu_entrega", "entregue"),
    ("servido", "concluido"),
    ("entregue", "concluido"),
    ("pronto", "concluido"),
    ("em_expedicao", "concluido"),
]
for _estado in (
    "rascunho",
    "aguardando_confirmacao",
    "confirmado",
    "enviado_producao",
    "em_preparo",
    "pronto",
    "em_expedicao",
    "saiu_entrega",
):
    _PEDIDO.append((_estado, "cancelado"))

MAQUINAS: dict[str, DefinicaoMaquina] = {
    "pedido": DefinicaoMaquina(
        _map(_PEDIDO), frozenset({"concluido", "cancelado"}), Permissao.PEDIDO_ALTERAR
    ),
    "pagamento": DefinicaoMaquina(
        _map(
            [
                ("nao_iniciado", "pendente"),
                ("nao_iniciado", "aguardando_entrega"),
                ("nao_iniciado", "aguardando_fechamento"),
                *(
                    (s, "parcialmente_pago")
                    for s in ("pendente", "aguardando_entrega", "aguardando_fechamento")
                ),
                *(
                    (s, "pago")
                    for s in (
                        "pendente",
                        "aguardando_entrega",
                        "aguardando_fechamento",
                        "parcialmente_pago",
                    )
                ),
                ("pendente", "falhou"),
                ("falhou", "pendente"),
                *(
                    (s, "cancelado")
                    for s in (
                        "nao_iniciado",
                        "pendente",
                        "aguardando_entrega",
                        "aguardando_fechamento",
                        "falhou",
                    )
                ),
                ("pago", "estornado_parcial"),
                ("estornado_parcial", "estornado"),
                ("pago", "estornado"),
                ("estornado_parcial", "pago"),
            ]
        ),
        frozenset({"cancelado", "estornado"}),
        Permissao.PAGAMENTO_REGISTRAR,
    ),
    "comanda": DefinicaoMaquina(
        _map(
            [
                ("aberta", "em_consumo"),
                ("aberta", "conta_solicitada"),
                ("em_consumo", "conta_solicitada"),
                ("conta_solicitada", "em_consumo"),
                ("conta_solicitada", "fechamento_em_andamento"),
                ("fechamento_em_andamento", "parcialmente_paga"),
                ("fechamento_em_andamento", "fechada"),
                ("parcialmente_paga", "fechada"),
                ("aberta", "cancelada"),
                ("em_consumo", "cancelada"),
                ("conta_solicitada", "cancelada"),
            ]
        ),
        frozenset({"fechada", "cancelada"}),
        Permissao.COMANDA_ALTERAR,
    ),
    "producao": DefinicaoMaquina(
        _map(
            [
                ("aguardando", "aceita"),
                ("aguardando", "em_preparo"),
                ("aceita", "em_preparo"),
                ("em_preparo", "pausada"),
                ("pausada", "em_preparo"),
                ("aceita", "pronta"),
                ("em_preparo", "pronta"),
                ("pausada", "pronta"),
                ("pronta", "retirada"),
                *(
                    (s, "cancelada")
                    for s in ("aguardando", "aceita", "em_preparo", "pausada")
                ),
            ]
        ),
        frozenset({"retirada", "cancelada"}),
        Permissao.PRODUCAO_ATUALIZAR,
    ),
    "entrega": DefinicaoMaquina(
        _map(
            [
                ("aguardando_producao", "aguardando_expedicao"),
                ("aguardando_expedicao", "aguardando_entregador"),
                *(
                    (s, "atribuida")
                    for s in (
                        "aguardando_producao",
                        "aguardando_expedicao",
                        "aguardando_entregador",
                    )
                ),
                ("atribuida", "coletada"),
                ("coletada", "em_rota"),
                ("em_rota", "entregue"),
                ("coletada", "entregue"),
                ("em_rota", "tentativa_falhou"),
                ("tentativa_falhou", "atribuida"),
                *(
                    (s, "cancelada")
                    for s in (
                        "aguardando_producao",
                        "aguardando_expedicao",
                        "aguardando_entregador",
                        "atribuida",
                        "tentativa_falhou",
                    )
                ),
            ]
        ),
        frozenset({"entregue", "cancelada"}),
        Permissao.EXPEDICAO_OPERAR,
    ),
}


class ErroTransicao(Exception):
    def __init__(self, codigo: str, mensagem: str = "Transição recusada") -> None:
        super().__init__(mensagem)
        self.codigo = codigo


@dataclass(frozen=True)
class SnapshotEstado:
    aggregate_type: str
    aggregate_id: str
    tenant_id: str
    unidade_id: str
    estado: str
    version: int


@dataclass(frozen=True)
class ComandoTransicao:
    destino: str
    versao_esperada: int
    idempotency_key: str
    timestamp: datetime
    contexto: ContextoExecucao
    precondicoes: Mapping[str, bool] = field(default_factory=dict)
    motivo: str | None = None
    decisao_cozinha: DecisaoCozinha | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EventoTransicao:
    event_id: str
    aggregate_id: str
    aggregate_type: str
    aggregate_version: int
    event_type: str
    tenant_id: str
    unidade_id: str
    timestamp: datetime
    actor: str
    correlation_id: str
    causation_id: str | None
    idempotency_key: str
    payload: tuple[tuple[str, Any], ...] = ()


@dataclass(frozen=True)
class ResultadoTransicao:
    snapshot: SnapshotEstado
    evento: EventoTransicao
    auditoria: EventoAuditoria
    idempotente: bool = False


class RegistroIdempotenciaEmMemoria:
    def __init__(self) -> None:
        self._resultados: dict[
            tuple[str, str, str], tuple[str, ResultadoTransicao]
        ] = {}

    def consultar(
        self, snapshot: SnapshotEstado, chave: str, fingerprint: str
    ) -> ResultadoTransicao | None:
        encontrado = self._resultados.get(
            (snapshot.aggregate_type, snapshot.aggregate_id, chave)
        )
        if encontrado is None:
            return None
        anterior, resultado = encontrado
        if anterior != fingerprint:
            raise ErroTransicao("conflito_idempotencia")
        return ResultadoTransicao(
            resultado.snapshot, resultado.evento, resultado.auditoria, True
        )

    def registrar(
        self,
        snapshot: SnapshotEstado,
        chave: str,
        fingerprint: str,
        resultado: ResultadoTransicao,
    ) -> None:
        self._resultados[(snapshot.aggregate_type, snapshot.aggregate_id, chave)] = (
            fingerprint,
            resultado,
        )


def _exigir_precondicoes(snapshot: SnapshotEstado, comando: ComandoTransicao) -> None:
    exigidas: dict[tuple[str, str, str], tuple[str, ...]] = {
        ("pedido", "rascunho", "aguardando_confirmacao"): (
            "itens_validos",
            "precos_calculados",
        ),
        ("pedido", "aguardando_confirmacao", "confirmado"): ("dados_confirmados",),
        ("pedido", "confirmado", "enviado_producao"): ("itens_roteados",),
        ("pedido", "enviado_producao", "em_preparo"): ("producao_iniciada",),
        ("pedido", "em_preparo", "pronto"): ("itens_resolvidos",),
        ("comanda", "fechamento_em_andamento", "fechada"): (
            "saldo_resolvido_ou_posterior",
            "pedidos_resolvidos",
        ),
        ("comanda", "parcialmente_paga", "fechada"): (
            "saldo_resolvido_ou_posterior",
            "pedidos_resolvidos",
        ),
    }
    for nome in exigidas.get(
        (snapshot.aggregate_type, snapshot.estado, comando.destino), ()
    ):
        if not comando.precondicoes.get(nome):
            raise ErroTransicao("precondicao_nao_atendida", nome)
    if (
        snapshot.aggregate_type == "pedido"
        and snapshot.estado == "confirmado"
        and comando.destino == "enviado_producao"
    ):
        if comando.decisao_cozinha is None or not comando.decisao_cozinha.permitido:
            raise ErroTransicao("cozinha_nao_autorizada")
    if comando.destino == "cancelado" and not (comando.motivo or "").strip():
        raise ErroTransicao("motivo_obrigatorio")


def transicionar(
    snapshot: SnapshotEstado,
    comando: ComandoTransicao,
    *,
    registro: RegistroIdempotenciaEmMemoria | None = None,
    autorizador: AutorizarAcao | None = None,
) -> ResultadoTransicao:
    if not comando.idempotency_key.strip():
        raise ErroTransicao("idempotency_key_obrigatoria")
    if comando.timestamp.tzinfo is None:
        raise ErroTransicao("timestamp_invalido")
    fingerprint = sha256(
        dumps(
            {
                "destino": comando.destino,
                "versao": comando.versao_esperada,
                "motivo": comando.motivo,
                "pre": sorted(comando.precondicoes.items()),
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    registro = registro or RegistroIdempotenciaEmMemoria()
    repetido = registro.consultar(snapshot, comando.idempotency_key, fingerprint)
    if repetido:
        return repetido
    maquina = MAQUINAS[snapshot.aggregate_type]
    if snapshot.estado in maquina.terminais:
        raise ErroTransicao("estado_terminal")
    if comando.versao_esperada != snapshot.version:
        raise ErroTransicao(f"{snapshot.aggregate_type}_concorrente")
    if (
        comando.contexto.tenant_id != snapshot.tenant_id
        or comando.contexto.unidade_id != snapshot.unidade_id
    ):
        raise ErroTransicao("recurso_indisponivel")
    if comando.destino not in maquina.transicoes.get(snapshot.estado, frozenset()):
        raise ErroTransicao(f"transicao_{snapshot.aggregate_type}_invalida")
    permissao = (
        Permissao.PEDIDO_CANCELAR
        if snapshot.aggregate_type == "pedido" and comando.destino == "cancelado"
        else maquina.permissao
    )
    decisao = (autorizador or AutorizarAcao()).executar(
        contexto=comando.contexto,
        permissao=permissao,
        recurso=snapshot.aggregate_type,
        tenant_recurso=snapshot.tenant_id,
        unidade_recurso=snapshot.unidade_id,
    )
    if not decisao.autorizado:
        raise ErroTransicao(decisao.codigo)
    _exigir_precondicoes(snapshot, comando)
    instante = comando.timestamp.astimezone(timezone.utc)
    novo = SnapshotEstado(
        snapshot.aggregate_type,
        snapshot.aggregate_id,
        snapshot.tenant_id,
        snapshot.unidade_id,
        comando.destino,
        snapshot.version + 1,
    )
    tipo = _tipo_evento(snapshot.aggregate_type, snapshot.estado, comando.destino)
    evento = EventoTransicao(
        str(uuid4()),
        snapshot.aggregate_id,
        snapshot.aggregate_type,
        novo.version,
        tipo,
        snapshot.tenant_id,
        snapshot.unidade_id,
        instante,
        comando.contexto.usuario_id,
        comando.contexto.correlation_id,
        comando.contexto.causation_id,
        comando.idempotency_key,
        sanitizar_metadata(dict(comando.metadata)),
    )
    papel = next(iter(sorted(comando.contexto.papeis, key=str)), None)
    politica = (
        comando.decisao_cozinha.politica_aplicada
        if comando.decisao_cozinha
        else decisao.politica_aplicada
    )
    versao_politica = (
        int(comando.decisao_cozinha.versao_politica)
        if comando.decisao_cozinha and comando.decisao_cozinha.versao_politica.isdigit()
        else 1
    )
    auditoria = EventoAuditoria(
        str(uuid4()),
        snapshot.tenant_id,
        snapshot.unidade_id,
        comando.contexto.usuario_id,
        papel,
        tipo,
        snapshot.aggregate_type,
        snapshot.aggregate_id,
        "permitido",
        comando.motivo or "transicao_normativa",
        comando.contexto.correlation_id,
        instante,
        comando.contexto.origem,
        politica,
        versao_politica,
        comando.contexto.causation_id,
        (("estado", snapshot.estado),),
        (("estado", novo.estado),),
        sanitizar_metadata(dict(comando.metadata)),
    )
    resultado = ResultadoTransicao(novo, evento, auditoria)
    registro.registrar(snapshot, comando.idempotency_key, fingerprint, resultado)
    return resultado


def _tipo_evento(agregado: str, origem: str, destino: str) -> str:
    especiais = {
        ("pedido", "aguardando_confirmacao", "rascunho"): "pedido.reaberto_edicao",
        ("pagamento", "nao_iniciado", "pendente"): "pagamento.iniciado",
        ("pagamento", "pendente", "pago"): "pagamento.confirmado",
        ("producao", "aceita", "em_preparo"): "producao.iniciada",
        ("entrega", "em_rota", "entregue"): "entrega.concluida",
    }
    return especiais.get((agregado, origem, destino), f"{agregado}.{destino}")
