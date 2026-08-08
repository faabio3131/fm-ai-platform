from core.dominio.erros import ErroDominio


class PedidoConcorrente(ErroDominio):
    codigo = "pedido_concorrente"


class EscopoPedidoInvalido(ErroDominio):
    codigo = "escopo_pedido_invalido"
