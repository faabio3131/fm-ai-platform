"""Adapters in-memory e runtime isolado do Delivery Próprio V1.

Somente testes usam este runtime. Nenhum banco real, gateway real, geocoder ou
serviço de entrega é acessado.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from threading import RLock

from core.dominio.enums import PagamentoStatus
from core.entrega.modelos import StatusEntrega
from core.pagamentos.modelos import MetodoPagamento

from .erros import ErroDelivery
from .modelos import (
    AreaEntrega,
    CarrinhoDelivery,
    CupomDelivery,
    EventoTracking,
    PagamentoDeliveryRef,
    PedidoDelivery,
    ProdutoDelivery,
    TipoCupom,
    moeda,
)
from .servicos import ServicoDelivery


class MemoriaCarrinhosDelivery:
    def __init__(self) -> None:
        self._lock = RLock()
        self._dados: dict[tuple[str, str, str], CarrinhoDelivery] = {}

    @staticmethod
    def _chave(
        tenant_id: str, unidade_id: str, carrinho_id: str
    ) -> tuple[str, str, str]:
        return tenant_id, unidade_id, carrinho_id

    def criar(self, carrinho: CarrinhoDelivery) -> CarrinhoDelivery:
        chave = self._chave(
            carrinho.tenant_id, carrinho.unidade_id, carrinho.carrinho_id
        )
        with self._lock:
            if chave in self._dados:
                raise ErroDelivery("carrinho_duplicado")
            self._dados[chave] = carrinho
            return carrinho

    def obter(
        self, *, tenant_id: str, unidade_id: str, carrinho_id: str
    ) -> CarrinhoDelivery | None:
        with self._lock:
            return self._dados.get(self._chave(tenant_id, unidade_id, carrinho_id))

    def salvar_cas(
        self, carrinho: CarrinhoDelivery, *, expected_version: int
    ) -> CarrinhoDelivery:
        chave = self._chave(
            carrinho.tenant_id, carrinho.unidade_id, carrinho.carrinho_id
        )
        with self._lock:
            atual = self._dados.get(chave)
            if atual is None:
                raise ErroDelivery("recurso_indisponivel")
            if atual.versao != expected_version:
                raise ErroDelivery("conflito_concorrencia")
            if carrinho.versao != expected_version + 1:
                raise ErroDelivery("incremento_versao_invalido")
            self._dados[chave] = carrinho
            return carrinho


class MemoriaPedidosDelivery:
    def __init__(self) -> None:
        self._lock = RLock()
        self._dados: dict[tuple[str, str, str], PedidoDelivery] = {}
        self._idempotencia_registro: dict[str, tuple[str, str, str]] = {}
        self._idempotencia_cancelamento: set[str] = set()

    @staticmethod
    def _chave(pedido: PedidoDelivery) -> tuple[str, str, str]:
        return pedido.tenant_id, pedido.unidade_id, pedido.pedido_id

    def registrar(
        self, *, pedido: PedidoDelivery, idempotency_key: str
    ) -> tuple[PedidoDelivery, bool]:
        with self._lock:
            existente_chave = self._idempotencia_registro.get(idempotency_key)
            if existente_chave is not None:
                return self._dados[existente_chave], True
            chave = self._chave(pedido)
            if chave in self._dados:
                raise ErroDelivery("pedido_duplicado")
            self._dados[chave] = pedido
            self._idempotencia_registro[idempotency_key] = chave
            return pedido, False

    def obter(
        self, *, tenant_id: str, unidade_id: str, pedido_id: str
    ) -> PedidoDelivery | None:
        with self._lock:
            return self._dados.get((tenant_id, unidade_id, pedido_id))

    def cancelar(
        self, *, pedido: PedidoDelivery, idempotency_key: str
    ) -> tuple[PedidoDelivery, bool]:
        chave = self._chave(pedido)
        with self._lock:
            if idempotency_key in self._idempotencia_cancelamento:
                atual = self._dados.get(chave)
                if atual is None:
                    raise ErroDelivery("pedido_cancelado_inconsistente")
                return atual, True
            if chave not in self._dados:
                raise ErroDelivery("recurso_indisponivel")
            self._dados[chave] = pedido
            self._idempotencia_cancelamento.add(idempotency_key)
            return pedido, False


class MemoriaPromocoesDelivery:
    def __init__(self) -> None:
        self._lock = RLock()
        self._cupom_reservas: dict[str, tuple[str, str, str, str, Decimal]] = {}
        self._cashback_reservas: dict[str, tuple[str, str, str, str, Decimal]] = {}
        self._saldos_cashback: dict[tuple[str, str, str], Decimal] = {}
        self._confirmados: dict[str, str] = {}

    def definir_saldo_cashback(
        self, *, tenant_id: str, unidade_id: str, cliente_ref: str, saldo: Decimal
    ) -> None:
        with self._lock:
            self._saldos_cashback[(tenant_id, unidade_id, cliente_ref)] = moeda(saldo)

    def saldo_cashback(
        self, *, tenant_id: str, unidade_id: str, cliente_ref: str
    ) -> Decimal:
        with self._lock:
            return self._saldos_cashback.get(
                (tenant_id, unidade_id, cliente_ref), Decimal("0.00")
            )

    def reservar_cupom(
        self,
        *,
        cupom: CupomDelivery,
        cliente_ref: str,
        carrinho_id: str,
        desconto: str,
        idempotency_key: str,
    ) -> str:
        with self._lock:
            existente = self._cupom_reservas.get(idempotency_key)
            if existente is not None:
                return str(existente[4])
            ativas = list(self._cupom_reservas.values())
            total_codigo = sum(1 for r in ativas if r[2] == cupom.codigo)
            total_cliente = sum(
                1 for r in ativas if r[2] == cupom.codigo and r[3] == cliente_ref
            )
            if cupom.limite_total is not None and total_codigo >= cupom.limite_total:
                raise ErroDelivery("cupom_esgotado")
            if cupom.limite_cliente is not None and total_cliente >= cupom.limite_cliente:
                raise ErroDelivery("limite_cupom_cliente")
            valor = moeda(desconto)
            self._cupom_reservas[idempotency_key] = (
                cupom.tenant_id,
                cupom.unidade_id,
                cupom.codigo,
                cliente_ref,
                valor,
            )
            return str(valor)

    def reservar_cashback(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        cliente_ref: str,
        carrinho_id: str,
        valor_maximo: str,
        idempotency_key: str,
    ) -> str:
        with self._lock:
            existente = self._cashback_reservas.get(idempotency_key)
            if existente is not None:
                return str(existente[4])
            chave_saldo = (tenant_id, unidade_id, cliente_ref)
            saldo = self._saldos_cashback.get(chave_saldo, Decimal("0.00"))
            reservado = min(saldo, moeda(valor_maximo))
            self._saldos_cashback[chave_saldo] = moeda(saldo - reservado)
            self._cashback_reservas[idempotency_key] = (
                tenant_id,
                unidade_id,
                carrinho_id,
                cliente_ref,
                reservado,
            )
            return str(reservado)

    def validar_reservas(self, carrinho: CarrinhoDelivery) -> None:
        with self._lock:
            if carrinho.cupom_codigo:
                chave = f"delivery:cupom:{carrinho.carrinho_id}:{carrinho.cupom_codigo}"
                reserva = self._cupom_reservas.get(chave)
                if reserva is None or reserva[4] != carrinho.desconto_cupom:
                    raise ErroDelivery("reserva_cupom_ausente")
            if carrinho.cashback_reservado > 0:
                chave = f"delivery:cashback:{carrinho.carrinho_id}"
                reserva = self._cashback_reservas.get(chave)
                if reserva is None or reserva[4] != carrinho.cashback_reservado:
                    raise ErroDelivery("reserva_cashback_ausente")

    def confirmar_reservas(
        self, *, carrinho: CarrinhoDelivery, pedido_id: str
    ) -> None:
        with self._lock:
            self.validar_reservas(carrinho)
            self._confirmados[pedido_id] = carrinho.carrinho_id

    def estornar_reservas(
        self, *, carrinho: CarrinhoDelivery, pedido_id: str
    ) -> tuple[str, bool]:
        with self._lock:
            restaurado = Decimal("0.00")
            cashback_key = f"delivery:cashback:{carrinho.carrinho_id}"
            cashback = self._cashback_reservas.pop(cashback_key, None)
            if cashback is not None:
                tenant_id, unidade_id, _, cliente_ref, valor = cashback
                chave = (tenant_id, unidade_id, cliente_ref)
                self._saldos_cashback[chave] = moeda(
                    self._saldos_cashback.get(chave, Decimal("0.00")) + valor
                )
                restaurado = valor
            cupom_liberado = False
            if carrinho.cupom_codigo:
                cupom_key = f"delivery:cupom:{carrinho.carrinho_id}:{carrinho.cupom_codigo}"
                cupom_liberado = self._cupom_reservas.pop(cupom_key, None) is not None
            self._confirmados.pop(pedido_id, None)
            return str(restaurado), cupom_liberado


class MemoriaPagamentosDelivery:
    def __init__(self) -> None:
        self._lock = RLock()
        self._por_pedido: dict[tuple[str, str, str], PagamentoDeliveryRef] = {}
        self._idempotencia: dict[str, PagamentoDeliveryRef] = {}
        self._cancelamentos: dict[str, PagamentoStatus] = {}

    def criar_obrigacao(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        pedido_id: str,
        valor: str,
        metodo: MetodoPagamento,
        idempotency_key: str,
    ) -> PagamentoDeliveryRef:
        del valor
        with self._lock:
            existente = self._idempotencia.get(idempotency_key)
            if existente is not None:
                return existente
            status = (
                PagamentoStatus.AGUARDANDO_ENTREGA
                if metodo is MetodoPagamento.PAGAMENTO_NA_ENTREGA
                else PagamentoStatus.PENDENTE
            )
            ref = PagamentoDeliveryRef(
                pagamento_id=f"pay_{len(self._por_pedido) + 1:04d}",
                status=status,
                metodo=metodo,
            )
            self._por_pedido[(tenant_id, unidade_id, pedido_id)] = ref
            self._idempotencia[idempotency_key] = ref
            return ref

    def consultar(
        self, *, tenant_id: str, unidade_id: str, pedido_id: str
    ) -> PagamentoDeliveryRef:
        with self._lock:
            ref = self._por_pedido.get((tenant_id, unidade_id, pedido_id))
            if ref is None:
                raise ErroDelivery("pagamento_indisponivel")
            return ref

    def marcar_pago(
        self, *, tenant_id: str, unidade_id: str, pedido_id: str
    ) -> PagamentoDeliveryRef:
        with self._lock:
            chave = (tenant_id, unidade_id, pedido_id)
            atual = self._por_pedido.get(chave)
            if atual is None:
                raise ErroDelivery("pagamento_indisponivel")
            novo = replace(atual, status=PagamentoStatus.PAGO)
            self._por_pedido[chave] = novo
            return novo

    def cancelar_ou_estornar(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        pedido_id: str,
        valor: str,
        idempotency_key: str,
    ) -> PagamentoStatus:
        del valor
        with self._lock:
            existente = self._cancelamentos.get(idempotency_key)
            if existente is not None:
                return existente
            chave = (tenant_id, unidade_id, pedido_id)
            atual = self._por_pedido.get(chave)
            if atual is None:
                raise ErroDelivery("pagamento_indisponivel")
            status = (
                PagamentoStatus.ESTORNADO
                if atual.status is PagamentoStatus.PAGO
                else PagamentoStatus.CANCELADO
            )
            self._por_pedido[chave] = replace(atual, status=status)
            self._cancelamentos[idempotency_key] = status
            return status


class MemoriaEntregasDelivery:
    _TRANSICOES = {
        StatusEntrega.AGUARDANDO_PRODUCAO: {StatusEntrega.AGUARDANDO_EXPEDICAO},
        StatusEntrega.AGUARDANDO_EXPEDICAO: {
            StatusEntrega.AGUARDANDO_ENTREGADOR,
            StatusEntrega.ATRIBUIDA,
        },
        StatusEntrega.AGUARDANDO_ENTREGADOR: {StatusEntrega.ATRIBUIDA},
        StatusEntrega.ATRIBUIDA: {StatusEntrega.COLETADA},
        StatusEntrega.COLETADA: {StatusEntrega.EM_ROTA},
        StatusEntrega.EM_ROTA: {
            StatusEntrega.ENTREGUE,
            StatusEntrega.TENTATIVA_FALHOU,
        },
        StatusEntrega.TENTATIVA_FALHOU: {
            StatusEntrega.AGUARDANDO_ENTREGADOR,
            StatusEntrega.ATRIBUIDA,
        },
    }

    def __init__(self) -> None:
        self._lock = RLock()
        self._pedido_para_entrega: dict[tuple[str, str, str], str] = {}
        self._escopo_entrega: dict[str, tuple[str, str]] = {}
        self._timeline: dict[str, list[EventoTracking]] = {}
        self._idempotencia: dict[str, str] = {}
        self._cancelamentos: set[str] = set()

    def criar(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        pedido_id: str,
        endereco_id: str,
        idempotency_key: str,
    ) -> str:
        del endereco_id
        with self._lock:
            existente = self._idempotencia.get(idempotency_key)
            if existente is not None:
                return existente
            entrega_id = f"ent_{len(self._timeline) + 1:04d}"
            self._pedido_para_entrega[(tenant_id, unidade_id, pedido_id)] = entrega_id
            self._escopo_entrega[entrega_id] = (tenant_id, unidade_id)
            self._timeline[entrega_id] = [
                EventoTracking(
                    entrega_id=entrega_id,
                    status=StatusEntrega.AGUARDANDO_PRODUCAO,
                    mensagem="Pedido confirmado e aguardando produção.",
                    ocorrido_em=datetime.now(timezone.utc),
                )
            ]
            self._idempotencia[idempotency_key] = entrega_id
            return entrega_id

    def timeline(
        self, *, tenant_id: str, unidade_id: str, entrega_id: str
    ) -> tuple[EventoTracking, ...]:
        with self._lock:
            if self._escopo_entrega.get(entrega_id) != (tenant_id, unidade_id):
                raise ErroDelivery("recurso_indisponivel")
            return tuple(self._timeline[entrega_id])

    def avancar(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        entrega_id: str,
        status: StatusEntrega,
        mensagem: str,
    ) -> None:
        with self._lock:
            if self._escopo_entrega.get(entrega_id) != (tenant_id, unidade_id):
                raise ErroDelivery("recurso_indisponivel")
            atual = self._timeline[entrega_id][-1].status
            if status not in self._TRANSICOES.get(atual, set()):
                raise ErroDelivery("transicao_entrega_invalida")
            self._timeline[entrega_id].append(
                EventoTracking(
                    entrega_id=entrega_id,
                    status=status,
                    mensagem=mensagem,
                    ocorrido_em=datetime.now(timezone.utc),
                )
            )

    def cancelar(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        entrega_id: str,
        motivo: str,
        idempotency_key: str,
    ) -> bool:
        with self._lock:
            if idempotency_key in self._cancelamentos:
                return True
            if self._escopo_entrega.get(entrega_id) != (tenant_id, unidade_id):
                raise ErroDelivery("recurso_indisponivel")
            atual = self._timeline[entrega_id][-1].status
            if atual is StatusEntrega.ENTREGUE:
                raise ErroDelivery("pedido_entregue_nao_cancelavel")
            self._timeline[entrega_id].append(
                EventoTracking(
                    entrega_id=entrega_id,
                    status=StatusEntrega.CANCELADA,
                    mensagem=f"Entrega cancelada: {motivo.strip()}",
                    ocorrido_em=datetime.now(timezone.utc),
                )
            )
            self._cancelamentos.add(idempotency_key)
            return True


class RuntimeDeliveryTeste:
    def __init__(self) -> None:
        self.carrinhos = MemoriaCarrinhosDelivery()
        self.pedidos = MemoriaPedidosDelivery()
        self.pagamentos = MemoriaPagamentosDelivery()
        self.entregas = MemoriaEntregasDelivery()
        self.promocoes = MemoriaPromocoesDelivery()
        self.servico = ServicoDelivery(
            carrinhos=self.carrinhos,
            pedidos=self.pedidos,
            pagamentos=self.pagamentos,
            entregas=self.entregas,
            promocoes=self.promocoes,
        )
        agora = datetime.now(timezone.utc)
        self.catalogo = (
            ProdutoDelivery(
                produto_id="burger-teste",
                tenant_id="tenant-demo",
                unidade_id="unidade-demo",
                nome="Burger Delivery",
                preco=Decimal("32.00"),
                estoque_disponivel=Decimal("20"),
                custo_estimado=Decimal("12.00"),
            ),
            ProdutoDelivery(
                produto_id="batata-teste",
                tenant_id="tenant-demo",
                unidade_id="unidade-demo",
                nome="Batata Crocante",
                preco=Decimal("15.00"),
                estoque_disponivel=Decimal("30"),
                custo_estimado=Decimal("5.00"),
            ),
        )
        self.areas = (
            AreaEntrega(
                area_id="area-centro",
                tenant_id="tenant-demo",
                unidade_id="unidade-demo",
                nome="Centro",
                prefixos_cep=("010", "011"),
                taxa=Decimal("7.00"),
                sla_minutos=30,
                sla_maxutos=45,
                versao=1,
            ),
        )
        self.cupons = (
            CupomDelivery(
                codigo="BEMVINDO10",
                tenant_id="tenant-demo",
                unidade_id="unidade-demo",
                tipo=TipoCupom.PERCENTUAL,
                valor=Decimal("10"),
                minimo_pedido=Decimal("20"),
                inicio=agora - timedelta(days=1),
                fim=agora + timedelta(days=30),
                limite_total=100,
                limite_cliente=2,
            ),
        )
        self.promocoes.definir_saldo_cashback(
            tenant_id="tenant-demo",
            unidade_id="unidade-demo",
            cliente_ref="cliente-demo",
            saldo=Decimal("20.00"),
        )
