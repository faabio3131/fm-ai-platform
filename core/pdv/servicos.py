"""Orquestrador do rollout; shadow e canary possuem fronteiras distintas."""

from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Permissao

from .modelos import EntradaPDV, ResultadoPDV
from .repositorios import (
    EscritorShadow,
    ExecutorAutoritativo,
    ExecutorLegado,
    RegistroReconciliacao,
    UnitOfWorkPDV,
)
from .roteamento import (
    ConfiguracaoRolloutInvalida,
    ModoPDV,
    PDVRolloutConfig,
    decidir_modo,
)


class CheckoutNaoAutorizado(RuntimeError):
    pass


def finalizar_venda_pdv(
    *,
    entrada: EntradaPDV,
    contexto: ContextoExecucao,
    config: PDVRolloutConfig,
    legado: ExecutorLegado,
    uow_legado: UnitOfWorkPDV,
    shadow: EscritorShadow | None = None,
    uow_shadow: UnitOfWorkPDV | None = None,
    reconciliacao: RegistroReconciliacao | None = None,
    autoritativo: ExecutorAutoritativo | None = None,
    uow_autoritativo: UnitOfWorkPDV | None = None,
) -> ResultadoPDV:
    if (
        not contexto.identidade_sistema
        and Permissao.PDV_OPERAR not in contexto.permissoes
    ):
        raise CheckoutNaoAutorizado("pdv_operar_negado")
    modo = decidir_modo(
        contexto=contexto, terminal_id=entrada.terminal_id, config=config
    )
    # PR7 nao modela obrigacao zero: fallback explicito, nunca pagamento ficticio.
    if modo is ModoPDV.AUTHORITATIVE_CANARY and entrada.total.valor == 0:
        modo = ModoPDV.LEGACY
    if modo is ModoPDV.LEGACY:
        with uow_legado:
            resultado = legado.executar(entrada)
            uow_legado.commit()
        if entrada.total.valor == 0:
            return ResultadoPDV(
                **{**resultado.__dict__, "motivo": "saldo_zero_financeiro_nao_modelado"}
            )
        return resultado
    if modo is ModoPDV.SHADOW:
        with uow_legado:
            resultado = legado.executar(entrada)
            uow_legado.commit()
        if shadow is None or uow_shadow is None:
            return resultado
        try:
            with uow_shadow:
                pedido_id = shadow.escrever(entrada, resultado.venda_legada_id)
                uow_shadow.commit()
            return ResultadoPDV(
                **{**resultado.__dict__, "modo": modo.value, "pedido_id": pedido_id}
            )
        except Exception as exc:  # noqa: BLE001 - shadow nunca invalida a venda legada
            if reconciliacao:
                reconciliacao.registrar_falha_shadow(
                    entrada, resultado.venda_legada_id, type(exc).__name__
                )
            return ResultadoPDV(
                **{
                    **resultado.__dict__,
                    "modo": modo.value,
                    "motivo": "shadow_reparo_necessario",
                }
            )
    if autoritativo is None or uow_autoritativo is None:
        raise ConfiguracaoRolloutInvalida("executor_autoritativo_ausente")
    with uow_autoritativo:
        resultado = autoritativo.executar(entrada)
        uow_autoritativo.commit()
        return resultado
