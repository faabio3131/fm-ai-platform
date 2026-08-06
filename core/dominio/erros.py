"""Erros estáveis e serializáveis do domínio operacional."""

from __future__ import annotations

from typing import Any


class ErroDominio(Exception):
    codigo = "erro_dominio"

    def __init__(self, mensagem: str, detalhes: dict[str, Any] | None = None) -> None:
        self.mensagem = mensagem
        self.detalhes = detalhes or {}
        super().__init__(mensagem)

    def para_dict(self) -> dict[str, Any]:
        return {
            "codigo": self.codigo,
            "mensagem": self.mensagem,
            "detalhes": self.detalhes,
        }


class ErroValidacaoDominio(ErroDominio):
    codigo = "validacao_dominio"


class EstadoInvalido(ErroDominio):
    codigo = "estado_invalido"


class TransicaoInvalida(ErroDominio):
    codigo = "transicao_invalida"


class PermissaoNegada(ErroDominio):
    codigo = "permissao_negada"


class TenantInvalido(ErroValidacaoDominio):
    codigo = "tenant_invalido"


class ValorMonetarioInvalido(ErroValidacaoDominio):
    codigo = "valor_monetario_invalido"


class IdentificadorInvalido(ErroValidacaoDominio):
    codigo = "identificador_invalido"


class PedidoInvalido(ErroValidacaoDominio):
    codigo = "pedido_invalido"


class PagamentoInvalido(ErroValidacaoDominio):
    codigo = "pagamento_invalido"


class EstoqueInsuficiente(ErroDominio):
    codigo = "estoque_insuficiente"


class ConflitoIdempotencia(ErroDominio):
    codigo = "conflito_idempotencia"


class ConfirmacaoObrigatoria(ErroDominio):
    codigo = "confirmacao_obrigatoria"


class RecursoNaoEncontrado(ErroDominio):
    codigo = "recurso_nao_encontrado"
