"""Projecao explicita para Venda legada; nao importa app.py nem persiste efeitos."""

from typing import Any

from .modelos import MetodoPagamento, VendaFinanceira

_FORMAS = {
    MetodoPagamento.DINHEIRO: "Dinheiro",
    MetodoPagamento.PIX: "Pix",
    MetodoPagamento.CARTAO_CREDITO: "Cartão de Crédito",
    MetodoPagamento.CARTAO_DEBITO: "Cartão de Débito",
    MetodoPagamento.VOUCHER: "Voucher",
}


class AdapterVendaLegada:
    """Converte Decimal para float somente na borda historica documentada."""

    def materializar(
        self,
        venda: VendaFinanceira,
        *,
        produto_id: int,
        cliente_id: int | None = None,
        quantidade: int = 1,
        custo_total: float = 0.0,
    ) -> dict[str, Any]:
        if quantidade < 1:
            raise ValueError("quantidade deve ser positiva")
        return {
            "produto_id": produto_id,
            "cliente_id": cliente_id,
            "quantidade": quantidade,
            "valor_total": float(venda.valor.valor),
            "custo_total": custo_total,
            "forma_pagamento": _FORMAS.get(venda.metodo, "Outro"),
            "status_pagamento": "Aprovado",
            "data_venda": venda.reconhecida_em.replace(tzinfo=None),
        }
