"""Boundary cognitivo compartilhado para consumidores FM Control Center.

Este módulo não contém regra de negócio do FMCC e não cria um segundo Core.
Ele usa o AI Model Router canônico apenas para planejamento e síntese textual.
Autoridade de tenant, métricas e ações permanece no consumidor governado.
"""

from __future__ import annotations

import json
from typing import Any

from core.ai_router import AIModelRouter, CapabilityIA, SolicitacaoIA

_MAX_QUESTION_LENGTH = 4000
_MAX_ANSWER_LENGTH = 8000
_FORBIDDEN_PLAN_ARGUMENTS = frozenset(
    {
        "tenant_id",
        "tenantId",
        "user_id",
        "userId",
        "authorization",
        "token",
        "secret",
        "service_token",
        "role",
        "permissions",
    }
)


class ErroCoreCompartilhadoFMCC(RuntimeError):
    def __init__(self, codigo: str) -> None:
        self.codigo = codigo
        super().__init__(codigo)


def _objeto_json(conteudo: Any) -> dict[str, Any]:
    if isinstance(conteudo, dict):
        return conteudo

    if not isinstance(conteudo, str):
        raise ErroCoreCompartilhadoFMCC("fmcc_core.resposta_invalida")

    texto = conteudo.strip()
    if texto.startswith("```"):
        texto = texto.strip("`")
        if texto.startswith("json"):
            texto = texto[4:].strip()

    try:
        objeto = json.loads(texto)
    except json.JSONDecodeError as exc:
        raise ErroCoreCompartilhadoFMCC(
            "fmcc_core.resposta_invalida"
        ) from exc

    if not isinstance(objeto, dict):
        raise ErroCoreCompartilhadoFMCC("fmcc_core.resposta_invalida")
    return objeto


def _texto_pergunta(pergunta: str) -> str:
    normalizada = pergunta.strip()
    if not normalizada or len(normalizada) > _MAX_QUESTION_LENGTH:
        raise ErroCoreCompartilhadoFMCC("fmcc_core.pergunta_invalida")
    return normalizada


class ServicoCoreCompartilhadoFMCC:
    """Planejamento/síntese provider-neutral sobre o router canônico."""

    def __init__(self, router: AIModelRouter) -> None:
        self._router = router

    def planejar(
        self,
        *,
        pergunta: str,
        tenant_id: str,
        usuario_id: str,
        correlation_id: str,
        capabilities_permitidas: tuple[str, ...],
    ) -> dict[str, Any]:
        pergunta = _texto_pergunta(pergunta)
        permitidas = tuple(
            item.strip()
            for item in capabilities_permitidas
            if isinstance(item, str) and item.strip()
        )
        if not permitidas:
            raise ErroCoreCompartilhadoFMCC(
                "fmcc_core.capabilities_ausentes"
            )

        resultado = self._router.executar(
            SolicitacaoIA(
                tenant_id=tenant_id,
                unidade_id="fm-control-center",
                request_id=correlation_id,
                correlation_id=correlation_id,
                capability=CapabilityIA.FMCC_PLANNING,
                conteudo={
                    "system": (
                        "Você é o planejador cognitivo compartilhado da Nova FM. "
                        "Escolha SOMENTE uma capability da allowlist fornecida. "
                        "Responda SOMENTE JSON com capability e arguments. "
                        "Nunca inclua tenant, usuário, papel, permissão, token, "
                        "segredo ou autorização nos arguments."
                    ),
                    "question": pergunta,
                    "allowed_capabilities": permitidas,
                },
            )
        )

        plano = _objeto_json(resultado.conteudo)
        capability = str(plano.get("capability", "")).strip()
        argumentos = plano.get("arguments", {})

        if capability not in permitidas:
            raise ErroCoreCompartilhadoFMCC(
                "fmcc_core.capability_nao_permitida"
            )
        if not isinstance(argumentos, dict):
            raise ErroCoreCompartilhadoFMCC(
                "fmcc_core.arguments_invalidos"
            )
        if _FORBIDDEN_PLAN_ARGUMENTS.intersection(argumentos):
            raise ErroCoreCompartilhadoFMCC(
                "fmcc_core.arguments_de_escopo_proibidos"
            )

        return {
            "capability": capability,
            "arguments": argumentos,
        }

    def sintetizar(
        self,
        *,
        pergunta: str,
        tenant_id: str,
        usuario_id: str,
        correlation_id: str,
        fatos: tuple[dict[str, Any], ...],
        evidencias: tuple[dict[str, Any], ...],
    ) -> dict[str, Any]:
        pergunta = _texto_pergunta(pergunta)
        if not fatos or not evidencias:
            raise ErroCoreCompartilhadoFMCC(
                "fmcc_core.evidencia_obrigatoria"
            )

        resultado = self._router.executar(
            SolicitacaoIA(
                tenant_id=tenant_id,
                unidade_id="fm-control-center",
                request_id=correlation_id,
                correlation_id=correlation_id,
                capability=CapabilityIA.FMCC_SYNTHESIS,
                conteudo={
                    "system": (
                        "Sintetize uma resposta executiva usando EXCLUSIVAMENTE "
                        "os facts fornecidos. Não invente números, fontes, datas, "
                        "moedas ou conclusões ausentes. Não trate missing como zero. "
                        "Não calcule lucro ou conversão se esses fatos não vierem "
                        "explicitamente prontos da autoridade determinística. "
                        "Responda em texto simples e conciso."
                    ),
                    "question": pergunta,
                    "facts": list(fatos),
                    "evidence": list(evidencias),
                },
            )
        )

        bruto = resultado.conteudo
        if isinstance(bruto, dict):
            resposta = str(bruto.get("answer", "")).strip()
        elif isinstance(bruto, str):
            resposta = bruto.strip()
        else:
            resposta = ""

        if not resposta or len(resposta) > _MAX_ANSWER_LENGTH:
            raise ErroCoreCompartilhadoFMCC(
                "fmcc_core.resposta_invalida"
            )

        # Evidência e factualStatus são definidos pelo boundary governado,
        # nunca pelo modelo. O modelo somente redige a resposta.
        return {
            "answer": resposta,
            "evidence": list(evidencias),
            "factualStatus": "grounded",
        }
