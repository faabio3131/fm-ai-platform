"""Erros normalizados do CRM e conversão consentida V1."""


class ErroCRM(ValueError):
    """Erro de domínio com código estável para UI/adapters."""

    def __init__(self, codigo: str) -> None:
        super().__init__(codigo)
        self.codigo = codigo
