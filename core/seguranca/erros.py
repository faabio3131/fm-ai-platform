"""Erros seguros e estáveis da fundação de segurança."""


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


class CredenciaisInvalidas(ErroSeguranca):
    codigo = "seguranca.credenciais_invalidas"


class UsuarioInativo(ErroSeguranca):
    codigo = "seguranca.usuario_inativo"


class SegredoAusente(ErroSeguranca):
    codigo = "seguranca.segredo_ausente"


class ReferenciaSegredoInvalida(ErroSeguranca):
    codigo = "seguranca.referencia_segredo_invalida"
