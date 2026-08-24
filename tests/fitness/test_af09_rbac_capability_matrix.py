from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from inspect import signature

import pytest

import application.checkout as checkout_module
from application.checkout import CheckoutInvalido, ComandoCheckoutV1
from core.assistente_atendimento.atendimento_modelos import (
    CarrinhoAtendimento,
    ItemCarrinhoAtendimento,
)
from core.assistente_atendimento.checkout_adapter import CheckoutAssistenteV1
from core.dominio.dinheiro import Dinheiro
from core.dominio.enums import CanalAtendimento, OrigemPedido, PedidoStatus
from core.dominio.erros import PermissaoNegada
from core.dominio.ids import (
    CorrelationId,
    IdempotencyKey,
    PedidoId,
    PedidoItemId,
    ProdutoId,
    TenantId,
    UnidadeId,
)
from core.dominio.pedidos import ItemPedido, Pedido
from core.dominio.tipos import QuantidadeItem
from core.estados.maquinas import ErroTransicao
from core.estoque.modelos import ItemSnapshotFicha, SnapshotFichaEstoque, TipoMovimento
from core.estoque.repositorios import RepositorioEstoqueEmMemoria
from core.estoque.servicos import registrar_movimento
from core.eventos.modelos import EnvelopeMensagem
from core.pagamentos.erros import OperacaoPagamentoNaoAutorizada
from core.pagamentos.modelos import MetodoPagamento
from core.pagamentos.repositorios import RepositorioPagamentosEmMemoria
from core.pagamentos.servicos import criar_obrigacao_pagamento
from core.pdv.cutover_canonico import contexto_estoque_automatico_pdv
from core.pedidos.servicos import registrar_novo_pedido, transicionar_pedido
from core.seguranca.auditoria import RepositorioAuditoriaEmMemoria
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import MATRIZ_PADRAO, Papel, Permissao

_NOW = datetime(2026, 8, 23, 18, 30, tzinfo=timezone.utc)
_TENANT = "tenant-af09"
_UNIT = "unidade-af09"
_OTHER_TENANT = "tenant-af09-outro"
_OTHER_UNIT = "unidade-af09-outra"


class _RepositorioPedidosEmMemoria:
    def __init__(self) -> None:
        self._pedidos: dict[tuple[str, str, str], Pedido] = {}
        self.eventos: list[object] = []

    @staticmethod
    def _key(
        tenant_id: object, unidade_id: object, pedido_id: object
    ) -> tuple[str, str, str]:
        return str(tenant_id), str(unidade_id), str(pedido_id)

    def buscar(self, tenant_id, unidade_id, pedido_id) -> Pedido | None:
        return self._pedidos.get(self._key(tenant_id, unidade_id, pedido_id))

    def listar(self, tenant_id, unidade_id) -> tuple[Pedido, ...]:
        return tuple(
            pedido
            for (tenant, unidade, _), pedido in self._pedidos.items()
            if tenant == str(tenant_id) and unidade == str(unidade_id)
        )

    def buscar_por_idempotencia(self, tenant_id, unidade_id, chave) -> Pedido | None:
        return next(
            (
                pedido
                for pedido in self.listar(tenant_id, unidade_id)
                if pedido.idempotency_key == chave
            ),
            None,
        )

    def obter_versao(self, tenant_id, unidade_id, pedido_id) -> int | None:
        pedido = self.buscar(tenant_id, unidade_id, pedido_id)
        return pedido.versao if pedido is not None else None

    def salvar(self, pedido: Pedido, *, versao_esperada: int | None = None) -> Pedido:
        key = self._key(pedido.tenant_id, pedido.unidade_id, pedido.id)
        atual = self._pedidos.get(key)
        if versao_esperada is not None:
            assert atual is not None and atual.versao == versao_esperada
        self._pedidos[key] = pedido
        return pedido

    def salvar_eventos(self, tenant_id, unidade_id, pedido_id, eventos) -> None:
        assert self.buscar(tenant_id, unidade_id, pedido_id) is not None
        self.eventos.extend(eventos)

    @property
    def quantidade(self) -> int:
        return len(self._pedidos)


class _OutboxEmMemoria:
    def __init__(self) -> None:
        self.mensagens: list[EnvelopeMensagem] = []

    def adicionar(self, mensagem: EnvelopeMensagem) -> None:
        self.mensagens.append(mensagem)

    def consultar(
        self,
        *,
        tenant_id=None,
        unidade_id=None,
        event_id=None,
        idempotency_key=None,
    ) -> EnvelopeMensagem | None:
        return next(
            (
                mensagem
                for mensagem in self.mensagens
                if (tenant_id is None or mensagem.tenant_id == tenant_id)
                and (unidade_id is None or mensagem.unidade_id == unidade_id)
                and (event_id is None or mensagem.event_id == event_id)
                and (
                    idempotency_key is None
                    or mensagem.idempotency_key == idempotency_key
                )
            ),
            None,
        )


class _RecursosEmMemoria:
    def __init__(self) -> None:
        self.pedidos = _RepositorioPedidosEmMemoria()
        self.pagamentos = RepositorioPagamentosEmMemoria()
        self.estoque = RepositorioEstoqueEmMemoria()
        self.outbox = _OutboxEmMemoria()
        self.auditoria = RepositorioAuditoriaEmMemoria()

    def registrar_efeitos(self, *, eventos=(), auditorias=()) -> None:
        for evento in eventos:
            self.outbox.adicionar(evento)
        for evento in auditorias:
            self.auditoria.adicionar(evento)


def _contexto(
    permissoes: frozenset[Permissao],
    *,
    papel: Papel = Papel.ATENDIMENTO,
    tenant_id: str = _TENANT,
    unidade_id: str = _UNIT,
    usuario_id: str = "ator-af09",
) -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id=tenant_id,
        unidade_id=unidade_id,
        usuario_id=usuario_id,
        papeis=frozenset({papel}),
        permissoes=permissoes,
        correlation_id="corr-af09",
        solicitado_em=_NOW,
        origem="fitness.af09",
        unidades_permitidas=frozenset({unidade_id, _OTHER_UNIT}),
    )


def _pedido(
    sufixo: str,
    *,
    tenant_id: str = _TENANT,
    unidade_id: str = _UNIT,
    total: str = "30.00",
) -> Pedido:
    tenant = TenantId(tenant_id)
    unidade = UnidadeId(unidade_id)
    item = ItemPedido(
        id=PedidoItemId(f"item-{sufixo}"),
        tenant_id=tenant,
        unidade_id=unidade,
        produto_id=ProdutoId("produto-af09"),
        nome_produto="Produto AF-09",
        quantidade=QuantidadeItem(1),
        preco_unitario=Dinheiro(total),
        subtotal=Dinheiro(total),
    )
    return Pedido.novo(
        id=PedidoId(f"pedido-{sufixo}"),
        tenant_id=tenant,
        unidade_id=unidade,
        origem=OrigemPedido.WHATSAPP,
        canal=CanalAtendimento.WHATSAPP,
        status=PedidoStatus.RASCUNHO,
        cliente_id=None,
        criado_em=_NOW,
        atualizado_em=_NOW,
        versao=1,
        correlation_id=CorrelationId("corr-af09"),
        idempotency_key=IdempotencyKey(f"af09:{sufixo}"),
        subtotal=Dinheiro(total),
        descontos=Dinheiro("0"),
        taxas=Dinheiro("0"),
        total=Dinheiro(total),
        itens=(item,),
    )


def _comando(pedido: Pedido, *, com_estoque: bool = False) -> ComandoCheckoutV1:
    snapshot = None
    if com_estoque:
        snapshot = SnapshotFichaEstoque(
            pedido_id=str(pedido.id),
            versao_ficha="af09-v1",
            capturado_em=_NOW,
            itens=(
                ItemSnapshotFicha(
                    produto_id="produto-af09",
                    item_pedido_id=str(pedido.itens[0].id),
                    insumo_id="insumo-af09",
                    quantidade_por_unidade=Decimal(1),
                    quantidade_total=Decimal(1),
                    unidade_medida="un",
                ),
            ),
        )
    return ComandoCheckoutV1(
        pedido=pedido,
        timestamp=_NOW,
        pagamento_id=f"pagamento-{pedido.id}",
        metodo_pagamento=MetodoPagamento.PAGAMENTO_NA_ENTREGA,
        snapshot_estoque=snapshot,
        recebimento_posterior=True,
    )


def _registrar(
    pedido: Pedido,
    contexto: ContextoExecucao,
    recursos: _RecursosEmMemoria,
):
    return registrar_novo_pedido(
        pedido=pedido,
        contexto=contexto,
        repositorio=recursos.pedidos,
        outbox=recursos.outbox,
        auditoria=recursos.auditoria,
    )


def _transicionar(
    pedido: Pedido,
    contexto: ContextoExecucao,
    recursos: _RecursosEmMemoria,
):
    return transicionar_pedido(
        tenant_id=pedido.tenant_id,
        unidade_id=pedido.unidade_id,
        pedido_id=pedido.id,
        destino=PedidoStatus.AGUARDANDO_CONFIRMACAO,
        versao_esperada=pedido.versao,
        idempotency_key=IdempotencyKey(f"{pedido.idempotency_key}:transicao"),
        contexto=contexto,
        repositorio=recursos.pedidos,
        outbox=recursos.outbox,
        auditoria=recursos.auditoria,
        timestamp=_NOW,
        precondicoes={"itens_validos": True, "precos_calculados": True},
    )


def test_af09_a_creator_only_can_create_order() -> None:
    recursos = _RecursosEmMemoria()
    resultado = _registrar(
        _pedido("a"),
        _contexto(frozenset({Permissao.PEDIDO_CRIAR})),
        recursos,
    )

    assert recursos.pedidos.quantidade == 1
    assert resultado.auditoria is not None
    assert resultado.auditoria.politica == "rbac_pedido_criar"


def test_af09_b_alter_only_cannot_create_order() -> None:
    recursos = _RecursosEmMemoria()

    with pytest.raises(PermissaoNegada, match="permissao_insuficiente"):
        _registrar(
            _pedido("b"),
            _contexto(frozenset({Permissao.PEDIDO_ALTERAR})),
            recursos,
        )

    assert recursos.pedidos.quantidade == 0
    assert recursos.outbox.mensagens == []
    assert recursos.auditoria.eventos == []


def test_af09_c_create_only_cannot_alter_order() -> None:
    recursos = _RecursosEmMemoria()
    contexto = _contexto(frozenset({Permissao.PEDIDO_CRIAR}))
    pedido = _pedido("c")
    _registrar(pedido, contexto, recursos)

    with pytest.raises(ErroTransicao) as erro:
        _transicionar(pedido, contexto, recursos)

    assert erro.value.codigo == "permissao_insuficiente"
    persistido = recursos.pedidos.buscar(
        pedido.tenant_id, pedido.unidade_id, pedido.id
    )
    assert persistido is not None
    assert persistido.status is PedidoStatus.RASCUNHO
    assert len(recursos.outbox.mensagens) == 1


def test_af09_d_alter_permission_allows_legitimate_transition() -> None:
    recursos = _RecursosEmMemoria()
    pedido = _pedido("d")
    _registrar(
        pedido,
        _contexto(frozenset({Permissao.PEDIDO_CRIAR})),
        recursos,
    )

    resultado = _transicionar(
        pedido,
        _contexto(frozenset({Permissao.PEDIDO_ALTERAR})),
        recursos,
    )

    assert resultado.pedido.status is PedidoStatus.AGUARDANDO_CONFIRMACAO


def test_af09_e_atendimento_uses_canonical_checkout_without_broad_permissions() -> None:
    recursos = _RecursosEmMemoria()
    contexto = _contexto(MATRIZ_PADRAO[Papel.ATENDIMENTO])

    assert Permissao.PEDIDO_ALTERAR not in contexto.permissoes
    assert Permissao.PAGAMENTO_REGISTRAR not in contexto.permissoes

    resultado = checkout_module.executar_checkout_em_transacao(
        comando=_comando(_pedido("e")),
        contexto=contexto,
        recursos=recursos,
    )

    assert (
        resultado.aguardando_confirmacao.pedido.status
        is PedidoStatus.AGUARDANDO_CONFIRMACAO
    )
    assert resultado.pagamento is not None
    assert resultado.pagamento.pagamento.tenant_id == _TENANT
    assert resultado.pagamento.pagamento.unidade_id == _UNIT


def test_af09_f_create_permission_does_not_authorize_arbitrary_payment() -> None:
    repositorio = RepositorioPagamentosEmMemoria()
    contexto = _contexto(frozenset({Permissao.PEDIDO_CRIAR}))

    with pytest.raises(OperacaoPagamentoNaoAutorizada, match="permissao_insuficiente"):
        criar_obrigacao_pagamento(
            contexto=contexto,
            repositorio=repositorio,
            pagamento_id="pagamento-af09-f",
            pedido_id="pedido-af09-f",
            valor_previsto=Dinheiro("30"),
            metodo=MetodoPagamento.PIX,
            idempotency_key="af09-f",
            timestamp=_NOW,
        )

    assert repositorio.buscar_pagamento(_TENANT, _UNIT, "pagamento-af09-f") is None


def test_af09_g_checkout_derives_narrow_internal_authority_per_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recursos = _RecursosEmMemoria()
    contexto = _contexto(frozenset({Permissao.PEDIDO_CRIAR}))
    pedido = _pedido("g")
    capturados: dict[str, ContextoExecucao] = {}

    seed = registrar_movimento(
        contexto=_contexto(frozenset({Permissao.ESTOQUE_AJUSTAR})),
        repositorio=recursos.estoque,
        insumo_id="insumo-af09",
        tipo=TipoMovimento.ENTRADA,
        quantidade_movimento="5",
        unidade_medida="un",
        origem_tipo="fitness",
        origem_id="seed-af09",
        origem_versao=1,
        idempotency_key="seed-af09",
        motivo="seed controlado AF-09",
    )
    assert seed.movimentos

    original_criar = checkout_module.registrar_novo_pedido
    original_pagamento = checkout_module.criar_obrigacao_pagamento
    original_estoque = checkout_module.reservar_estoque
    original_transicao = checkout_module.transicionar_pedido

    def criar(**kwargs):
        capturados["criar"] = kwargs["contexto"]
        return original_criar(**kwargs)

    def pagamento(**kwargs):
        capturados["pagamento"] = kwargs["contexto"]
        return original_pagamento(**kwargs)

    def estoque(**kwargs):
        capturados["estoque"] = kwargs["contexto"]
        return original_estoque(**kwargs)

    def transicao(**kwargs):
        capturados["transicao"] = kwargs["contexto"]
        return original_transicao(**kwargs)

    monkeypatch.setattr(checkout_module, "registrar_novo_pedido", criar)
    monkeypatch.setattr(checkout_module, "criar_obrigacao_pagamento", pagamento)
    monkeypatch.setattr(checkout_module, "reservar_estoque", estoque)
    monkeypatch.setattr(checkout_module, "transicionar_pedido", transicao)

    checkout_module.executar_checkout_em_transacao(
        comando=_comando(pedido, com_estoque=True),
        contexto=contexto,
        recursos=recursos,
    )

    assert capturados["criar"] is contexto
    assert capturados["pagamento"].permissoes == frozenset(
        {Permissao.PAGAMENTO_REGISTRAR}
    )
    assert capturados["estoque"].permissoes == frozenset(
        {Permissao.ESTOQUE_RESERVAR}
    )
    assert capturados["transicao"].permissoes == frozenset(
        {Permissao.PEDIDO_ALTERAR}
    )
    for interno in (
        capturados["pagamento"],
        capturados["estoque"],
        capturados["transicao"],
    ):
        assert interno.usuario_id == contexto.usuario_id
        assert interno.tenant_id == contexto.tenant_id
        assert interno.unidade_id == contexto.unidade_id
        assert interno.correlation_id == contexto.correlation_id
        assert interno.unidades_permitidas == frozenset({_UNIT})
        assert interno.identidade_sistema is False

    estoque_pdv = contexto_estoque_automatico_pdv(
        contexto,
        _NOW,
        permissao=Permissao.ESTOQUE_BAIXAR,
    )
    assert estoque_pdv.permissoes == frozenset({Permissao.ESTOQUE_BAIXAR})
    assert estoque_pdv.identidade_sistema is False
    assert estoque_pdv.usuario_id == contexto.usuario_id
    assert estoque_pdv.unidades_permitidas == frozenset({_UNIT})


def test_af09_h_internal_authority_is_not_a_caller_controlled_parameter() -> None:
    assert set(signature(checkout_module.executar_checkout_em_transacao).parameters) == {
        "comando",
        "contexto",
        "recursos",
    }
    assert set(signature(checkout_module.executar_checkout_v1).parameters) == {
        "comando",
        "contexto",
        "session_factory",
    }


def test_af09_i_checkout_rejects_cross_tenant_and_cross_unit_before_effects() -> None:
    contexto = _contexto(frozenset({Permissao.PEDIDO_CRIAR}))

    for pedido in (
        _pedido("i-tenant", tenant_id=_OTHER_TENANT),
        _pedido("i-unidade", unidade_id=_OTHER_UNIT),
    ):
        recursos = _RecursosEmMemoria()
        with pytest.raises(CheckoutInvalido, match="fora do tenant/unidade"):
            checkout_module.executar_checkout_em_transacao(
                comando=_comando(pedido),
                contexto=contexto,
                recursos=recursos,
            )
        assert recursos.pedidos.quantidade == 0
        assert recursos.outbox.mensagens == []
        assert recursos.auditoria.eventos == []


def test_af09_j_downstream_audit_preserves_original_caller_and_scope() -> None:
    recursos = _RecursosEmMemoria()
    contexto = _contexto(
        MATRIZ_PADRAO[Papel.ATENDIMENTO],
        usuario_id="atendimento-original-af09",
    )

    checkout_module.executar_checkout_em_transacao(
        comando=_comando(_pedido("j")),
        contexto=contexto,
        recursos=recursos,
    )

    assert len(recursos.auditoria.eventos) == 3
    assert all(
        evento.usuario_id == "atendimento-original-af09"
        and evento.papel_efetivo is Papel.ATENDIMENTO
        and evento.tenant_id == _TENANT
        and evento.unidade_id == _UNIT
        and evento.correlation_id == "corr-af09"
        for evento in recursos.auditoria.eventos
    )


def test_af09_k_role_without_create_permission_produces_zero_effects() -> None:
    recursos = _RecursosEmMemoria()
    pedido = _pedido("k")
    contexto = _contexto(
        MATRIZ_PADRAO[Papel.FINANCEIRO],
        papel=Papel.FINANCEIRO,
    )

    with pytest.raises(PermissaoNegada, match="permissao_insuficiente"):
        checkout_module.executar_checkout_em_transacao(
            comando=_comando(pedido),
            contexto=contexto,
            recursos=recursos,
        )

    assert recursos.pedidos.quantidade == 0
    assert recursos.pagamentos.buscar_pagamento(
        _TENANT, _UNIT, f"pagamento-{pedido.id}"
    ) is None
    assert recursos.estoque.buscar_reserva(_TENANT, _UNIT, str(pedido.id)) is None
    assert recursos.outbox.mensagens == []
    assert recursos.auditoria.eventos == []


def test_af09_l_assistant_real_caller_reaches_governed_checkout() -> None:
    recursos = _RecursosEmMemoria()
    contexto = _contexto(MATRIZ_PADRAO[Papel.ATENDIMENTO])

    def executor(**kwargs):
        assert kwargs["contexto"] is contexto
        return checkout_module.executar_checkout_em_transacao(
            comando=kwargs["comando"],
            contexto=kwargs["contexto"],
            recursos=recursos,
        )

    adapter = CheckoutAssistenteV1(
        session_factory=lambda: pytest.fail("AF-09 não deve abrir banco"),
        executor=executor,
        agora=lambda: _NOW,
    )
    carrinho = CarrinhoAtendimento(
        tenant_id=_TENANT,
        unidade_id=_UNIT,
        conversa_id="conversa-af09",
        mensagem_id="mensagem-af09",
        itens=(
            ItemCarrinhoAtendimento(
                produto_id="produto-af09",
                nome_produto="Produto AF-09",
                quantidade=1,
                preco_unitario=Decimal("30.00"),
            ),
        ),
        fingerprint="fingerprint-af09",
    )

    resultado = adapter.executar(
        contexto=contexto,
        carrinho=carrinho,
        cliente_ref="cliente-af09",
        canal="whatsapp",
        metodo=MetodoPagamento.PAGAMENTO_NA_ENTREGA,
        idempotency_key="confirmacao-af09",
    )

    assert resultado.pedido_status == PedidoStatus.AGUARDANDO_CONFIRMACAO.value
    assert resultado.pagamento_status is not None
    assert recursos.pedidos.quantidade == 1
