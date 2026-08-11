"""Runtime in-memory do PR17; não acessa marketplace ou banco reais."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from core.dominio.tempo import SystemClock
from core.eventos.observabilidade import ColetorMetricasEmMemoria
from core.eventos.repositorios import (
    RepositorioDLQEmMemoria,
    RepositorioInboxEmMemoria,
    RepositorioOutboxEmMemoria,
)

from .adapters import RegistroAdaptersMarketplace
from .erros import ErroMarketplaceTransitorio
from .ifood_sandbox import IFOOD_CAPACIDADES, IfoodSandboxAdapter, IfoodSandboxTransport
from .modelos import (
    IntegracaoMarketplace,
    PedidoExterno,
    PedidoMarketplaceSnapshot,
    PlataformaMarketplace,
    StatusIntegracao,
    StatusPedidoExterno,
)
from .repositorios import (
    RepositorioIntegracoesMarketplaceEmMemoria,
    RepositorioPedidosExternosEmMemoria,
)
from .retry import PoliticaRetryMarketplace
from .servicos import ServicoMarketplaces


@dataclass
class PedidoInternoSandbox:
    pedido_id: str
    tenant_id: str
    unidade_id: str
    integracao_id: str
    id_externo: str
    status: str


class PedidosInternosSandbox:
    def __init__(self) -> None:
        self.dados: dict[tuple[str, str, str, str], PedidoInternoSandbox] = {}
        self.falhas_criacao_restantes = 0
        self.atualizacoes: list[tuple[str, StatusPedidoExterno, str]] = []

    def criar_ou_obter(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        integracao_id: str,
        snapshot: PedidoMarketplaceSnapshot,
        idempotency_key: str,
    ) -> tuple[str, bool]:
        del idempotency_key
        if self.falhas_criacao_restantes > 0:
            self.falhas_criacao_restantes -= 1
            raise ErroMarketplaceTransitorio("pedido_interno_indisponivel")
        chave = (tenant_id, unidade_id, integracao_id, snapshot.id_externo)
        existente = self.dados.get(chave)
        if existente is not None:
            return existente.pedido_id, True
        pedido_id = f"ped-mkt-{len(self.dados) + 1:04d}"
        self.dados[chave] = PedidoInternoSandbox(
            pedido_id=pedido_id,
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            integracao_id=integracao_id,
            id_externo=snapshot.id_externo,
            status=snapshot.status.value,
        )
        return pedido_id, False

    def atualizar_status_marketplace(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        pedido_id: str,
        status: StatusPedidoExterno,
        idempotency_key: str,
    ) -> str:
        del tenant_id, unidade_id
        self.atualizacoes.append((pedido_id, status, idempotency_key))
        return status.value

    def reconciliar_marketplace(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        pedido: PedidoExterno,
        snapshot: PedidoMarketplaceSnapshot,
        idempotency_key: str,
    ) -> str:
        del tenant_id, unidade_id
        self.atualizacoes.append((pedido.pedido_id, snapshot.status, idempotency_key))
        return snapshot.status.value


class RuntimeMarketplaceTeste:
    def __init__(self) -> None:
        self.integracoes = RepositorioIntegracoesMarketplaceEmMemoria()
        self.pedidos_externos = RepositorioPedidosExternosEmMemoria()
        self.pedidos_internos = PedidosInternosSandbox()
        self.inbox = RepositorioInboxEmMemoria()
        self.outbox = RepositorioOutboxEmMemoria()
        self.dlq = RepositorioDLQEmMemoria()
        self.metricas = ColetorMetricasEmMemoria()
        self.transport = IfoodSandboxTransport()
        self.adapter_ifood = IfoodSandboxAdapter(self.transport)
        self.adapters = RegistroAdaptersMarketplace()
        self.adapters.registrar(self.adapter_ifood)
        self.integracao = IntegracaoMarketplace(
            integracao_id="integracao-ifood-demo",
            tenant_id="tenant-demo",
            unidade_id="unidade-demo",
            plataforma=PlataformaMarketplace.IFOOD,
            conta_externa="merchant-demo",
            segredo_ref="vault://ifood/demo",
            capacidades=IFOOD_CAPACIDADES,
            status=StatusIntegracao.ATIVA,
        )
        self.integracoes.adicionar(self.integracao)
        self.servico = ServicoMarketplaces(
            integracoes=self.integracoes,
            pedidos_externos=self.pedidos_externos,
            pedidos_internos=self.pedidos_internos,
            adapters=self.adapters,
            inbox=self.inbox,
            outbox=self.outbox,
            dlq=self.dlq,
            metricas=self.metricas,
            clock=SystemClock(),
            retry=PoliticaRetryMarketplace(
                max_attempts=3,
                backoff_base_seconds=0,
                backoff_max_seconds=0,
            ),
        )
        self.criado_em = datetime.now(timezone.utc)
