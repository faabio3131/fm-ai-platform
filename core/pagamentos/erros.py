class ErroPagamento(Exception):
    """Erro de negocio financeiro, seguro para a borda."""


class RecursoPagamentoIndisponivel(ErroPagamento):
    pass


class OperacaoPagamentoNaoAutorizada(ErroPagamento):
    pass


class FonteFinanceiraNaoConfiavel(ErroPagamento):
    """Confirmação eletrônica sem evidência produzida por fonte financeira validada."""


class ConflitoIdempotenciaPagamento(ErroPagamento):
    pass


class ConcorrenciaPagamento(ErroPagamento):
    pass


class ValorPagamentoInvalido(ErroPagamento):
    pass
