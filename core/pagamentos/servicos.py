"""Casos de uso financeiros puros; nenhum efeito em Pedido, cozinha ou estoque."""

import hashlib
import json
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from core.dominio.dinheiro import Dinheiro
from core.dominio.enums import PagamentoStatus
from core.dominio.ids import (
    CausationId,
    CorrelationId,
    EventoId,
    IdempotencyKey,
    TenantId,
    UnidadeId,
)
from core.eventos.modelos import EnvelopeMensagem
from core.seguranca.auditoria import EventoAuditoria, sanitizar_metadata
from core.seguranca.autorizacao import AutorizarAcao
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Papel, Permissao

from .adapters import WebhookNormalizado
from .erros import (
    FonteFinanceiraNaoConfiavel,
    OperacaoPagamentoNaoAutorizada,
    RecursoPagamentoIndisponivel,
    ValorPagamentoInvalido,
)
from .modelos import (
    CodigoCriterioFinanceiro,
    ConfirmacaoPagamento,
    CriterioFinanceiro,
    DivergenciaReconciliacao,
    MetodoPagamento,
    ObrigacaoPagamento,
    Pagamento,
    ResultadoPagamento,
    ResultadoReconciliacao,
    ResultadoReconhecimentoVenda,
    StatusTransacao,
    TipoTransacao,
    TransacaoPagamento,
    VendaFinanceira,
)
from .repositorios import RepositorioPagamentos
from .venda_legada import AdapterVendaLegada


def _hash(*valores: object) -> str:
    return hashlib.sha256(
        json.dumps(valores, default=str, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _autorizar(
    contexto: ContextoExecucao,
    permissao: Permissao,
    recurso_tenant: str,
    recurso_unidade: str,
) -> None:
    if contexto.identidade_sistema:
        return
    decisao = AutorizarAcao().executar(
        contexto=contexto,
        permissao=permissao,
        recurso="pagamento",
        tenant_recurso=recurso_tenant,
        unidade_recurso=recurso_unidade,
    )
    if not decisao.autorizado:
        raise OperacaoPagamentoNaoAutorizada(decisao.codigo)


def _efeitos(
    contexto: ContextoExecucao,
    pagamento: Pagamento,
    transacao: TransacaoPagamento,
    evento_tipo: str,
    acao: str,
    antes: str,
) -> tuple[tuple[EnvelopeMensagem, ...], tuple[EventoAuditoria, ...]]:
    evento = EnvelopeMensagem(
        EventoId(str(uuid4())),
        evento_tipo,
        pagamento.id,
        "pagamento",
        TenantId(pagamento.tenant_id),
        UnidadeId(pagamento.unidade_id),
        CorrelationId(transacao.correlation_id),
        CausationId(transacao.causation_id) if transacao.causation_id else None,
        IdempotencyKey(transacao.idempotency_key),
        transacao.occurred_at,
        {
            "pedido_id": pagamento.pedido_id,
            "valor": str(transacao.valor.valor),
            "metodo": transacao.metodo.value,
            "status": pagamento.status.value,
            "aggregate_version": pagamento.versao,
        },
        pagamento.versao,
    )
    papel = next(iter(sorted(contexto.papeis, key=str)), None)
    auditoria = EventoAuditoria(
        str(uuid4()),
        pagamento.tenant_id,
        pagamento.unidade_id,
        contexto.usuario_id,
        papel,
        acao,
        "pagamento",
        pagamento.id,
        "sucesso",
        "operacao_financeira",
        transacao.correlation_id,
        transacao.occurred_at,
        contexto.origem,
        "pagamentos_v1",
        causation_id=transacao.causation_id,
        antes_resumido=(("status", antes),),
        depois_resumido=(("status", pagamento.status.value),),
        metadata=sanitizar_metadata(
            {
                "valor": str(transacao.valor.valor),
                "metodo": transacao.metodo.value,
                "pedido_id": pagamento.pedido_id,
            }
        ),
    )
    return (evento,), (auditoria,)


def criar_obrigacao_pagamento(
    *,
    contexto: ContextoExecucao,
    repositorio: RepositorioPagamentos,
    pagamento_id: str,
    pedido_id: str,
    valor_previsto: Dinheiro,
    metodo: MetodoPagamento,
    idempotency_key: str,
    timestamp: datetime,
    comanda_id: str | None = None,
    provedor: str | None = None,
    recebimento_posterior: bool = False,
) -> ResultadoPagamento:
    _autorizar(
        contexto, Permissao.PAGAMENTO_REGISTRAR, contexto.tenant_id, contexto.unidade_id
    )
    fp = _hash(
        pagamento_id,
        pedido_id,
        valor_previsto.valor,
        metodo,
        comanda_id,
        recebimento_posterior,
    )

    def op() -> ResultadoPagamento:
        obrigacao = ObrigacaoPagamento(
            pagamento_id,
            contexto.tenant_id,
            contexto.unidade_id,
            pedido_id,
            valor_previsto,
            timestamp,
            1,
            contexto.correlation_id,
            comanda_id,
        )
        salva = repositorio.salvar_obrigacao(obrigacao, idempotency_key, fp)
        atual = repositorio.buscar_pagamento(
            contexto.tenant_id, contexto.unidade_id, salva.id
        )
        if atual:
            trans = repositorio.listar_transacoes(
                contexto.tenant_id, contexto.unidade_id, salva.id
            )[0]
            eventos, auditorias = _efeitos(
                contexto,
                atual,
                trans,
                "pagamento.iniciado",
                "pagamento.obrigacao_criada",
                PagamentoStatus.NAO_INICIADO.value,
            )
            return ResultadoPagamento(atual, trans, None, eventos, auditorias, True)
        status = (
            PagamentoStatus.AGUARDANDO_ENTREGA
            if metodo == MetodoPagamento.PAGAMENTO_NA_ENTREGA
            else PagamentoStatus.PENDENTE
        )
        pagamento = Pagamento(
            salva.id,
            salva.tenant_id,
            salva.unidade_id,
            salva.pedido_id,
            status,
            metodo,
            valor_previsto,
            Dinheiro(Decimal(0), valor_previsto.moeda),
            Dinheiro(Decimal(0), valor_previsto.moeda),
            valor_previsto,
            valor_previsto.moeda,
            recebimento_posterior,
            timestamp,
            timestamp,
            1,
            contexto.correlation_id,
            comanda_id,
            provedor,
        )
        trans = TransacaoPagamento(
            str(uuid4()),
            pagamento.id,
            pagamento.tenant_id,
            pagamento.unidade_id,
            TipoTransacao.INICIACAO,
            StatusTransacao.PENDENTE,
            Dinheiro(Decimal(0), pagamento.moeda),
            metodo,
            provedor,
            None,
            idempotency_key,
            timestamp,
            timestamp,
            contexto.correlation_id,
            contexto.causation_id,
            (),
        )
        repositorio.salvar_pagamento(pagamento, 0)
        repositorio.append_transacao(trans, fp)
        eventos, auditorias = _efeitos(
            contexto,
            pagamento,
            trans,
            "pagamento.iniciado",
            "pagamento.obrigacao_criada",
            PagamentoStatus.NAO_INICIADO.value,
        )
        return ResultadoPagamento(pagamento, trans, None, eventos, auditorias)

    return repositorio.executar_atomicamente(op)


_METODOS_CONFIRMAVEIS_MANUALMENTE = frozenset({MetodoPagamento.DINHEIRO})


def _confirmar_pagamento_validado(
    *,
    contexto: ContextoExecucao,
    repositorio: RepositorioPagamentos,
    pagamento_id: str,
    valor: Dinheiro,
    metodo: MetodoPagamento,
    idempotency_key: str,
    expected_version: int,
    timestamp: datetime,
    referencia_externa: str | None = None,
    correlation_id: str | None = None,
    valor_recebido: Dinheiro | None = None,
    fonte_financeira_validada: bool,
) -> ResultadoPagamento:
    if not fonte_financeira_validada and metodo not in _METODOS_CONFIRMAVEIS_MANUALMENTE:
        raise FonteFinanceiraNaoConfiavel(
            "metodo exige confirmacao de fonte financeira validada"
        )
    if valor.valor <= 0:
        raise ValorPagamentoInvalido("valor deve ser positivo")
    fp = _hash(
        pagamento_id,
        valor.valor,
        metodo,
        referencia_externa,
        valor_recebido.valor if valor_recebido else None,
    )

    def op() -> ResultadoPagamento:
        pagamento = repositorio.buscar_pagamento(
            contexto.tenant_id, contexto.unidade_id, pagamento_id
        )
        obrigacao = repositorio.buscar_obrigacao(
            contexto.tenant_id, contexto.unidade_id, pagamento_id
        )
        if not pagamento or not obrigacao:
            raise RecursoPagamentoIndisponivel("recurso_indisponivel")
        _autorizar(
            contexto,
            Permissao.PAGAMENTO_CONFIRMAR,
            pagamento.tenant_id,
            pagamento.unidade_id,
        )
        existentes = repositorio.listar_transacoes(
            contexto.tenant_id, contexto.unidade_id, pagamento_id
        )
        repetida = next(
            (t for t in existentes if t.idempotency_key == idempotency_key), None
        )
        if repetida:
            if _hash(
                pagamento_id,
                repetida.valor.valor,
                repetida.metodo,
                repetida.id_externo,
                None,
            ) != fp and not (valor_recebido is None and repetida.valor == valor):
                from .erros import ConflitoIdempotenciaPagamento

                raise ConflitoIdempotenciaPagamento("conflito_idempotencia")
            return ResultadoPagamento(pagamento, repetida, None, (), (), True)
        if pagamento.versao != expected_version:
            from .erros import ConcorrenciaPagamento

            raise ConcorrenciaPagamento("versao_pagamento_divergente")
        saldo = pagamento.saldo
        recebido = valor_recebido or valor
        financeiro = valor
        troco = Dinheiro(Decimal(0), pagamento.moeda)
        if metodo == MetodoPagamento.DINHEIRO and recebido.valor > saldo.valor:
            financeiro = saldo
            troco = recebido - saldo
        elif valor.valor > saldo.valor:
            raise ValorPagamentoInvalido("confirmacao excede obrigacao")
        novo_pago = pagamento.valor_pago + financeiro
        novo_saldo = pagamento.valor_previsto - (novo_pago - pagamento.valor_estornado)
        status = (
            PagamentoStatus.PAGO
            if novo_saldo.valor == 0
            else PagamentoStatus.PARCIALMENTE_PAGO
        )
        novo = replace(
            pagamento,
            status=status,
            valor_pago=novo_pago,
            saldo=novo_saldo,
            atualizado_em=timestamp,
            versao=pagamento.versao + 1,
            metodo=metodo,
            correlation_id=correlation_id or contexto.correlation_id,
        )
        trans = TransacaoPagamento(
            str(uuid4()),
            pagamento.id,
            pagamento.tenant_id,
            pagamento.unidade_id,
            TipoTransacao.CONFIRMACAO,
            StatusTransacao.CONFIRMADA,
            financeiro,
            metodo,
            pagamento.provedor,
            referencia_externa,
            idempotency_key,
            timestamp,
            timestamp,
            correlation_id or contexto.correlation_id,
            contexto.causation_id,
            (("troco", str(troco.valor)),),
        )
        repositorio.append_transacao(trans, fp)
        repositorio.salvar_pagamento(novo, expected_version)
        confirmacao = ConfirmacaoPagamento(
            pagamento.id,
            financeiro,
            recebido,
            troco,
            metodo,
            referencia_externa,
            timestamp,
        )
        tipo = (
            "pagamento.confirmado"
            if status == PagamentoStatus.PAGO
            else "pagamento.parcial_confirmado"
        )
        eventos, auditorias = _efeitos(
            contexto,
            novo,
            trans,
            tipo,
            "pagamento.confirmado_manual",
            pagamento.status.value,
        )
        return ResultadoPagamento(novo, trans, confirmacao, eventos, auditorias)

    return repositorio.executar_atomicamente(op)


def confirmar_pagamento(
    *,
    contexto: ContextoExecucao,
    repositorio: RepositorioPagamentos,
    pagamento_id: str,
    valor: Dinheiro,
    metodo: MetodoPagamento,
    idempotency_key: str,
    expected_version: int,
    timestamp: datetime,
    referencia_externa: str | None = None,
    correlation_id: str | None = None,
    valor_recebido: Dinheiro | None = None,
) -> ResultadoPagamento:
    """Confirmação humana/manual; somente dinheiro pode liquidar sem provedor."""

    return _confirmar_pagamento_validado(
        contexto=contexto,
        repositorio=repositorio,
        pagamento_id=pagamento_id,
        valor=valor,
        metodo=metodo,
        idempotency_key=idempotency_key,
        expected_version=expected_version,
        timestamp=timestamp,
        referencia_externa=referencia_externa,
        correlation_id=correlation_id,
        valor_recebido=valor_recebido,
        fonte_financeira_validada=False,
    )


def processar_webhook(
    *,
    contexto: ContextoExecucao,
    repositorio: RepositorioPagamentos,
    pagamento_id: str,
    webhook: WebhookNormalizado,
    expected_version: int,
) -> ResultadoPagamento | None:
    if not webhook.assinatura_validada or webhook.tipo not in {"confirmado", "pago"}:
        return None
    return _confirmar_pagamento_validado(
        contexto=contexto,
        repositorio=repositorio,
        pagamento_id=pagamento_id,
        valor=webhook.valor,
        metodo=MetodoPagamento.PIX,
        referencia_externa=webhook.id_externo,
        idempotency_key=f"webhook:{webhook.provedor}:{webhook.idempotency_key}",
        expected_version=expected_version,
        timestamp=webhook.timestamp,
        fonte_financeira_validada=True,
    )


def registrar_estorno(
    *,
    contexto: ContextoExecucao,
    repositorio: RepositorioPagamentos,
    pagamento_id: str,
    valor: Dinheiro,
    motivo: str,
    idempotency_key: str,
    expected_version: int,
    timestamp: datetime,
) -> ResultadoPagamento:
    if not motivo.strip() or valor.valor <= 0:
        raise ValorPagamentoInvalido("estorno exige valor positivo e motivo")
    fp = _hash(pagamento_id, valor.valor, motivo)

    def op() -> ResultadoPagamento:
        pagamento = repositorio.buscar_pagamento(
            contexto.tenant_id, contexto.unidade_id, pagamento_id
        )
        if not pagamento:
            raise RecursoPagamentoIndisponivel("recurso_indisponivel")
        _autorizar(
            contexto,
            Permissao.PAGAMENTO_ESTORNAR,
            pagamento.tenant_id,
            pagamento.unidade_id,
        )
        if pagamento.versao != expected_version:
            from .erros import ConcorrenciaPagamento

            raise ConcorrenciaPagamento("versao_pagamento_divergente")
        if valor.valor > (pagamento.valor_pago - pagamento.valor_estornado).valor:
            raise ValorPagamentoInvalido("estorno excede valor liquido")
        estornado = pagamento.valor_estornado + valor
        integral = estornado == pagamento.valor_pago
        status = (
            PagamentoStatus.ESTORNADO if integral else PagamentoStatus.ESTORNADO_PARCIAL
        )
        novo = replace(
            pagamento,
            status=status,
            valor_estornado=estornado,
            saldo=pagamento.valor_previsto - (pagamento.valor_pago - estornado),
            atualizado_em=timestamp,
            versao=pagamento.versao + 1,
        )
        trans = TransacaoPagamento(
            str(uuid4()),
            pagamento.id,
            pagamento.tenant_id,
            pagamento.unidade_id,
            TipoTransacao.ESTORNO,
            StatusTransacao.CONFIRMADA,
            valor,
            pagamento.metodo,
            pagamento.provedor,
            None,
            idempotency_key,
            timestamp,
            timestamp,
            contexto.correlation_id,
            contexto.causation_id,
            (("motivo", motivo),),
        )
        trans = repositorio.append_transacao(trans, fp)
        repositorio.salvar_pagamento(novo, expected_version)
        eventos, auditorias = _efeitos(
            contexto,
            novo,
            trans,
            "pagamento.estornado" if integral else "pagamento.estornado_parcial",
            "pagamento.estornado",
            pagamento.status.value,
        )
        return ResultadoPagamento(novo, trans, None, eventos, auditorias)

    return repositorio.executar_atomicamente(op)


def _registrar_estado_sem_valor(
    *,
    contexto: ContextoExecucao,
    repositorio: RepositorioPagamentos,
    pagamento_id: str,
    destino: PagamentoStatus,
    tipo_transacao: TipoTransacao,
    status_transacao: StatusTransacao,
    evento_tipo: str,
    idempotency_key: str,
    expected_version: int,
    timestamp: datetime,
    motivo: str,
) -> ResultadoPagamento:
    if not motivo.strip():
        raise ValorPagamentoInvalido("operacao exige motivo")
    fp = _hash(pagamento_id, destino, motivo)

    def op() -> ResultadoPagamento:
        pagamento = repositorio.buscar_pagamento(
            contexto.tenant_id, contexto.unidade_id, pagamento_id
        )
        if not pagamento:
            raise RecursoPagamentoIndisponivel("recurso_indisponivel")
        _autorizar(
            contexto,
            Permissao.PAGAMENTO_REGISTRAR,
            pagamento.tenant_id,
            pagamento.unidade_id,
        )
        if pagamento.versao != expected_version:
            from .erros import ConcorrenciaPagamento

            raise ConcorrenciaPagamento("versao_pagamento_divergente")
        permitidas = {
            PagamentoStatus.FALHOU: {PagamentoStatus.PENDENTE},
            PagamentoStatus.PENDENTE: {PagamentoStatus.FALHOU},
            PagamentoStatus.CANCELADO: {
                PagamentoStatus.NAO_INICIADO,
                PagamentoStatus.PENDENTE,
                PagamentoStatus.AGUARDANDO_ENTREGA,
                PagamentoStatus.AGUARDANDO_FECHAMENTO,
                PagamentoStatus.FALHOU,
            },
        }
        if pagamento.status not in permitidas[destino]:
            raise ValorPagamentoInvalido("transicao_pagamento_invalida")
        novo = replace(
            pagamento,
            status=destino,
            atualizado_em=timestamp,
            versao=pagamento.versao + 1,
        )
        transacao = TransacaoPagamento(
            str(uuid4()),
            pagamento.id,
            pagamento.tenant_id,
            pagamento.unidade_id,
            tipo_transacao,
            status_transacao,
            Dinheiro(Decimal(0), pagamento.moeda),
            pagamento.metodo,
            pagamento.provedor,
            None,
            idempotency_key,
            timestamp,
            timestamp,
            contexto.correlation_id,
            contexto.causation_id,
            (("motivo", motivo),),
            motivo if destino == PagamentoStatus.FALHOU else None,
        )
        transacao = repositorio.append_transacao(transacao, fp)
        repositorio.salvar_pagamento(novo, expected_version)
        eventos, auditorias = _efeitos(
            contexto,
            novo,
            transacao,
            evento_tipo,
            evento_tipo,
            pagamento.status.value,
        )
        return ResultadoPagamento(novo, transacao, None, eventos, auditorias)

    return repositorio.executar_atomicamente(op)


def registrar_falha(**kwargs: Any) -> ResultadoPagamento:
    return _registrar_estado_sem_valor(
        **kwargs,
        destino=PagamentoStatus.FALHOU,
        tipo_transacao=TipoTransacao.FALHA,
        status_transacao=StatusTransacao.FALHOU,
        evento_tipo="pagamento.falhou",
    )


def retentar_pagamento(**kwargs: Any) -> ResultadoPagamento:
    return _registrar_estado_sem_valor(
        **kwargs,
        destino=PagamentoStatus.PENDENTE,
        tipo_transacao=TipoTransacao.INICIACAO,
        status_transacao=StatusTransacao.PENDENTE,
        evento_tipo="pagamento.retentado",
    )


def cancelar_pagamento(**kwargs: Any) -> ResultadoPagamento:
    return _registrar_estado_sem_valor(
        **kwargs,
        destino=PagamentoStatus.CANCELADO,
        tipo_transacao=TipoTransacao.CANCELAMENTO,
        status_transacao=StatusTransacao.CANCELADA,
        evento_tipo="pagamento.cancelado",
    )


def avaliar_criterio_financeiro(
    *,
    contexto: ContextoExecucao,
    pagamento: Pagamento | None,
    pedido_id: str,
    timestamp: datetime,
    comanda_fechada: bool = False,
    saldo_comanda_resolvido: bool = False,
    recebimento_posterior_autorizado: bool = False,
    responsavel_autorizado: str | None = None,
    motivo: str | None = None,
    confirmacao_humana: bool = False,
) -> CriterioFinanceiro:
    zero = Dinheiro(Decimal(0), pagamento.moeda if pagamento else "BRL")
    codigo, elegivel, valor, razao = (
        CodigoCriterioFinanceiro.NAO_ELEGIVEL,
        False,
        zero,
        "obrigacao financeira nao resolvida",
    )
    if (
        pagamento
        and pagamento.status == PagamentoStatus.PAGO
        and pagamento.saldo.valor == 0
    ):
        codigo, elegivel, valor, razao = (
            CodigoCriterioFinanceiro.PAGAMENTO_CONFIRMADO,
            True,
            pagamento.valor_pago - pagamento.valor_estornado,
            "pagamento liquido resolve obrigacao",
        )
    elif comanda_fechada and saldo_comanda_resolvido and pagamento:
        codigo, elegivel, valor, razao = (
            CodigoCriterioFinanceiro.COMANDA_FECHADA,
            True,
            pagamento.valor_previsto,
            "comanda fechada com saldo resolvido",
        )
    elif (
        recebimento_posterior_autorizado
        and pagamento
        and responsavel_autorizado
        and motivo
        and confirmacao_humana
        and Papel.GERENTE_IA not in contexto.papeis
    ):
        codigo, elegivel, valor, razao = (
            CodigoCriterioFinanceiro.RECEBIMENTO_POSTERIOR_AUTORIZADO,
            True,
            pagamento.valor_previsto,
            motivo,
        )
    return CriterioFinanceiro(
        elegivel,
        codigo,
        razao,
        pedido_id,
        valor,
        "financeiro_v1",
        pagamento.versao if pagamento else 1,
        responsavel_autorizado or contexto.usuario_id,
        timestamp,
        contexto.correlation_id,
        pagamento.id if pagamento else None,
        pagamento.comanda_id if pagamento else None,
        sanitizar_metadata({"confirmacao_humana": confirmacao_humana}),
    )


def reconhecer_venda(
    *,
    contexto: ContextoExecucao,
    repositorio: RepositorioPagamentos,
    criterio: CriterioFinanceiro,
    metodo: MetodoPagamento,
    idempotency_key: str,
    timestamp: datetime,
    produto_id_legado: int = 1,
    adapter_legado: AdapterVendaLegada | None = None,
) -> ResultadoReconhecimentoVenda:
    if not criterio.elegivel or criterio.valor_reconhecivel.valor <= 0:
        raise ValorPagamentoInvalido("criterio financeiro nao elegivel")
    _autorizar(
        contexto, Permissao.PAGAMENTO_CONFIRMAR, contexto.tenant_id, contexto.unidade_id
    )
    fp = _hash(
        criterio.pedido_id,
        criterio.codigo,
        criterio.versao,
        criterio.valor_reconhecivel.valor,
        metodo,
    )

    def op() -> ResultadoReconhecimentoVenda:
        venda = VendaFinanceira(
            str(uuid4()),
            contexto.tenant_id,
            contexto.unidade_id,
            criterio.pedido_id,
            criterio.pagamento_id,
            criterio.comanda_id,
            criterio.codigo,
            criterio.versao,
            criterio.valor_reconhecivel,
            metodo,
            timestamp,
            contexto.correlation_id,
            idempotency_key,
        )
        salva = repositorio.salvar_venda(venda, fp)
        idempotente = salva is not venda
        representacao = (adapter_legado or AdapterVendaLegada()).materializar(
            salva, produto_id=produto_id_legado
        )
        evento = EnvelopeMensagem(
            EventoId(str(uuid4())),
            "venda.criada",
            salva.id,
            "venda",
            TenantId(salva.tenant_id),
            UnidadeId(salva.unidade_id),
            CorrelationId(salva.correlation_id),
            CausationId(contexto.causation_id) if contexto.causation_id else None,
            IdempotencyKey(idempotency_key),
            timestamp,
            {
                "pedido_id": salva.pedido_id,
                "pagamento_id": salva.pagamento_id,
                "valor": str(salva.valor.valor),
                "criterio": salva.criterio_codigo.value,
                "aggregate_version": 1,
            },
            1,
        )
        papel = next(iter(sorted(contexto.papeis, key=str)), None)
        auditoria = EventoAuditoria(
            str(uuid4()),
            salva.tenant_id,
            salva.unidade_id,
            contexto.usuario_id,
            papel,
            "venda.reconhecida",
            "venda",
            salva.id,
            "sucesso",
            criterio.motivo,
            salva.correlation_id,
            timestamp,
            contexto.origem,
            criterio.policy,
            metadata=sanitizar_metadata(
                {
                    "pedido_id": salva.pedido_id,
                    "pagamento_id": salva.pagamento_id,
                    "criterio": criterio.codigo.value,
                    "valor": str(salva.valor.valor),
                }
            ),
        )
        return ResultadoReconhecimentoVenda(
            salva, representacao, evento, auditoria, idempotente
        )

    return repositorio.executar_atomicamente(op)


def reconciliar_pagamentos(
    *,
    contexto: ContextoExecucao,
    repositorio: RepositorioPagamentos,
    pagamentos: tuple[Pagamento, ...],
    externas: tuple[Any, ...] = (),
    timestamp: datetime,
) -> ResultadoReconciliacao:
    _autorizar(
        contexto,
        Permissao.FINANCEIRO_VISUALIZAR,
        contexto.tenant_id,
        contexto.unidade_id,
    )
    divergencias: list[DivergenciaReconciliacao] = []
    externos = {getattr(e, "id_externo", ""): e for e in externas}
    conhecidos: set[str] = set()
    for p in pagamentos:
        obrigacao = repositorio.buscar_obrigacao(
            contexto.tenant_id, contexto.unidade_id, p.id
        )
        transacoes = repositorio.listar_transacoes(
            contexto.tenant_id, contexto.unidade_id, p.id
        )
        confirmadas = [
            t
            for t in transacoes
            if t.tipo == TipoTransacao.CONFIRMACAO
            and t.status == StatusTransacao.CONFIRMADA
        ]
        conhecidos.update(t.id_externo for t in transacoes if t.id_externo)
        if not obrigacao:
            divergencias.append(
                DivergenciaReconciliacao(
                    "confirmacao_sem_obrigacao",
                    "critica",
                    "Pagamento sem obrigacao",
                    p.id,
                )
            )
        if p.status == PagamentoStatus.PAGO and not confirmadas:
            divergencias.append(
                DivergenciaReconciliacao(
                    "pagamento_sem_confirmacao",
                    "critica",
                    "Estado pago sem transacao confirmada",
                    p.id,
                )
            )
        soma = sum((t.valor.valor for t in confirmadas), start=0)
        if soma != p.valor_pago.valor:
            divergencias.append(
                DivergenciaReconciliacao(
                    "valor_divergente",
                    "critica",
                    "Confirmacoes divergem do agregado",
                    p.id,
                )
            )
        if p.status == PagamentoStatus.PAGO and not repositorio.buscar_venda_pedido(
            contexto.tenant_id, contexto.unidade_id, p.pedido_id, p.versao
        ):
            divergencias.append(
                DivergenciaReconciliacao(
                    "venda_ausente", "alta", "Venda ausente apesar do pagamento", p.id
                )
            )
    for externo in externos:
        if externo and externo not in conhecidos:
            divergencias.append(
                DivergenciaReconciliacao(
                    "transacao_externa_desconhecida",
                    "alta",
                    f"Transacao externa desconhecida: {externo}",
                )
            )
    papel = next(iter(sorted(contexto.papeis, key=str)), None)
    auditoria = EventoAuditoria(
        str(uuid4()),
        contexto.tenant_id,
        contexto.unidade_id,
        contexto.usuario_id,
        papel,
        "pagamento.reconciliado",
        "pagamento",
        None,
        "sucesso",
        "reconciliacao_manual",
        contexto.correlation_id,
        timestamp,
        contexto.origem,
        "financeiro_v1",
        metadata=(("divergencias", len(divergencias)),),
    )
    return ResultadoReconciliacao(
        contexto.tenant_id,
        contexto.unidade_id,
        timestamp,
        tuple(divergencias),
        contexto.correlation_id,
        (auditoria,),
    )


solicitar_estorno = registrar_estorno
