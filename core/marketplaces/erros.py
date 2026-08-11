"""Erros normalizados do framework de marketplaces V1."""

from core.eventos.retry import ErroNaoRetryable


class ErroMarketplace(ValueError):
    """Erro base com código estável para adapters e serviços."""

    def __init__(self, codigo: str) -> None:
        super().__init__(codigo)
        self.codigo = codigo


class ErroMarketplacePermanente(ErroNaoRetryable):
    """Falha que deve ir para DLQ sem novas tentativas automáticas."""

    def __init__(self, codigo: str) -> None:
        super().__init__(codigo)
        self.codigo = codigo


class ErroMarketplaceTransitorio(Exception):
    """Falha externa/transitória elegível a retry."""

    def __init__(self, codigo: str) -> None:
        super().__init__(codigo)
        self.codigo = codigo
