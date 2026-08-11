"""Erros estaveis da operacao de salao V1."""


class ErroSalao(Exception):
    def __init__(self, codigo: str, mensagem: str = "Operacao de salao recusada") -> None:
        super().__init__(mensagem)
        self.codigo = codigo
