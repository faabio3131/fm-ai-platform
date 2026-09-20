"""Casos de uso determinísticos de compra, conferência e recebimento físico."""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Protocol, runtime_checkable
from uuid import uuid4
from xml.etree import ElementTree

from core.dominio.ids import (
    CausationId,
    CorrelationId,
    EventoId,
    IdempotencyKey,
    TenantId,
    UnidadeId,
)
from core.estoque.modelos import ResultadoMovimento, TipoMovimento
from core.estoque.repositorios import RepositorioEstoque
from core.estoque.servicos import registrar_movimento
from core.eventos.modelos import EnvelopeMensagem
from core.seguranca.auditoria import EventoAuditoria, sanitizar_metadata
from core.seguranca.autorizacao import AutorizarAcao
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Permissao
from kordena_fiscal.domain import (
    ExecutionScope,
    FiscalEnvironment,
    FiscalValidationError,
)
from kordena_fiscal.inbound import FiscalInboundDocument

from .erros import (
    ConflitoProcurement,
    EstadoProcurementInvalido,
    ProcurementForaDoEscopo,
    ProcurementNaoAutorizado,
)
from .modelos import (
    CustoAquisicao,
    Divergencia,
    Fornecedor,
    ItemPedidoCompra,
    ItemRecebido,
    PedidoCompra,
    RecebimentoCompra,
    StatusPedidoCompra,
    StatusRecebimento,
    TipoDivergencia,
    VinculoProdutoFornecedor,
)
from .repositorios import RepositorioProcurement


@dataclass(frozen=True, slots=True)
class ResultadoRecebimento:
    recebimento: RecebimentoCompra
    movimentos_estoque: tuple[ResultadoMovimento, ...]
    idempotente: bool
    eventos: tuple[EnvelopeMensagem, ...] = ()
    auditorias: tuple[EventoAuditoria, ...] = ()


@runtime_checkable
class _VinculadoAUow(Protocol):
    @property
    def unit_of_work_token(self) -> object: ...


def _autorizar(contexto: ContextoExecucao, permissao: Permissao) -> None:
    if contexto.identidade_sistema:
        return
    decisao = AutorizarAcao().executar(
        contexto=contexto,
        permissao=permissao,
        recurso="procurement",
        tenant_recurso=contexto.tenant_id,
        unidade_recurso=contexto.unidade_id,
    )
    if not decisao.autorizado:
        raise ProcurementNaoAutorizado(decisao.codigo)


def _escopo(contexto: ContextoExecucao, scope: ExecutionScope) -> None:
    unidades = contexto.unidades_permitidas or frozenset({contexto.unidade_id})
    if contexto.tenant_id != scope.tenant_id or scope.unit_id not in unidades:
        raise ProcurementForaDoEscopo("recurso_indisponivel")


def _totais_xml(documento: FiscalInboundDocument) -> tuple[Decimal, Decimal, Decimal]:
    conteudo = documento.xml_content
    upper = conteudo.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise FiscalValidationError("NF-e XML declarations are not accepted")
    try:
        raiz = ElementTree.fromstring(conteudo)
    except ElementTree.ParseError as exc:
        raise FiscalValidationError("NF-e XML is malformed") from exc

    def local(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    total = next((no for no in raiz.iter() if local(no.tag) == "ICMSTot"), None)
    if total is None:
        soma = sum((item.total_value for item in documento.items), Decimal(0))
        return Decimal(0), Decimal(0), soma

    def valor(nome: str, padrao: Decimal | None = None) -> Decimal:
        no = next((filho for filho in total if local(filho.tag) == nome), None)
        if no is None or not (no.text or "").strip():
            if padrao is not None:
                return padrao
            raise FiscalValidationError(f"NF-e XML is missing {nome}")
        numero = Decimal((no.text or "").strip())
        if not numero.is_finite() or numero < 0:
            raise FiscalValidationError(f"NF-e XML field {nome} is invalid")
        return numero

    soma = sum((item.total_value for item in documento.items), Decimal(0))
    return valor("vFrete", Decimal(0)), valor("vDesc", Decimal(0)), valor("vNF", soma)


class ServicoProcurement:
    def __init__(
        self,
        *,
        repositorio: RepositorioProcurement,
        estoque: RepositorioEstoque,
    ) -> None:
        procurement_uow = (
            repositorio.unit_of_work_token
            if isinstance(repositorio, _VinculadoAUow)
            else None
        )
        estoque_uow = (
            estoque.unit_of_work_token if isinstance(estoque, _VinculadoAUow) else None
        )
        if (procurement_uow is None) != (estoque_uow is None) or (
            procurement_uow is not None and procurement_uow is not estoque_uow
        ):
            raise ValueError(
                "procurement e estoque devem compartilhar a mesma Unit of Work"
            )
        self._repositorio = repositorio
        self._estoque = estoque

    def cadastrar_fornecedor(
        self,
        *,
        contexto: ContextoExecucao,
        scope: ExecutionScope,
        fornecedor_id: str,
        documento: str,
        nome: str,
    ) -> Fornecedor:
        _escopo(contexto, scope)
        _autorizar(contexto, Permissao.COMPRA_APROVAR)
        atual = self._repositorio.fornecedor_por_documento(scope, documento)
        if atual:
            return atual
        agora = contexto.solicitado_em
        return self._repositorio.salvar_fornecedor(
            Fornecedor(fornecedor_id, scope, documento, nome, True, agora, agora)
        )

    def vincular_produto(
        self,
        *,
        contexto: ContextoExecucao,
        scope: ExecutionScope,
        fornecedor_id: str,
        codigo_fornecedor: str,
        insumo_id: str,
    ) -> VinculoProdutoFornecedor:
        _escopo(contexto, scope)
        _autorizar(contexto, Permissao.COMPRA_APROVAR)
        return self._repositorio.salvar_vinculo(
            VinculoProdutoFornecedor(
                scope,
                fornecedor_id,
                codigo_fornecedor,
                insumo_id,
                contexto.solicitado_em,
                contexto.usuario_id,
            )
        )

    def criar_pedido(
        self,
        *,
        contexto: ContextoExecucao,
        scope: ExecutionScope,
        pedido_id: str,
        fornecedor_id: str,
        itens: tuple[ItemPedidoCompra, ...],
        frete: Decimal,
        desconto: Decimal,
        total: Decimal,
    ) -> PedidoCompra:
        _escopo(contexto, scope)
        _autorizar(contexto, Permissao.COMPRA_APROVAR)
        agora = contexto.solicitado_em
        pedido = PedidoCompra(
            pedido_id,
            scope,
            fornecedor_id,
            itens,
            frete,
            desconto,
            total,
            StatusPedidoCompra.RASCUNHO,
            contexto.usuario_id,
            agora,
            agora,
        )
        return self._repositorio.salvar_pedido(pedido)

    def aprovar_pedido(
        self,
        *,
        contexto: ContextoExecucao,
        scope: ExecutionScope,
        pedido_id: str,
        versao_esperada: int,
    ) -> PedidoCompra:
        _escopo(contexto, scope)
        _autorizar(contexto, Permissao.COMPRA_APROVAR)
        pedido = self._repositorio.obter_pedido(scope, pedido_id)
        if pedido is None:
            raise EstadoProcurementInvalido("pedido_nao_encontrado")
        if pedido.status is StatusPedidoCompra.APROVADO:
            return pedido
        if pedido.status is not StatusPedidoCompra.RASCUNHO:
            raise EstadoProcurementInvalido("pedido_nao_pode_ser_aprovado")
        aprovado = replace(
            pedido,
            status=StatusPedidoCompra.APROVADO,
            atualizado_em=contexto.solicitado_em,
            versao=pedido.versao + 1,
        )
        return self._repositorio.salvar_pedido(
            aprovado, versao_esperada=versao_esperada
        )

    def receber(
        self,
        *,
        contexto: ContextoExecucao,
        scope: ExecutionScope,
        pedido_id: str,
        documento: FiscalInboundDocument,
        itens_recebidos: tuple[ItemRecebido, ...],
        idempotency_key: str,
        recebimento_id: str | None = None,
    ) -> ResultadoRecebimento:
        _escopo(contexto, scope)
        _autorizar(contexto, Permissao.FISCAL_COMPRAS_RECEBER)
        if documento.scope.partition_key != scope.partition_key:
            raise ProcurementForaDoEscopo("documento_fiscal_fora_do_escopo")

        def replay_idempotente(
            existente: RecebimentoCompra,
        ) -> ResultadoRecebimento:
            assinatura_atual = tuple(
                (
                    item.linha_pedido,
                    item.linha_fiscal,
                    item.insumo_id,
                    item.quantidade,
                    item.unidade_medida,
                    item.valor_unitario,
                    item.condicao_aceita,
                )
                for item in itens_recebidos
            )
            assinatura_existente = tuple(
                (
                    item.linha_pedido,
                    item.linha_fiscal,
                    item.insumo_id,
                    item.quantidade,
                    item.unidade_medida,
                    item.valor_unitario,
                    item.condicao_aceita,
                )
                for item in existente.itens
            )
            if (
                existente.pedido_id != pedido_id
                or existente.inbound_id != documento.inbound_id
                or assinatura_existente != assinatura_atual
            ):
                raise ConflitoProcurement("conflito_idempotencia_recebimento")
            return ResultadoRecebimento(existente, (), True)

        existente = self._repositorio.recebimento_por_idempotencia(
            scope, idempotency_key
        )
        if existente is not None:
            return replay_idempotente(existente)
        pedido = self._repositorio.obter_pedido(scope, pedido_id)
        if pedido is None or pedido.status not in {
            StatusPedidoCompra.APROVADO,
            StatusPedidoCompra.PARCIALMENTE_RECEBIDO,
        }:
            # Outro worker pode ter concluído o mesmo comando entre a consulta
            # idempotente e a leitura do pedido. Releia antes de rejeitar o estado.
            existente = self._repositorio.recebimento_por_idempotencia(
                scope, idempotency_key
            )
            if existente is not None:
                return replay_idempotente(existente)
            raise EstadoProcurementInvalido("pedido_nao_esta_aprovado")
        fornecedor = next(
            (
                f
                for f in (
                    self._repositorio.fornecedor_por_documento(
                        scope, documento.issuer_document.value
                    ),
                )
                if f is not None
            ),
            None,
        )
        divergencias: list[Divergencia] = []
        if fornecedor is None or fornecedor.fornecedor_id != pedido.fornecedor_id:
            divergencias.append(
                Divergencia(
                    TipoDivergencia.PRODUTO,
                    None,
                    pedido.fornecedor_id,
                    documento.issuer_document.value,
                )
            )
        pedido_por_linha = {item.linha: item for item in pedido.itens}
        fiscal_por_linha = {item.line_number: item for item in documento.items}
        vistos: set[int] = set()
        for recebido in itens_recebidos:
            item_pedido = pedido_por_linha.get(recebido.linha_pedido)
            item_fiscal = fiscal_por_linha.get(recebido.linha_fiscal)
            if item_pedido is None or item_fiscal is None:
                divergencias.append(
                    Divergencia(
                        TipoDivergencia.PRODUTO,
                        recebido.linha_pedido,
                        "linha_existente",
                        "linha_ausente",
                    )
                )
                continue
            if recebido.linha_pedido in vistos:
                divergencias.append(
                    Divergencia(
                        TipoDivergencia.PRODUTO,
                        recebido.linha_pedido,
                        "linha_unica",
                        "linha_repetida",
                    )
                )
            vistos.add(recebido.linha_pedido)
            vinculo = self._repositorio.resolver_vinculo(
                scope, pedido.fornecedor_id, item_fiscal.product_code
            )
            if (
                vinculo is None
                or vinculo.insumo_id != item_pedido.insumo_id
                or recebido.insumo_id != item_pedido.insumo_id
            ):
                divergencias.append(
                    Divergencia(
                        TipoDivergencia.PRODUTO,
                        recebido.linha_pedido,
                        item_pedido.insumo_id,
                        recebido.insumo_id,
                    )
                )
            if (
                recebido.unidade_medida != item_pedido.unidade_medida
                or recebido.unidade_medida != item_fiscal.commercial_unit
            ):
                divergencias.append(
                    Divergencia(
                        TipoDivergencia.UNIDADE,
                        recebido.linha_pedido,
                        item_pedido.unidade_medida,
                        recebido.unidade_medida,
                    )
                )
            if (
                recebido.valor_unitario != item_pedido.valor_unitario
                or recebido.valor_unitario != item_fiscal.unit_value
            ):
                divergencias.append(
                    Divergencia(
                        TipoDivergencia.PRECO,
                        recebido.linha_pedido,
                        str(item_pedido.valor_unitario),
                        str(recebido.valor_unitario),
                    )
                )
            ja_recebido = Decimal(
                str(
                    self._repositorio.quantidade_recebida(
                        scope, pedido_id, recebido.linha_pedido
                    )
                )
            )
            if (
                recebido.quantidade != item_fiscal.quantity
                or ja_recebido + recebido.quantidade > item_pedido.quantidade
            ):
                divergencias.append(
                    Divergencia(
                        TipoDivergencia.QUANTIDADE,
                        recebido.linha_pedido,
                        str(
                            min(
                                item_pedido.quantidade - ja_recebido,
                                item_fiscal.quantity,
                            )
                        ),
                        str(recebido.quantidade),
                    )
                )

        frete, desconto, total_fiscal = _totais_xml(documento)
        recebido_final = all(
            Decimal(
                str(self._repositorio.quantidade_recebida(scope, pedido_id, item.linha))
            )
            + sum(
                (
                    r.quantidade
                    for r in itens_recebidos
                    if r.linha_pedido == item.linha and r.condicao_aceita
                ),
                Decimal(0),
            )
            == item.quantidade
            for item in pedido.itens
        )
        if recebido_final:
            for tipo, esperado, encontrado in (
                (TipoDivergencia.FRETE, pedido.frete, frete),
                (TipoDivergencia.DESCONTO, pedido.desconto, desconto),
                (TipoDivergencia.TOTAL, pedido.total, total_fiscal),
            ):
                if esperado != encontrado:
                    divergencias.append(
                        Divergencia(tipo, None, str(esperado), str(encontrado))
                    )

        if any(not item.condicao_aceita for item in itens_recebidos):
            status = StatusRecebimento.REJEITADO
        elif divergencias:
            status = StatusRecebimento.DIVERGENTE
        elif recebido_final:
            status = StatusRecebimento.CONCLUIDO
        else:
            status = StatusRecebimento.PARCIAL
        recebimento = RecebimentoCompra(
            recebimento_id or str(uuid4()),
            scope,
            pedido_id,
            documento.inbound_id,
            documento.access_key.value,
            idempotency_key,
            itens_recebidos,
            tuple(divergencias),
            status,
            contexto.usuario_id,
            contexto.solicitado_em,
            metadata={
                "estoque_aplicavel": scope.environment is FiscalEnvironment.PRODUCTION
            },
        )

        def operacao() -> ResultadoRecebimento:
            try:
                salvo, criado = self._repositorio.salvar_recebimento(recebimento)
            except ConflitoProcurement:
                # O estado usado no matching pode ter mudado enquanto outro
                # worker concluía a mesma chave. A autoridade é o comando
                # original, validado novamente dentro da fronteira atômica.
                existente_concorrente = (
                    self._repositorio.recebimento_por_idempotencia(
                        scope, idempotency_key
                    )
                )
                if existente_concorrente is None:
                    raise
                return replay_idempotente(existente_concorrente)
            if not criado:
                return replay_idempotente(salvo)
            novo_status = (
                StatusPedidoCompra.CONCLUIDO
                if status is StatusRecebimento.CONCLUIDO
                else StatusPedidoCompra.PARCIALMENTE_RECEBIDO
                if status is StatusRecebimento.PARCIAL
                else pedido.status
            )
            if novo_status is not pedido.status:
                self._repositorio.salvar_pedido(
                    replace(
                        pedido,
                        status=novo_status,
                        atualizado_em=contexto.solicitado_em,
                        versao=pedido.versao + 1,
                    ),
                    versao_esperada=pedido.versao,
                )
            movimentos: list[ResultadoMovimento] = []
            if (
                status in {StatusRecebimento.PARCIAL, StatusRecebimento.CONCLUIDO}
                and scope.environment is FiscalEnvironment.PRODUCTION
            ):
                sistema = ContextoExecucao.sistema(
                    identidade="procurement",
                    motivo="entrada confirmada por recebimento físico",
                    tenant_id=scope.tenant_id,
                    unidade_id=scope.unit_id,
                    correlation_id=scope.correlation_id,
                    solicitado_em=contexto.solicitado_em,
                )
                agregados: dict[tuple[str, str, Decimal], Decimal] = {}
                for item in itens_recebidos:
                    if item.condicao_aceita:
                        chave = (
                            item.insumo_id,
                            item.unidade_medida,
                            item.valor_unitario,
                        )
                        agregados[chave] = (
                            agregados.get(chave, Decimal(0)) + item.quantidade
                        )
                for (insumo_id, unidade, custo), quantidade in sorted(
                    agregados.items()
                ):
                    movimentos.append(
                        registrar_movimento(
                            contexto=sistema,
                            repositorio=self._estoque,
                            insumo_id=insumo_id,
                            tipo=TipoMovimento.ENTRADA,
                            quantidade_movimento=quantidade,
                            unidade_medida=unidade,
                            origem_tipo="procurement_receipt",
                            origem_id=salvo.recebimento_id,
                            origem_versao=salvo.versao,
                            idempotency_key=f"proc:{scope.environment.value}:{salvo.recebimento_id}:{insumo_id}",
                            motivo="recebimento_fisico_confirmado",
                            metadata={
                                "pedido_id": pedido_id,
                                "access_key": documento.access_key.value,
                                "environment": scope.environment.value,
                            },
                        )
                    )
                    self._repositorio.registrar_custo(
                        CustoAquisicao(
                            scope,
                            insumo_id,
                            salvo.recebimento_id,
                            custo,
                            unidade,
                            "custo_unitario_documento_confirmado_v1",
                            contexto.usuario_id,
                            contexto.solicitado_em,
                        )
                    )
            evento_tipo = {
                StatusRecebimento.PARCIAL: "fiscal.recebimento.confirmado",
                StatusRecebimento.CONCLUIDO: "fiscal.recebimento.confirmado",
                StatusRecebimento.DIVERGENTE: "fiscal.divergencia.detectada",
                StatusRecebimento.REJEITADO: "fiscal.recebimento.rejeitado",
            }[status]
            evento = EnvelopeMensagem(
                EventoId(str(uuid4())),
                evento_tipo,
                salvo.recebimento_id,
                "procurement",
                TenantId(scope.tenant_id),
                UnidadeId(scope.unit_id),
                CorrelationId(scope.correlation_id),
                CausationId(contexto.causation_id) if contexto.causation_id else None,
                IdempotencyKey(idempotency_key),
                contexto.solicitado_em,
                {
                    "pedido_id": pedido_id,
                    "inbound_id": documento.inbound_id,
                    "status": status.value,
                    "divergencias": len(divergencias),
                },
                1,
            )
            papel = next(iter(sorted(contexto.papeis, key=str)), None)
            auditoria = EventoAuditoria(
                str(uuid4()),
                scope.tenant_id,
                scope.unit_id,
                contexto.usuario_id,
                papel,
                "fiscal.compras.receber",
                "recebimento_compra",
                salvo.recebimento_id,
                "sucesso" if not divergencias else "divergencia",
                status.value,
                scope.correlation_id,
                contexto.solicitado_em,
                contexto.origem,
                "procurement_v1",
                metadata=sanitizar_metadata(
                    {
                        "pedido_id": pedido_id,
                        "status": status.value,
                        "divergencias": len(divergencias),
                    }
                ),
            )
            return ResultadoRecebimento(
                salvo,
                tuple(movimentos),
                False,
                (evento,),
                (auditoria,),
            )

        return self._repositorio.atomicamente(operacao)

    def devolver_ao_fornecedor(
        self,
        *,
        contexto: ContextoExecucao,
        scope: ExecutionScope,
        recebimento_id: str,
        idempotency_key: str,
        motivo: str,
    ) -> tuple[ResultadoMovimento, ...]:
        """Devolve integralmente um recebimento aceito sem apagar seu histórico."""

        _escopo(contexto, scope)
        _autorizar(contexto, Permissao.FISCAL_COMPRAS_RECEBER)
        if scope.environment is not FiscalEnvironment.PRODUCTION:
            raise EstadoProcurementInvalido(
                "devolucao_estoque_exige_particao_production"
            )
        recebimento = self._repositorio.obter_recebimento(scope, recebimento_id)
        if recebimento is None or recebimento.status not in {
            StatusRecebimento.PARCIAL,
            StatusRecebimento.CONCLUIDO,
        }:
            raise EstadoProcurementInvalido("recebimento_nao_elegivel_para_devolucao")
        sistema = ContextoExecucao.sistema(
            identidade="procurement",
            motivo="devolucao ao fornecedor confirmada",
            tenant_id=scope.tenant_id,
            unidade_id=scope.unit_id,
            correlation_id=scope.correlation_id,
            solicitado_em=contexto.solicitado_em,
        )
        agregados: dict[tuple[str, str], Decimal] = {}
        for item in recebimento.itens:
            if item.condicao_aceita:
                chave = (item.insumo_id, item.unidade_medida)
                agregados[chave] = agregados.get(chave, Decimal(0)) + item.quantidade
        return tuple(
            registrar_movimento(
                contexto=sistema,
                repositorio=self._estoque,
                insumo_id=insumo_id,
                tipo=TipoMovimento.DEVOLUCAO_FORNECEDOR,
                quantidade_movimento=quantidade,
                unidade_medida=unidade,
                origem_tipo="procurement_return",
                origem_id=recebimento.recebimento_id,
                origem_versao=recebimento.versao,
                idempotency_key=f"{idempotency_key}:{insumo_id}",
                motivo=motivo,
                metadata={
                    "pedido_id": recebimento.pedido_id,
                    "access_key": recebimento.chave_acesso,
                    "environment": scope.environment.value,
                },
            )
            for (insumo_id, unidade), quantidade in sorted(agregados.items())
        )
