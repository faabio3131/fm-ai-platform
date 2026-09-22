"""Erros determinísticos da FM Commercial Platform."""


class ErroComercial(ValueError):
    """Erro base do domínio comercial."""


class DadoComercialInvalido(ErroComercial):
    pass


class RegistroComercialNaoEncontrado(ErroComercial):
    pass


class ConflitoIdempotenciaComercial(ErroComercial):
    pass


class ConflitoConcorrenciaComercial(ErroComercial):
    pass


class RegistroComercialDuplicado(ErroComercial):
    pass


class TransicaoComercialInvalida(ErroComercial):
    pass
