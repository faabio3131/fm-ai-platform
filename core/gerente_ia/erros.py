"""Erros estáveis do Gerente IA V1."""


class ErroGerenteIA(ValueError):
    """Erro de domínio sem detalhes sensíveis."""

    def __init__(self, codigo: str) -> None:
        super().__init__(codigo)
        self.codigo = codigo
