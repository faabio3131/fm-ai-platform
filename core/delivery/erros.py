"""Erros normalizados do Delivery Próprio V1."""


class ErroDelivery(ValueError):
    """Erro de domínio com código estável para UI/adapters."""

    def __init__(self, codigo: str) -> None:
        super().__init__(codigo)
        self.codigo = codigo
