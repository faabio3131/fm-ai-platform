"""Erros publicos e uniformes do estoque operacional V1."""


class ErroEstoque(Exception):
    pass


class SaldoInsuficiente(ErroEstoque):
    pass


class ConflitoIdempotenciaEstoque(ErroEstoque):
    pass


class ConcorrenciaEstoque(ErroEstoque):
    pass


class RecursoEstoqueIndisponivel(ErroEstoque):
    pass


class OperacaoEstoqueNaoAutorizada(ErroEstoque):
    pass


class ReservaInvalida(ErroEstoque):
    pass
