"""Erros estáveis da interface do garçom V1."""


class ErroGarcom(Exception):
    def __init__(self, codigo: str, mensagem: str = "Operação do garçom recusada") -> None:
        super().__init__(mensagem)
        self.codigo = codigo
