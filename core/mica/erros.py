"""Erros normalizados da Mica V1."""


class ErroMica(RuntimeError):
    def __init__(self, codigo: str, detalhe: str | None = None) -> None:
        super().__init__(detalhe or codigo)
        self.codigo = codigo
        self.detalhe = detalhe
