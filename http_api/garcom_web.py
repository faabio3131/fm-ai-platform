"""HTTP session-aware do Garçom Web V1, sem segunda autoridade de domínio."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

from fastapi import APIRouter, Header, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from application.garcom_fechamento import (
    AplicacaoFechamentoGarcomV1,
    ConfiguracaoFechamentoGarcom,
    DemonstrativoFechamentoGarcom,
    DestinoRecebimento,
    ModoRecebimentoGarcom,
)
from application.garcom_transacoes import AplicacaoGarcomV1
from application.salao_transacoes import AplicacaoSalaoV1
from core.garcom import ErroGarcom, ServicoGarcom
from core.kds import RepositorioKDSSQLAlchemy
from core.pagamentos.erros import ErroPagamento
from core.pagamentos.modelos import ResultadoPagamento
from core.salao import (
    Comanda,
    ErroSalao,
    MetodoFechamento,
    RepositorioSalaoSQLAlchemy,
)
from core.seguranca import ContextoExecucao
from core.seguranca.erros import CredenciaisInvalidas, ErroSeguranca
from http_api.auth import AuthSessionRuntime
from http_api.operational_auth import obter_identidade_operacional

SessionFactory = Callable[[], Session]


class ConfiguracaoFechamentoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    modo_recebimento: ModoRecebimentoGarcom
    couvert_ativado: bool
    couvert_valor: Decimal = Field(ge=0)
    versao: int = Field(ge=1)


class AbrirComandaIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    versao: int = Field(ge=1)
    numero: str | None = Field(default=None, max_length=64)


class MutacaoVersionadaIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    versao: int = Field(ge=1)


class ComponentesFechamentoIn(MutacaoVersionadaIn):
    incluir_taxa_servico: bool = True


class DestinoRecebimentoIn(MutacaoVersionadaIn):
    destino: DestinoRecebimento


class ParcelaIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    metodo: MetodoFechamento
    valor: Decimal = Field(gt=0)
    participante_id: str | None = None


class DivisaoIn(MutacaoVersionadaIn):
    parcelas: list[ParcelaIn] = Field(min_length=1)


class CriarPagamentoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pagamento_id: str = Field(min_length=1, max_length=64)
    pedido_id: str = Field(min_length=1, max_length=64)
    metodo: MetodoFechamento
    valor: Decimal = Field(gt=0)
    provedor: str | None = Field(default=None, max_length=80)


class ConfirmarPagamentoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    metodo: MetodoFechamento
    valor: Decimal = Field(gt=0)
    versao_pagamento: int = Field(ge=1)
    referencia_externa: str | None = Field(default=None, max_length=160)


class RegistrarPagamentoIn(MutacaoVersionadaIn):
    metodo: MetodoFechamento
    valor: Decimal = Field(gt=0)


def _contexto(
    request: Request,
    session: Session,
    *,
    auth_runtime: AuthSessionRuntime,
) -> ContextoExecucao:
    identidade = obter_identidade_operacional(
        request,
        session,
        auth_runtime=auth_runtime,
    )
    if identidade.modo != "session":
        raise CredenciaisInvalidas("sessao_web_obrigatoria")
    return identidade.identidade.contexto(
        origem="garcom_web_http_v1",
        correlation_id=request.headers.get("x-correlation-id") or None,
    )


def _comanda_dict(comanda: Comanda) -> dict[str, object]:
    return {
        "id": comanda.comanda_id,
        "numero": comanda.numero,
        "mesa_id": comanda.mesa_id,
        "status": comanda.status.name,
        "total": str(comanda.total),
        "saldo": str(comanda.saldo),
        "versao": comanda.versao,
    }


def _demonstrativo_dict(
    item: DemonstrativoFechamentoGarcom,
) -> dict[str, object]:
    destino = item.destino_recebimento
    return {
        "comanda_id": item.comanda_id,
        "consumo": str(item.consumo),
        "couvert_artistico": str(item.couvert_artistico),
        "taxa_servico_percentual": str(item.taxa_servico_percentual),
        "taxa_servico_valor": str(item.taxa_servico_valor),
        "taxa_servico_incluida": item.taxa_servico_incluida,
        "desconto": str(item.desconto),
        "total": str(item.total),
        "saldo": str(item.saldo),
        "configuracao_versao": item.configuracao_versao,
        "consolidado": item.consolidado,
        "destino_recebimento": destino.value if destino else None,
    }


def _config_dict(
    item: ConfiguracaoFechamentoGarcom,
) -> dict[str, object]:
    return {
        "tenant_id": item.tenant_id,
        "unidade_id": item.unidade_id,
        "modo_recebimento": item.modo_recebimento.value,
        "taxa_servico_percentual": str(item.taxa_servico_percentual),
        "couvert_ativado": item.couvert_ativado,
        "couvert_valor": str(item.couvert_valor),
        "versao": item.versao,
    }


def _pagamento_dict(
    resultado: ResultadoPagamento,
) -> dict[str, object]:
    pagamento = resultado.pagamento
    return {
        "id": pagamento.id,
        "pedido_id": pagamento.pedido_id,
        "comanda_id": pagamento.comanda_id,
        "metodo": pagamento.metodo.value,
        "status": pagamento.status.value,
        "valor_previsto": str(pagamento.valor_previsto.valor),
        "valor_pago": str(pagamento.valor_pago.valor),
        "saldo": str(pagamento.saldo.valor),
        "versao": pagamento.versao,
        "idempotente": resultado.idempotente,
    }

def _erro_http(exc: Exception) -> JSONResponse:
    if isinstance(exc, CredenciaisInvalidas):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"erro": exc.codigo},
        )
    if isinstance(exc, ErroSeguranca):
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"erro": exc.codigo},
        )
    if isinstance(exc, (ErroGarcom, ErroSalao)):
        codigo = exc.codigo
        if codigo.startswith("seguranca.") or codigo in {
            "comanda_fora_alcada",
            "alçada_insuficiente",
        }:
            http_status = status.HTTP_403_FORBIDDEN
        elif codigo in {
            "comanda_indisponivel",
            "recurso_indisponivel",
            "configuracao_estabelecimento_ausente",
        }:
            http_status = status.HTTP_404_NOT_FOUND
        elif "concorrente" in codigo or codigo in {
            "conflito_idempotencia",
            "destino_recebimento_ja_definido",
            "transicao_comanda_invalida",
        }:
            http_status = status.HTTP_409_CONFLICT
        else:
            http_status = status.HTTP_400_BAD_REQUEST
        return JSONResponse(
            status_code=http_status,
            content={"erro": codigo},
        )
    if isinstance(exc, ErroPagamento):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"erro": str(exc)},
        )
    if isinstance(exc, (ValueError, RuntimeError)):
        code = str(exc) or "requisicao_invalida"
        return JSONResponse(
            status_code=(
                status.HTTP_409_CONFLICT
                if "concorrente" in code
                else status.HTTP_400_BAD_REQUEST
            ),
            content={"erro": code},
        )
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"erro": "garcom_indisponivel"},
    )


def build_garcom_web_router(
    *,
    session_factory: SessionFactory,
    auth_runtime: AuthSessionRuntime,
) -> APIRouter:
    router = APIRouter(prefix="/v1/garcom", tags=["garcom-web"])
    app_garcom = AplicacaoGarcomV1(session_factory)
    app_fechamento = AplicacaoFechamentoGarcomV1(session_factory)
    app_salao = AplicacaoSalaoV1(session_factory)

    def contexto_request(request: Request) -> ContextoExecucao:
        with session_factory() as session:
            return _contexto(
                request,
                session,
                auth_runtime=auth_runtime,
            )

    @router.get("/painel")
    def painel(request: Request) -> dict[str, object] | JSONResponse:
        try:
            with session_factory() as session:
                contexto = _contexto(
                    request,
                    session,
                    auth_runtime=auth_runtime,
                )
                item = ServicoGarcom(
                    RepositorioSalaoSQLAlchemy(session),
                    RepositorioKDSSQLAlchemy(session),
                ).listar_painel(contexto)
                return {
                    "papel": item.papel,
                    "kds_degradado": item.kds_degradado,
                    "atualizado_em": item.atualizado_em.isoformat(),
                    "mesas": [
                        {
                            "id": mesa.mesa_id,
                            "codigo": mesa.codigo,
                            "nome": mesa.nome,
                            "capacidade": mesa.capacidade,
                            "status": mesa.status.upper(),
                            "versao": mesa.versao,
                            "disponivel_para_abertura": (
                                mesa.disponivel_para_abertura
                            ),
                        }
                        for mesa in item.mesas
                    ],
                    "comandas": [
                        {
                            "id": comanda.comanda_id,
                            "mesa_id": comanda.mesa_id,
                            "numero": comanda.numero,
                            "status": comanda.status.upper(),
                            "responsavel_id": comanda.responsavel_id,
                            "total": str(comanda.total),
                            "saldo": str(comanda.saldo),
                            "versao": comanda.versao,
                            "propria": comanda.propria,
                        }
                        for comanda in item.comandas
                    ],
                    "alertas_prontos": [
                        {
                            "producao_id": alerta.producao_id,
                            "pedido_id": alerta.pedido_id,
                            "setor_nome": alerta.setor_nome,
                            "comanda_id": alerta.comanda_id,
                            "comanda_numero": alerta.comanda_numero,
                            "mesa_id": alerta.mesa_id,
                            "mesa_codigo": alerta.mesa_codigo,
                            "pronta_em": alerta.pronta_em.isoformat(),
                            "versao": alerta.versao,
                        }
                        for alerta in item.alertas_prontos
                    ],
                }
        except Exception as exc:  # noqa: BLE001
            return _erro_http(exc)

    @router.post("/mesas/{mesa_id}/comandas")
    def abrir_comanda(
        mesa_id: str,
        payload: AbrirComandaIn,
        request: Request,
        idempotency_key: str = Header(
            ...,
            alias="Idempotency-Key",
            min_length=1,
            max_length=128,
        ),
    ) -> dict[str, object] | JSONResponse:
        try:
            contexto = contexto_request(request)
            comanda = app_garcom.abrir_comanda(
                contexto,
                mesa_id=mesa_id,
                expected_mesa_version=payload.versao,
                numero=payload.numero,
                idempotency_key=idempotency_key,
            )
            return {"comanda": _comanda_dict(comanda)}
        except Exception as exc:  # noqa: BLE001
            return _erro_http(exc)

    @router.post("/comandas/{comanda_id}/solicitar-conta")
    def solicitar_conta(
        comanda_id: str,
        payload: MutacaoVersionadaIn,
        request: Request,
        idempotency_key: str = Header(
            ...,
            alias="Idempotency-Key",
            min_length=1,
            max_length=128,
        ),
    ) -> dict[str, object] | JSONResponse:
        try:
            contexto = contexto_request(request)
            comanda = app_garcom.solicitar_conta(
                contexto,
                comanda_id=comanda_id,
                expected_version=payload.versao,
                idempotency_key=idempotency_key,
            )
            return {"comanda": _comanda_dict(comanda)}
        except Exception as exc:  # noqa: BLE001
            return _erro_http(exc)

    @router.post("/comandas/{comanda_id}/retomar-consumo")
    def retomar_consumo(
        comanda_id: str,
        payload: MutacaoVersionadaIn,
        request: Request,
        idempotency_key: str = Header(
            ...,
            alias="Idempotency-Key",
            min_length=1,
            max_length=128,
        ),
    ) -> dict[str, object] | JSONResponse:
        try:
            contexto = contexto_request(request)
            if app_fechamento.demonstrativo(
                contexto,
                comanda_id=comanda_id,
            ).consolidado:
                raise ErroSalao("fechamento_ja_consolidado")
            comanda = app_garcom.retomar_consumo(
                contexto,
                comanda_id=comanda_id,
                expected_version=payload.versao,
                idempotency_key=idempotency_key,
            )
            return {"comanda": _comanda_dict(comanda)}
        except Exception as exc:  # noqa: BLE001
            return _erro_http(exc)

    @router.get("/configuracao-fechamento")
    def obter_configuracao(
        request: Request,
    ) -> dict[str, object] | JSONResponse:
        try:
            return _config_dict(
                app_fechamento.obter_configuracao(
                    contexto_request(request)
                )
            )
        except Exception as exc:  # noqa: BLE001
            return _erro_http(exc)

    @router.put("/configuracao-fechamento")
    def salvar_configuracao(
        payload: ConfiguracaoFechamentoIn,
        request: Request,
    ) -> dict[str, object] | JSONResponse:
        try:
            return _config_dict(
                app_fechamento.salvar_configuracao(
                    contexto_request(request),
                    modo_recebimento=payload.modo_recebimento,
                    couvert_ativado=payload.couvert_ativado,
                    couvert_valor=payload.couvert_valor,
                    expected_version=payload.versao,
                )
            )
        except Exception as exc:  # noqa: BLE001
            return _erro_http(exc)

    @router.get("/comandas/{comanda_id}/demonstrativo")
    def demonstrativo(
        comanda_id: str,
        request: Request,
        incluir_taxa_servico: bool = True,
    ) -> dict[str, object] | JSONResponse:
        try:
            return _demonstrativo_dict(
                app_fechamento.demonstrativo(
                    contexto_request(request),
                    comanda_id=comanda_id,
                    incluir_taxa_servico=incluir_taxa_servico,
                )
            )
        except Exception as exc:  # noqa: BLE001
            return _erro_http(exc)

    @router.post("/comandas/{comanda_id}/componentes")
    def consolidar_componentes(
        comanda_id: str,
        payload: ComponentesFechamentoIn,
        request: Request,
        idempotency_key: str = Header(
            ...,
            alias="Idempotency-Key",
            min_length=1,
            max_length=128,
        ),
    ) -> dict[str, object] | JSONResponse:
        try:
            return _demonstrativo_dict(
                app_fechamento.consolidar_componentes(
                    contexto_request(request),
                    comanda_id=comanda_id,
                    incluir_taxa_servico=payload.incluir_taxa_servico,
                    expected_version=payload.versao,
                    idempotency_key=idempotency_key,
                )
            )
        except Exception as exc:  # noqa: BLE001
            return _erro_http(exc)

    @router.post("/comandas/{comanda_id}/destino")
    def definir_destino(
        comanda_id: str,
        payload: DestinoRecebimentoIn,
        request: Request,
        idempotency_key: str = Header(
            ...,
            alias="Idempotency-Key",
            min_length=1,
            max_length=128,
        ),
    ) -> dict[str, str] | JSONResponse:
        try:
            destino = app_fechamento.definir_destino(
                contexto_request(request),
                comanda_id=comanda_id,
                destino=payload.destino,
                expected_version=payload.versao,
                idempotency_key=idempotency_key,
            )
            return {"destino": destino.value}
        except Exception as exc:  # noqa: BLE001
            return _erro_http(exc)

    @router.post("/comandas/{comanda_id}/divisao")
    def definir_divisao(
        comanda_id: str,
        payload: DivisaoIn,
        request: Request,
        idempotency_key: str = Header(
            ...,
            alias="Idempotency-Key",
            min_length=1,
            max_length=128,
        ),
    ) -> dict[str, object] | JSONResponse:
        try:
            comanda, parcelas = app_salao.definir_divisao_pagamento(
                contexto_request(request),
                comanda_id=comanda_id,
                expected_version=payload.versao,
                idempotency_key=idempotency_key,
                divisoes=tuple(
                    (
                        parcela.metodo,
                        parcela.valor,
                        parcela.participante_id,
                    )
                    for parcela in payload.parcelas
                ),
            )
            return {
                "comanda": _comanda_dict(comanda),
                "parcelas": [
                    {
                        "id": parcela.parcela_id,
                        "metodo": parcela.metodo.value,
                        "valor": str(parcela.valor),
                        "participante_id": parcela.participante_id,
                        "ordem": parcela.ordem,
                    }
                    for parcela in parcelas
                ],
            }
        except Exception as exc:  # noqa: BLE001
            return _erro_http(exc)

    @router.post("/comandas/{comanda_id}/pagamentos")
    def criar_pagamento(
        comanda_id: str,
        payload: CriarPagamentoIn,
        request: Request,
        idempotency_key: str = Header(
            ...,
            alias="Idempotency-Key",
            min_length=1,
            max_length=128,
        ),
    ) -> dict[str, object] | JSONResponse:
        try:
            resultado = app_salao.criar_pagamento_canonico(
                contexto_request(request),
                pagamento_id=payload.pagamento_id,
                pedido_id=payload.pedido_id,
                comanda_id=comanda_id,
                metodo=payload.metodo,
                valor=payload.valor,
                idempotency_key=idempotency_key,
                provedor=payload.provedor,
            )
            return _pagamento_dict(resultado)
        except Exception as exc:  # noqa: BLE001
            return _erro_http(exc)

    @router.post(
        "/comandas/{comanda_id}/pagamentos/{pagamento_id}/confirmar"
    )
    def confirmar_pagamento(
        comanda_id: str,
        pagamento_id: str,
        payload: ConfirmarPagamentoIn,
        request: Request,
        idempotency_key: str = Header(
            ...,
            alias="Idempotency-Key",
            min_length=1,
            max_length=128,
        ),
    ) -> dict[str, object] | JSONResponse:
        try:
            resultado = app_salao.confirmar_pagamento_canonico(
                contexto_request(request),
                pagamento_id=pagamento_id,
                comanda_id=comanda_id,
                metodo=payload.metodo,
                valor=payload.valor,
                expected_payment_version=payload.versao_pagamento,
                idempotency_key=idempotency_key,
                referencia_externa=payload.referencia_externa,
            )
            return _pagamento_dict(resultado)
        except Exception as exc:  # noqa: BLE001
            return _erro_http(exc)

    @router.post(
        "/comandas/{comanda_id}/pagamentos/{pagamento_id}/aplicar"
    )
    def aplicar_pagamento(
        comanda_id: str,
        pagamento_id: str,
        payload: RegistrarPagamentoIn,
        request: Request,
        idempotency_key: str = Header(
            ...,
            alias="Idempotency-Key",
            min_length=1,
            max_length=128,
        ),
    ) -> dict[str, object] | JSONResponse:
        try:
            comanda = app_salao.registrar_pagamento_confirmado(
                contexto_request(request),
                pagamento_id=pagamento_id,
                comanda_id=comanda_id,
                metodo=payload.metodo,
                valor=payload.valor,
                expected_version=payload.versao,
                idempotency_key=idempotency_key,
            )
            return {"comanda": _comanda_dict(comanda)}
        except Exception as exc:  # noqa: BLE001
            return _erro_http(exc)

    @router.post("/comandas/{comanda_id}/fechar")
    def fechar_comanda(
        comanda_id: str,
        payload: MutacaoVersionadaIn,
        request: Request,
        idempotency_key: str = Header(
            ...,
            alias="Idempotency-Key",
            min_length=1,
            max_length=128,
        ),
    ) -> dict[str, object] | JSONResponse:
        try:
            contexto = contexto_request(request)
            with session_factory() as session:
                sala = RepositorioSalaoSQLAlchemy(session)
                pedidos = sala.listar_pedidos(
                    contexto.tenant_id,
                    contexto.unidade_id,
                    comanda_id,
                )
                pedido_ids = {pedido.pedido_id for pedido in pedidos}
                ativos = RepositorioKDSSQLAlchemy(session).listar_fila(
                    contexto.tenant_id,
                    contexto.unidade_id,
                )
                pedidos_resolvidos = not any(
                    producao.pedido_id in pedido_ids
                    for producao, _setor in ativos
                )
            comanda = app_salao.fechar_comanda(
                contexto,
                comanda_id=comanda_id,
                expected_version=payload.versao,
                idempotency_key=idempotency_key,
                pedidos_resolvidos=pedidos_resolvidos,
            )
            return {"comanda": _comanda_dict(comanda)}
        except Exception as exc:  # noqa: BLE001
            return _erro_http(exc)

    return router
