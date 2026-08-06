"""Erros seguros e estaveis da fundacao de seguranca."""


class ErroSeguranca(ValueError):
    codigo = "seguranca.erro"


class ContextoAusente(ErroSeguranca):
    codigo = "seguranca.contexto_ausente"


class TenantNaoAutorizado(ErroSeguranca):
    codigo = "seguranca.recurso_indisponivel"


class UnidadeNaoAutorizada(ErroSeguranca):
    codigo = "seguranca.recurso_indisponivel"


class PermissaoInsuficiente(ErroSeguranca):
    codigo = "seguranca.permissao_insuficiente"


class AlcadaExcedida(ErroSeguranca):
    codigo = "seguranca.alcada_excedida"


class ConfirmacaoSegurancaObrigatoria(ErroSeguranca):
    codigo = "seguranca.confirmacao_obrigatoria"


class IdentidadeSistemaInvalida(ErroSeguranca):
    codigo = "seguranca.identidade_sistema_invalida"


class RecursoProtegido(ErroSeguranca):
    codigo = "seguranca.recurso_indisponivel"


class MetadataAuditoriaInvalida(ErroSeguranca):
    codigo = "seguranca.metadata_invalida"
