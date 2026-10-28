"""Erros determinísticos da autoridade de Procurement V1."""


class ErroProcurement(RuntimeError):
    pass


class ProcurementNaoAutorizado(ErroProcurement):
    pass


class ProcurementForaDoEscopo(ErroProcurement):
    pass


class ConflitoProcurement(ErroProcurement):
    pass


class EstadoProcurementInvalido(ErroProcurement):
    pass


class DivergenciaRecebimento(ErroProcurement):
    pass
