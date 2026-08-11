"""Erros estáveis da Expedição e Entrega V1."""


class ErroEntrega(Exception):
    def __init__(self, codigo: str, mensagem: str = "Operação de entrega recusada") -> None:
        super().__init__(mensagem)
        self.codigo = codigo
