"""Bridge fiscal/financeiro dentro da autoridade canônica de pagamentos V1."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import StrEnum
from threading import RLock
from typing import Protocol, TypeVar
from uuid import uuid4

from core.dominio.ids import (
    CorrelationId,
    EventoId,
    IdempotencyKey,
    TenantId,
    UnidadeId,
)
from core.eventos.modelos import EnvelopeMensagem
from core.procurement.modelos import (
    PedidoCompra,
    RecebimentoCompra,
    StatusRecebimento,
)
from core.seguranca.auditoria import EventoAuditoria, sanitizar_metadata
from core.seguranca.autorizacao import AutorizarAcao
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Permissao
from kordena_fiscal.domain import ExecutionScope, FiscalEnvironment

from .erros import (
    ConflitoIdempotenciaPagamento,
    EfeitoFinanceiroFiscalBloqueado,
    OperacaoPagamentoNaoAutorizada,
    ValorPagamentoInvalido,
)

T = TypeVar("T")


def _utc(valor: datetime) -> datetime:
    if valor.tzinfo is None or valor.utcoffset() is None:
        raise ValorPagamentoInvalido("timestamp_deve_conter_timezone")
    return valor.astimezone(timezone.utc)


def _dinheiro(valor: Decimal | str | int, *, zero: bool = True) -> Decimal:
    numero = Decimal(str(valor))
    if not numero.is_finite() or numero < 0 or (not zero and numero == 0):
        raise ValorPagamentoInvalido("valor_financeiro_invalido")
    return numero.quantize(Decimal("0.01"))


def _hash(*valores: object) -> str:
    return hashlib.sha256(
        json.dumps(valores, default=str, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class StatusObrigacaoCompra(StrEnum):
    ABERTA = "aberta"
    AJUSTADA = "ajustada"
    CANCELADA = "cancelada"


class StatusReconciliacaoCompra(StrEnum):
    PARCIAL = "parcial"
    CONCILIADA = "conciliada"


class TipoAjusteObrigacaoCompra(StrEnum):
    DEVOLUCAO = "devolucao"
    CANCELAMENTO = "cancelamento"


class ResultadoCreditoTributario(StrEnum):
    ELEGIVEL = "elegivel"
    INELEGIVEL = "inelegivel"
    BLOQUEADO = "bloqueado"


@dataclass(frozen=True, slots=True)
class ObrigacaoCompraFiscal:
    obrigacao_id: str
    scope: ExecutionScope
    fornecedor_id: str
    pedido_id: str
    recebimento_id: str
    inbound_id: str
    chave_acesso: str
    valor_original: Decimal
    valor_ajustado: Decimal
    saldo: Decimal
    moeda: str
    status: StatusObrigacaoCompra
    reconciliacao: StatusReconciliacaoCompra
    idempotency_key: str
    criado_por: str
    criado_em: datetime
    correlation_id: str
    versao: int = 1

    def __post_init__(self) -> None:
        for campo in (
            "obrigacao_id",
            "fornecedor_id",
            "pedido_id",
            "recebimento_id",
            "inbound_id",
            "chave_acesso",
            "idempotency_key",
            "criado_por",
            "correlation_id",
        ):
            if not str(getattr(self, campo)).strip():
                raise ValorPagamentoInvalido(f"{campo}_obrigatorio")
        original = _dinheiro(self.valor_original, zero=False)
        ajustado = _dinheiro(self.valor_ajustado)
        saldo = _dinheiro(self.saldo)
        if original - ajustado != saldo or ajustado > original:
            raise ValorPagamentoInvalido("saldo_obrigacao_inconsistente")
        if self.status is StatusObrigacaoCompra.CANCELADA and saldo != 0:
            raise ValorPagamentoInvalido("obrigacao_cancelada_com_saldo")
        object.__setattr__(self, "valor_original", original)
        object.__setattr__(self, "valor_ajustado", ajustado)
        object.__setattr__(self, "saldo", saldo)
        object.__setattr__(self, "moeda", self.moeda.upper())
        object.__setattr__(self, "criado_em", _utc(self.criado_em))
        if self.versao < 1:
            raise ValorPagamentoInvalido("versao_obrigacao_invalida")

    @property
    def fingerprint(self) -> str:
        return _hash(
            self.scope.partition_key,
            self.fornecedor_id,
            self.pedido_id,
            self.recebimento_id,
            self.inbound_id,
            self.chave_acesso,
            self.valor_original,
            self.moeda,
            self.reconciliacao,
        )


@dataclass(frozen=True, slots=True)
class AjusteObrigacaoCompra:
    ajuste_id: str
    scope: ExecutionScope
    obrigacao_id: str
    tipo: TipoAjusteObrigacaoCompra
    valor: Decimal
    motivo: str
    origem_id: str
    idempotency_key: str
    criado_por: str
    criado_em: datetime
    correlation_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "valor", _dinheiro(self.valor, zero=False))
        object.__setattr__(self, "criado_em", _utc(self.criado_em))
        if not self.motivo.strip():
            raise ValorPagamentoInvalido("motivo_ajuste_obrigatorio")

    @property
    def fingerprint(self) -> str:
        return _hash(
            self.scope.partition_key,
            self.obrigacao_id,
            self.tipo,
            self.valor,
            self.origem_id,
            self.motivo,
        )


@dataclass(frozen=True, slots=True)
class RegraCreditoTributario:
    regra_id: str
    versao: int
    tributo: str
    cfops_elegiveis: frozenset[str]
    csts_elegiveis: frozenset[str]
    aliquota_credito: Decimal
    vigente_desde: date
    vigente_ate: date | None = None

    def __post_init__(self) -> None:
        aliquota = Decimal(str(self.aliquota_credito))
        if self.versao < 1 or aliquota < 0 or aliquota > 1:
            raise ValorPagamentoInvalido("regra_tributaria_invalida")
        if not self.regra_id.strip() or not self.tributo.strip():
            raise ValorPagamentoInvalido("identidade_regra_tributaria_invalida")
        object.__setattr__(self, "aliquota_credito", aliquota)
        object.__setattr__(self, "cfops_elegiveis", frozenset(self.cfops_elegiveis))
        object.__setattr__(self, "csts_elegiveis", frozenset(self.csts_elegiveis))


@dataclass(frozen=True, slots=True)
class DecisaoCreditoTributario:
    decisao_id: str
    scope: ExecutionScope
    obrigacao_id: str
    obrigacao_versao: int
    tributo: str
    resultado: ResultadoCreditoTributario
    base_calculo: Decimal
    valor_destacado: Decimal
    valor_credito: Decimal
    cfop: str
    cst: str
    regra_id: str | None
    regra_versao: int | None
    motivo: str
    idempotency_key: str
    decidido_por: str
    decidido_em: datetime
    correlation_id: str

    def __post_init__(self) -> None:
        for campo in ("base_calculo", "valor_destacado", "valor_credito"):
            object.__setattr__(self, campo, _dinheiro(getattr(self, campo)))
        if self.valor_credito > self.valor_destacado:
            raise ValorPagamentoInvalido("credito_supera_valor_destacado")
        if self.obrigacao_versao < 1:
            raise ValorPagamentoInvalido("versao_obrigacao_decisao_invalida")
        object.__setattr__(self, "decidido_em", _utc(self.decidido_em))

    @property
    def fingerprint(self) -> str:
        return _hash(
            self.scope.partition_key,
            self.obrigacao_id,
            self.obrigacao_versao,
            self.tributo,
            self.base_calculo,
            self.valor_destacado,
            self.cfop,
            self.cst,
            self.regra_id,
            self.regra_versao,
        )


@dataclass(frozen=True, slots=True)
class ResultadoBridgeFinanceiroFiscal:
    obrigacao: ObrigacaoCompraFiscal
    idempotente: bool
    eventos: tuple[EnvelopeMensagem, ...] = ()
    auditorias: tuple[EventoAuditoria, ...] = ()


@dataclass(frozen=True, slots=True)
class ResumoFinanceiroFiscal:
    scope: ExecutionScope
    obrigacoes: int
    valor_original: Decimal
    valor_ajustado: Decimal
    saldo_aberto: Decimal
    creditos_elegiveis: Decimal
    fontes: tuple[str, ...]


class RepositorioBridgeFinanceiroFiscal(Protocol):
    def atomicamente(self, operacao: Callable[[], T]) -> T: ...
    def salvar_obrigacao(
        self, obrigacao: ObrigacaoCompraFiscal
    ) -> tuple[ObrigacaoCompraFiscal, bool]: ...
    def obrigacao_por_recebimento(
        self, scope: ExecutionScope, recebimento_id: str
    ) -> ObrigacaoCompraFiscal | None: ...
    def obrigacoes_por_pedido(
        self, scope: ExecutionScope, pedido_id: str
    ) -> tuple[ObrigacaoCompraFiscal, ...]: ...
    def salvar_ajuste(
        self, ajuste: AjusteObrigacaoCompra
    ) -> tuple[AjusteObrigacaoCompra, ObrigacaoCompraFiscal, bool]: ...
    def ajuste_por_idempotencia(
        self, scope: ExecutionScope, idempotency_key: str
    ) -> AjusteObrigacaoCompra | None: ...
    def salvar_decisao(
        self, decisao: DecisaoCreditoTributario
    ) -> tuple[DecisaoCreditoTributario, bool]: ...
    def listar_obrigacoes(
        self, scope: ExecutionScope
    ) -> tuple[ObrigacaoCompraFiscal, ...]: ...
    def listar_decisoes(
        self, scope: ExecutionScope
    ) -> tuple[DecisaoCreditoTributario, ...]: ...


class RepositorioBridgeFinanceiroFiscalEmMemoria:
    def __init__(self) -> None:
        self._obrigacoes: dict[tuple[str, str], ObrigacaoCompraFiscal] = {}
        self._por_recebimento: dict[tuple[str, str], str] = {}
        self._ajustes: dict[tuple[str, str], AjusteObrigacaoCompra] = {}
        self._decisoes: dict[tuple[str, str], DecisaoCreditoTributario] = {}
        self._lock = RLock()

    @staticmethod
    def _scope(scope: ExecutionScope) -> str:
        return "|".join(scope.partition_key)

    def atomicamente(self, operacao: Callable[[], T]) -> T:
        with self._lock:
            snapshot = (
                dict(self._obrigacoes),
                dict(self._por_recebimento),
                dict(self._ajustes),
                dict(self._decisoes),
            )
            try:
                return operacao()
            except Exception:
                (
                    self._obrigacoes,
                    self._por_recebimento,
                    self._ajustes,
                    self._decisoes,
                ) = snapshot
                raise

    def salvar_obrigacao(
        self, obrigacao: ObrigacaoCompraFiscal
    ) -> tuple[ObrigacaoCompraFiscal, bool]:
        escopo = self._scope(obrigacao.scope)
        chave_recebimento = (escopo, obrigacao.recebimento_id)
        existente_id = self._por_recebimento.get(chave_recebimento)
        if existente_id:
            existente = self._obrigacoes[(escopo, existente_id)]
            if existente.fingerprint != obrigacao.fingerprint:
                raise ConflitoIdempotenciaPagamento("recebimento_financeiro_divergente")
            return existente, False
        self._obrigacoes[(escopo, obrigacao.obrigacao_id)] = obrigacao
        self._por_recebimento[chave_recebimento] = obrigacao.obrigacao_id
        return obrigacao, True

    def obrigacao_por_recebimento(
        self, scope: ExecutionScope, recebimento_id: str
    ) -> ObrigacaoCompraFiscal | None:
        escopo = self._scope(scope)
        obrigacao_id = self._por_recebimento.get((escopo, recebimento_id))
        return self._obrigacoes.get((escopo, obrigacao_id)) if obrigacao_id else None

    def obrigacoes_por_pedido(
        self, scope: ExecutionScope, pedido_id: str
    ) -> tuple[ObrigacaoCompraFiscal, ...]:
        escopo = self._scope(scope)
        return tuple(
            item
            for (particao, _), item in self._obrigacoes.items()
            if particao == escopo and item.pedido_id == pedido_id
        )

    def salvar_ajuste(
        self, ajuste: AjusteObrigacaoCompra
    ) -> tuple[AjusteObrigacaoCompra, ObrigacaoCompraFiscal, bool]:
        escopo = self._scope(ajuste.scope)
        chave = (escopo, ajuste.idempotency_key)
        existente = self._ajustes.get(chave)
        obrigacao = self._obrigacoes.get((escopo, ajuste.obrigacao_id))
        if obrigacao is None:
            raise EfeitoFinanceiroFiscalBloqueado("obrigacao_compra_inexistente")
        if existente:
            if existente.fingerprint != ajuste.fingerprint:
                raise ConflitoIdempotenciaPagamento("ajuste_financeiro_divergente")
            return existente, obrigacao, False
        if ajuste.valor > obrigacao.saldo:
            raise ValorPagamentoInvalido("ajuste_supera_saldo_obrigacao")
        ajustado = obrigacao.valor_ajustado + ajuste.valor
        saldo = obrigacao.valor_original - ajustado
        atualizada = replace(
            obrigacao,
            valor_ajustado=ajustado,
            saldo=saldo,
            status=(
                StatusObrigacaoCompra.CANCELADA
                if saldo == 0
                else StatusObrigacaoCompra.AJUSTADA
            ),
            versao=obrigacao.versao + 1,
        )
        self._ajustes[chave] = ajuste
        self._obrigacoes[(escopo, obrigacao.obrigacao_id)] = atualizada
        return ajuste, atualizada, True

    def ajuste_por_idempotencia(
        self, scope: ExecutionScope, idempotency_key: str
    ) -> AjusteObrigacaoCompra | None:
        return self._ajustes.get((self._scope(scope), idempotency_key))

    def salvar_decisao(
        self, decisao: DecisaoCreditoTributario
    ) -> tuple[DecisaoCreditoTributario, bool]:
        chave = (self._scope(decisao.scope), decisao.idempotency_key)
        existente = self._decisoes.get(chave)
        if existente:
            if existente.fingerprint != decisao.fingerprint:
                raise ConflitoIdempotenciaPagamento("decisao_tributaria_divergente")
            return existente, False
        self._decisoes[chave] = decisao
        return decisao, True

    def listar_obrigacoes(
        self, scope: ExecutionScope
    ) -> tuple[ObrigacaoCompraFiscal, ...]:
        escopo = self._scope(scope)
        return tuple(v for (particao, _), v in self._obrigacoes.items() if particao == escopo)

    def listar_decisoes(
        self, scope: ExecutionScope
    ) -> tuple[DecisaoCreditoTributario, ...]:
        escopo = self._scope(scope)
        return tuple(v for (particao, _), v in self._decisoes.items() if particao == escopo)


def _autorizar(contexto: ContextoExecucao, permissao: Permissao) -> None:
    if contexto.identidade_sistema:
        return
    decisao = AutorizarAcao().executar(
        contexto=contexto,
        permissao=permissao,
        recurso="financeiro_fiscal",
        tenant_recurso=contexto.tenant_id,
        unidade_recurso=contexto.unidade_id,
    )
    if not decisao.autorizado:
        raise OperacaoPagamentoNaoAutorizada(decisao.codigo)


def _validar_scope(contexto: ContextoExecucao, scope: ExecutionScope) -> None:
    unidades = contexto.unidades_permitidas or frozenset({contexto.unidade_id})
    if contexto.tenant_id != scope.tenant_id or scope.unit_id not in unidades:
        raise EfeitoFinanceiroFiscalBloqueado("recurso_indisponivel")


class ServicoBridgeFinanceiroFiscal:
    def __init__(self, repositorio: RepositorioBridgeFinanceiroFiscal) -> None:
        self._repositorio = repositorio

    def criar_obrigacao(
        self,
        *,
        contexto: ContextoExecucao,
        scope: ExecutionScope,
        pedido: PedidoCompra,
        recebimento: RecebimentoCompra,
        total_documental: Decimal,
        idempotency_key: str,
        obrigacao_id: str | None = None,
        moeda: str = "BRL",
    ) -> ResultadoBridgeFinanceiroFiscal:
        _autorizar(contexto, Permissao.FINANCEIRO_COMPRAS_REGISTRAR)
        _validar_scope(contexto, scope)
        if scope.environment is not FiscalEnvironment.PRODUCTION:
            raise EfeitoFinanceiroFiscalBloqueado("financeiro_exige_particao_production")
        if pedido.scope.partition_key != scope.partition_key or recebimento.scope.partition_key != scope.partition_key:
            raise EfeitoFinanceiroFiscalBloqueado("origem_financeira_fora_do_escopo")
        if recebimento.pedido_id != pedido.pedido_id or recebimento.status not in {
            StatusRecebimento.PARCIAL,
            StatusRecebimento.CONCLUIDO,
        }:
            raise EfeitoFinanceiroFiscalBloqueado("recebimento_nao_autoriza_obrigacao")
        if recebimento.divergencias:
            raise EfeitoFinanceiroFiscalBloqueado("recebimento_divergente")
        total = _dinheiro(total_documental, zero=False)

        def operacao() -> ResultadoBridgeFinanceiroFiscal:
            existente = self._repositorio.obrigacao_por_recebimento(
                scope, recebimento.recebimento_id
            )
            anteriores = tuple(
                item
                for item in self._repositorio.obrigacoes_por_pedido(
                    scope, pedido.pedido_id
                )
                if item.recebimento_id != recebimento.recebimento_id
            )
            subtotal = _dinheiro(
                sum(
                    (
                        item.quantidade * item.valor_unitario
                        for item in recebimento.itens
                        if item.condicao_aceita
                    ),
                    Decimal(0),
                ),
                zero=False,
            )
            valor = (
                total - sum((item.valor_original for item in anteriores), Decimal(0))
                if recebimento.status is StatusRecebimento.CONCLUIDO
                else subtotal
            )
            valor = _dinheiro(valor, zero=False)
            reconciliacao = (
                StatusReconciliacaoCompra.CONCILIADA
                if recebimento.status is StatusRecebimento.CONCLUIDO
                else StatusReconciliacaoCompra.PARCIAL
            )
            nova = ObrigacaoCompraFiscal(
                obrigacao_id or str(uuid4()),
                scope,
                pedido.fornecedor_id,
                pedido.pedido_id,
                recebimento.recebimento_id,
                recebimento.inbound_id,
                recebimento.chave_acesso,
                valor,
                Decimal(0),
                valor,
                moeda,
                StatusObrigacaoCompra.ABERTA,
                reconciliacao,
                idempotency_key,
                contexto.usuario_id,
                contexto.solicitado_em,
                scope.correlation_id,
            )
            if existente is not None and existente.fingerprint != nova.fingerprint:
                raise ConflitoIdempotenciaPagamento("recebimento_financeiro_divergente")
            salva, criada = self._repositorio.salvar_obrigacao(nova)
            if not criada:
                return ResultadoBridgeFinanceiroFiscal(salva, True)
            evento = EnvelopeMensagem(
                EventoId(str(uuid4())),
                "financeiro.obrigacao_compra.criada",
                salva.obrigacao_id,
                "financeiro",
                TenantId(scope.tenant_id),
                UnidadeId(scope.unit_id),
                CorrelationId(scope.correlation_id),
                None,
                IdempotencyKey(idempotency_key),
                contexto.solicitado_em,
                {
                    "pedido_id": pedido.pedido_id,
                    "recebimento_id": recebimento.recebimento_id,
                    "valor": str(salva.valor_original),
                    "reconciliacao": salva.reconciliacao.value,
                },
                salva.versao,
            )
            auditoria = EventoAuditoria(
                str(uuid4()),
                scope.tenant_id,
                scope.unit_id,
                contexto.usuario_id,
                next(iter(sorted(contexto.papeis, key=str)), None),
                "financeiro.compras.registrar",
                "obrigacao_compra_fiscal",
                salva.obrigacao_id,
                "sucesso",
                "obrigacao_criada_sem_pagamento",
                scope.correlation_id,
                contexto.solicitado_em,
                contexto.origem,
                "financial_tax_bridge_v1",
                metadata=sanitizar_metadata(
                    {
                        "pedido_id": pedido.pedido_id,
                        "recebimento_id": recebimento.recebimento_id,
                        "valor": str(salva.valor_original),
                    }
                ),
            )
            return ResultadoBridgeFinanceiroFiscal(salva, False, (evento,), (auditoria,))

        return self._repositorio.atomicamente(operacao)

    def ajustar_obrigacao(
        self,
        *,
        contexto: ContextoExecucao,
        scope: ExecutionScope,
        recebimento_id: str,
        tipo: TipoAjusteObrigacaoCompra,
        origem_id: str,
        motivo: str,
        idempotency_key: str,
        valor: Decimal | None = None,
    ) -> ObrigacaoCompraFiscal:
        _autorizar(contexto, Permissao.FINANCEIRO_COMPRAS_REGISTRAR)
        _validar_scope(contexto, scope)

        def operacao() -> ObrigacaoCompraFiscal:
            obrigacao = self._repositorio.obrigacao_por_recebimento(
                scope, recebimento_id
            )
            if obrigacao is None:
                raise EfeitoFinanceiroFiscalBloqueado("obrigacao_compra_inexistente")
            existente = self._repositorio.ajuste_por_idempotencia(
                scope, idempotency_key
            )
            if existente is not None:
                valor_esperado = obrigacao.saldo if valor is None else _dinheiro(valor)
                if (
                    existente.tipo is not tipo
                    or existente.origem_id != origem_id
                    or existente.motivo != motivo
                    or (valor is not None and existente.valor != valor_esperado)
                ):
                    raise ConflitoIdempotenciaPagamento(
                        "ajuste_financeiro_divergente"
                    )
                return obrigacao
            ajuste = AjusteObrigacaoCompra(
                str(uuid4()),
                scope,
                obrigacao.obrigacao_id,
                tipo,
                obrigacao.saldo if valor is None else valor,
                motivo,
                origem_id,
                idempotency_key,
                contexto.usuario_id,
                contexto.solicitado_em,
                scope.correlation_id,
            )
            _, atualizada, _ = self._repositorio.salvar_ajuste(ajuste)
            return atualizada

        return self._repositorio.atomicamente(operacao)

    def decidir_credito(
        self,
        *,
        contexto: ContextoExecucao,
        scope: ExecutionScope,
        recebimento_id: str,
        tributo: str,
        base_calculo: Decimal,
        valor_destacado: Decimal,
        cfop: str,
        cst: str,
        regra: RegraCreditoTributario | None,
        idempotency_key: str,
    ) -> DecisaoCreditoTributario:
        _autorizar(contexto, Permissao.FINANCEIRO_TRIBUTOS_DECIDIR)
        _validar_scope(contexto, scope)
        obrigacao = self._repositorio.obrigacao_por_recebimento(scope, recebimento_id)
        if obrigacao is None:
            raise EfeitoFinanceiroFiscalBloqueado("obrigacao_compra_inexistente")
        base = _dinheiro(base_calculo)
        destacado = _dinheiro(valor_destacado)
        data = contexto.solicitado_em.date()
        vigente = bool(
            regra
            and regra.vigente_desde <= data
            and (regra.vigente_ate is None or data <= regra.vigente_ate)
        )
        if not vigente or regra is None:
            resultado = ResultadoCreditoTributario.BLOQUEADO
            credito = Decimal(0)
            motivo = "regra_tributaria_ausente_ou_fora_da_vigencia"
        elif (
            cfop not in regra.cfops_elegiveis or cst not in regra.csts_elegiveis
        ):
            resultado = ResultadoCreditoTributario.INELEGIVEL
            credito = Decimal(0)
            motivo = "cfop_ou_cst_nao_elegivel_pela_regra"
        else:
            resultado = ResultadoCreditoTributario.ELEGIVEL
            credito = min(destacado, _dinheiro(base * regra.aliquota_credito))
            motivo = "criterios_explicitos_da_regra_atendidos"
        decisao = DecisaoCreditoTributario(
            str(uuid4()),
            scope,
            obrigacao.obrigacao_id,
            obrigacao.versao,
            tributo.upper(),
            resultado,
            base,
            destacado,
            credito,
            cfop,
            cst,
            regra.regra_id if vigente and regra else None,
            regra.versao if vigente and regra else None,
            motivo,
            idempotency_key,
            contexto.usuario_id,
            contexto.solicitado_em,
            scope.correlation_id,
        )
        salva, _ = self._repositorio.atomicamente(
            lambda: self._repositorio.salvar_decisao(decisao)
        )
        return salva

    def projetar(self, scope: ExecutionScope) -> ResumoFinanceiroFiscal:
        obrigacoes = self._repositorio.listar_obrigacoes(scope)
        decisoes = self._repositorio.listar_decisoes(scope)
        versoes = {item.obrigacao_id: item.versao for item in obrigacoes}
        return ResumoFinanceiroFiscal(
            scope,
            len(obrigacoes),
            sum((item.valor_original for item in obrigacoes), Decimal(0)),
            sum((item.valor_ajustado for item in obrigacoes), Decimal(0)),
            sum((item.saldo for item in obrigacoes), Decimal(0)),
            sum(
                (
                    item.valor_credito
                    for item in decisoes
                    if item.resultado is ResultadoCreditoTributario.ELEGIVEL
                    and versoes.get(item.obrigacao_id) == item.obrigacao_versao
                ),
                Decimal(0),
            ),
            tuple(sorted({item.recebimento_id for item in obrigacoes})),
        )
