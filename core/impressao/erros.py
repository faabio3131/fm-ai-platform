"""Erros estáveis da Impressão por Setor V1."""


class ErroImpressao(Exception):
    def __init__(self, codigo: str, mensagem: str = "Operação de impressão recusada") -> None:
        super().__init__(mensagem)
        self.codigo = codigo
