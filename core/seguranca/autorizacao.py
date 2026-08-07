"""Autorizacao deny-by-default e protecao IDOR."""

from dataclasses import dataclass
from typing import Any

from core.dominio.dinheiro import Dinheiro
from core.dominio.serializacao import Serializavel

from .contexto import ContextoExecucao
from .permissoes import Papel, Permissao
from .politicas import PoliticaAlcada


@dataclass(frozen=True)
class DecisaoAutorizacao(Serializavel):
    autorizado: bool
    codigo: str
    motivo: str
    confirmacao_exigida: bool
    aprovador_exigido: Papel | None
    politica_aplicada: str
    correlation_id: str


class AutorizarAcao:
    def __init__(self, politica_alcada: PoliticaAlcada | None = None) -> None:
        self._alcada = politica_alcada or PoliticaAlcada()

    def executar(
        self,
        *,
        contexto: ContextoExecucao,
        permissao: Permissao,
        recurso: str,
        tenant_recurso: str,
        unidade_recurso: str,
        valor: Dinheiro | None = None,
        estado_atual: str | None = None,
        metadata: tuple[tuple[str, Any], ...] = (),
    ) -> DecisaoAutorizacao:
        del recurso, estado_atual, metadata
        if tenant_recurso != contexto.tenant_id or unidade_recurso not in (
            contexto.unidades_permitidas or frozenset({contexto.unidade_id})
        ):
            return self._negar(contexto, "recurso_indisponivel", "Recurso indisponivel")
        if permissao not in contexto.permissoes:
            return self._negar(
                contexto, "permissao_insuficiente", "Operacao nao autorizada"
            )
        resultado = self._alcada.avaliar(permissao, valor)
        if resultado.confirmacao_exigida:
            return DecisaoAutorizacao(
                False,
                "aprovacao_exigida",
                resultado.motivo,
                True,
                resultado.papel_aprovador,
                resultado.politica,
                contexto.correlation_id,
            )
        if Papel.GERENTE_IA in contexto.papeis and permissao not in {
            Permissao.PEDIDO_VISUALIZAR,
            Permissao.GERENTE_IA_CONSULTAR,
            Permissao.GERENTE_IA_PREPARAR_ACAO,
        }:
            return DecisaoAutorizacao(
                False,
                "confirmacao_exigida",
                "Confirmacao humana exigida",
                True,
                Papel.GERENTE,
                "gerente_ia_minimo_privilegio",
                contexto.correlation_id,
            )
        return DecisaoAutorizacao(
            True,
            "autorizado",
            "Operacao autorizada",
            False,
            None,
            resultado.politica,
            contexto.correlation_id,
        )

    @staticmethod
    def _negar(
        contexto: ContextoExecucao, codigo: str, motivo: str
    ) -> DecisaoAutorizacao:
        return DecisaoAutorizacao(
            False,
            codigo,
            motivo,
            False,
            None,
            "deny_by_default",
            contexto.correlation_id,
        )


def recurso_no_escopo(
    contexto: ContextoExecucao, tenant_id: str, unidade_id: str
) -> bool:
    """Resposta uniforme: ID existente nunca implica autorização."""
    return tenant_id == contexto.tenant_id and unidade_id in (
        contexto.unidades_permitidas or frozenset({contexto.unidade_id})
    )
