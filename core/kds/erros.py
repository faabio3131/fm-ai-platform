"""Erros estaveis do KDS V1."""


class ErroKDS(Exception):
    def __init__(self, codigo: str, mensagem: str = "Operacao KDS recusada") -> None:
        super().__init__(mensagem)
        self.codigo = codigo
