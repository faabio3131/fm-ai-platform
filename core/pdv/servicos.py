"""Orquestrador do rollout; shadow e canary possuem fronteiras distintas."""

import logging

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

_LOGGER_ROLLOUT = logging.getLogger("fm_ai.pdv.rollout")


class CheckoutNaoAutorizado(RuntimeError):
    pass


def _emitir_metrica_rollout(
    *,
    contexto: ContextoExecucao,
    entrada: EntradaPDV,
    modo: ModoPDV,
    resultado: ResultadoPDV | None = None,
    motivo: str | None = None,
) -> None:
    """Telemetria sem PII/segredos e sem autoridade sobre o checkout."""

    _LOGGER_ROLLOUT.info(
        "pdv_rollout_resultado",
        extra={
            "pdv_event": "pdv_rollout_resultado",
            "pdv_tenant_id": contexto.tenant_id,
            "pdv_unidade_id": contexto.unidade_id,
            "pdv_terminal_id": entrada.terminal_id,
            "pdv_modo": modo.value,
            "pdv_sucesso": bool(resultado and resultado.sucesso),
            "pdv_idempotente": bool(resultado and resultado.idempotente),
            "pdv_motivo": (
                motivo
                if motivo is not None
                else (resultado.motivo if resultado is not None else None)
            ),
        },
    )


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

    if modo is ModoPDV.LEGACY:
        try:
            with uow_legado:
                resultado = legado.executar(entrada)
                uow_legado.commit()
        except Exception as exc:
            _emitir_metrica_rollout(
                contexto=contexto,
                entrada=entrada,
                modo=modo,
                motivo=f"exception:{type(exc).__name__}",
            )
            raise
        _emitir_metrica_rollout(
            contexto=contexto, entrada=entrada, modo=modo, resultado=resultado
        )
        return resultado

    if modo is ModoPDV.SHADOW:
        try:
            with uow_legado:
                resultado = legado.executar(entrada)
                uow_legado.commit()
        except Exception as exc:
            _emitir_metrica_rollout(
                contexto=contexto,
                entrada=entrada,
                modo=modo,
                motivo=f"exception:{type(exc).__name__}",
            )
            raise
        if shadow is None or uow_shadow is None:
            _emitir_metrica_rollout(
                contexto=contexto, entrada=entrada, modo=modo, resultado=resultado
            )
            return resultado
        try:
            with uow_shadow:
                pedido_id = shadow.escrever(entrada, resultado.venda_legada_id)
                uow_shadow.commit()
            resultado_shadow = ResultadoPDV(
                **{**resultado.__dict__, "modo": modo.value, "pedido_id": pedido_id}
            )
            _emitir_metrica_rollout(
                contexto=contexto,
                entrada=entrada,
                modo=modo,
                resultado=resultado_shadow,
            )
            return resultado_shadow
        except Exception as exc:  # noqa: BLE001
            if reconciliacao:
                reconciliacao.registrar_falha_shadow(
                    entrada, resultado.venda_legada_id, type(exc).__name__
                )
            resultado_shadow = ResultadoPDV(
                **{
                    **resultado.__dict__,
                    "modo": modo.value,
                    "motivo": "shadow_reparo_necessario",
                }
            )
            _emitir_metrica_rollout(
                contexto=contexto,
                entrada=entrada,
                modo=modo,
                resultado=resultado_shadow,
            )
            return resultado_shadow

    if autoritativo is None or uow_autoritativo is None:
        _emitir_metrica_rollout(
            contexto=contexto,
            entrada=entrada,
            modo=modo,
            motivo="executor_autoritativo_ausente",
        )
        raise ConfiguracaoRolloutInvalida("executor_autoritativo_ausente")

    try:
        with uow_autoritativo:
            resultado = autoritativo.executar(entrada)
            uow_autoritativo.commit()
    except Exception as exc:
        _emitir_metrica_rollout(
            contexto=contexto,
            entrada=entrada,
            modo=modo,
            motivo=f"exception:{type(exc).__name__}",
        )
        raise
    _emitir_metrica_rollout(
        contexto=contexto, entrada=entrada, modo=modo, resultado=resultado
    )
    return resultado
