"""DTOs HTTP da configuração financeira/operacional original, sem autoridade paralela."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, RootModel
from sqlalchemy.orm import Session

from application.administracao_proprietario import AplicacaoAdministracaoProprietarioV1
from core.administracao import ConfiguracaoEstabelecimento
from core.seguranca.erros import ErroSeguranca
from http_api.admin_backoffice import contexto_backoffice
from http_api.admin_dashboard import _tratar_erro
from http_api.auth import AuthSessionRuntime


class FormaPagamento(RootModel):
    root: str

    @classmethod
    def permitidas(cls) -> set[str]:
        return {
            "dinheiro",
            "pix",
            "cartao_credito",
            "cartao_debito",
            "voucher",
            "outro",
            "pagamento_na_entrega",
            "recebimento_posterior",
        }

    def validate_forma(self) -> str:
        forma = self.root.strip().casefold()
        if forma not in self.permitidas():
            raise ValueError("forma_pagamento_invalida")
        return forma


class ConfiguracaoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    formas_pagamento: list[str] = Field(default_factory=list)
    taxa_servico_percentual: Decimal = Field(default=Decimal(0), ge=0, le=100)
    parametros_operacionais: dict[str, Any] = Field(default_factory=dict)
    politica_financeira: dict[str, Any] = Field(default_factory=dict)
    versao: int = Field(ge=1)


class ConfiguracaoOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: str
    unidade_id: str
    formas_pagamento: list[str]
    taxa_servico_percentual: str
    parametros_operacionais: dict[str, Any]
    politica_financeira: dict[str, Any]
    versao: int
    atualizado_em: str | None = None


def _format_taxa(taxa: Decimal) -> str:
    s = format(taxa, "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


def _config_out(config: ConfiguracaoEstabelecimento) -> dict[str, Any]:
    return {
        "tenant_id": config.tenant_id,
        "unidade_id": config.unidade_id,
        "formas_pagamento": list(config.formas_pagamento),
        "taxa_servico_percentual": _format_taxa(config.taxa_servico_percentual),
        "parametros_operacionais": dict(config.parametros_operacionais),
        "politica_financeira": dict(config.politica_financeira),
        "versao": config.versao,
        "atualizado_em": config.atualizado_em.isoformat() if config.atualizado_em else None,
    }


def _validar_chaves_seguras(obj: Mapping[str, object] | dict[str, Any], campo: str) -> None:
    """Rejeita chaves que parecem segredos/credenciais."""
    chaves_proibidas = {
        "access_token", "api_key", "authorization", "client_secret", "password",
        "private_key", "refresh_token", "secret", "token", "senha", "segredo",
        "pix_key", "chave_pix", "webhook_secret", "hmac_key", "signing_key",
        "certificate", "privatekey", "clientsecret", "apikey", "accesstoken",
    }
    for chave in obj:
        if chave.strip().casefold() in chaves_proibidas:
            raise ValueError(f"{campo}.chave_secreta_proibida: {chave}")


def _erro_config(exc: Exception) -> JSONResponse:
    if isinstance(exc, ErroSeguranca):
        return _tratar_erro(exc)
    if isinstance(exc, PermissionError):
        return _tratar_erro(exc)
    if isinstance(exc, LookupError):
        return JSONResponse(status_code=404, content={"erro": str(exc) or "admin.configuracao_nao_encontrada"})
    if isinstance(exc, ValueError):
        return JSONResponse(status_code=400, content={"erro": str(exc)})
    if isinstance(exc, RuntimeError) and "concorrente" in str(exc).casefold():
        return JSONResponse(status_code=409, content={"erro": str(exc)})
    return _tratar_erro(exc)


def build_admin_configuracao_router(
    *, session_factory: Callable[[], Session], auth_runtime: AuthSessionRuntime
) -> APIRouter:
    router = APIRouter(prefix="/v1/admin", tags=["admin-configuracao"])
    app = AplicacaoAdministracaoProprietarioV1(session_factory)

    @router.get("/configuracao/{unidade_id}", response_model=None)
    def consultar_configuracao(
        unidade_id: str, request: Request
    ) -> dict[str, Any] | JSONResponse:
        try:
            contexto = contexto_backoffice(
                request,
                auth_runtime=auth_runtime,
                origem="admin_configuracao_http_v1.consultar",
            )
            config = app.obter_configuracao(contexto=contexto, unidade_id=unidade_id)
            return _config_out(config)
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _erro_config(exc)

    @router.put("/configuracao/{unidade_id}", response_model=None)
    def atualizar_configuracao(
        unidade_id: str, payload: ConfiguracaoIn, request: Request
    ) -> dict[str, Any] | JSONResponse:
        try:
            contexto = contexto_backoffice(
                request,
                auth_runtime=auth_runtime,
                origem="admin_configuracao_http_v1.atualizar",
            )

            # Valida chaves proibidas
            _validar_chaves_seguras(payload.parametros_operacionais, "parametros_operacionais")
            _validar_chaves_seguras(payload.politica_financeira, "politica_financeira")

            # Valida formas de pagamento
            formas_validadas = []
            for forma in payload.formas_pagamento:
                f = FormaPagamento(root=forma)
                formas_validadas.append(f.validate_forma())

            configuracao = ConfiguracaoEstabelecimento(
                tenant_id=contexto.tenant_id,
                unidade_id=unidade_id,
                formas_pagamento=tuple(formas_validadas),
                taxa_servico_percentual=payload.taxa_servico_percentual,
                parametros_operacionais=payload.parametros_operacionais,
                politica_financeira=payload.politica_financeira,
                versao=payload.versao,
            )

            atual = app.salvar_configuracao(
                contexto=contexto,
                configuracao=configuracao,
                versao_esperada=payload.versao,
            )
            return _config_out(atual)
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _erro_config(exc)

    return router