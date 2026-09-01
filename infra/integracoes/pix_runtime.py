"""Orquestração do Pix comercial pelo Control Plane da V1.

Este módulo não lê credenciais globais, não escolhe silenciosamente entre múltiplos
provedores e não executa I/O por conta própria. A fábrica já autenticada e isolada
por tenant/unidade resolve o adapter homologado; os testes podem injetar adapters
falsos sem movimentação financeira real.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from core.dominio.dinheiro import Dinheiro
from core.integracoes.modelos import ConfiguracaoServicoExterno, ErroConfiguracaoServico
from core.pagamentos.pagbank import ClientePagBank
from core.seguranca.contexto import ContextoExecucao


class FabricaPixRuntime(Protocol):
    def pagbank(self, *, contexto: ContextoExecucao, configuracao_id: str): ...

    def mercado_pago(self, *, contexto: ContextoExecucao, configuracao_id: str): ...


class RepositorioPixRuntime(Protocol):
    def listar(
        self, *, tenant_id: str, unidade_id: str
    ) -> tuple[ConfiguracaoServicoExterno, ...]: ...


@dataclass(frozen=True, kw_only=True)
class DadosPagadorPix:
    nome: str
    email: str
    documento: str = ""


@dataclass(frozen=True, kw_only=True)
class CobrancaPixRuntime:
    provedor: str
    id_externo: str
    status: str
    valor: Decimal
    pix_copia_cola: str | None
    qr_code_url: str | None = None
    qr_code_base64: str | None = None

    @property
    def paga(self) -> bool:
        return self.status.strip().casefold() in {
            "pago",
            "paid",
            "approved",
            "aprovado",
            "autorizado",
        }


def selecionar_integracao_pix(
    configuracoes: Sequence[ConfiguracaoServicoExterno],
) -> ConfiguracaoServicoExterno:
    candidatas = tuple(
        config
        for config in configuracoes
        if config.servico == "pagamentos.pix"
        and config.provedor in {"pagbank", "mercado_pago"}
        and config.habilitada
        and config.homologada
    )
    if not candidatas:
        raise ErroConfiguracaoServico("pix_sem_provedor_homologado")
    if len(candidatas) > 1:
        raise ErroConfiguracaoServico("pix_multiplos_provedores_homologados")
    return candidatas[0]


def criar_cobranca_pix(
    *,
    fabrica: FabricaPixRuntime,
    contexto: ContextoExecucao,
    configuracao: ConfiguracaoServicoExterno,
    pagamento_id: str,
    valor: Decimal,
    idempotency_key: str,
    pagador: DadosPagadorPix,
) -> CobrancaPixRuntime:
    if valor <= 0:
        raise ValueError("valor_pix_invalido")
    if not pagamento_id.strip() or not idempotency_key.strip():
        raise ValueError("identificador_pix_invalido")

    if configuracao.provedor == "pagbank":
        adapter = fabrica.pagbank(
            contexto=contexto,
            configuracao_id=configuracao.configuracao_id,
        )
        cobranca = adapter.criar_pix(
            pagamento_id=pagamento_id,
            valor=Dinheiro(valor),
            idempotency_key=idempotency_key,
            cliente=ClientePagBank(
                nome=pagador.nome,
                email=pagador.email,
                tax_id=pagador.documento,
            ),
        )
        exibicao = dict(cobranca.payload_exibicao)
        return CobrancaPixRuntime(
            provedor="pagbank",
            id_externo=cobranca.id_externo,
            status=cobranca.status,
            valor=cobranca.valor.valor,
            pix_copia_cola=exibicao.get("pix_copia_cola"),
            qr_code_url=exibicao.get("qr_code_png_url"),
        )

    if configuracao.provedor == "mercado_pago":
        if not pagador.email.strip():
            raise ValueError("email_pagador_pix_obrigatorio")
        adapter = fabrica.mercado_pago(
            contexto=contexto,
            configuracao_id=configuracao.configuracao_id,
        )
        cobranca = adapter.criar_pix(
            valor=valor,
            email_pagador=pagador.email,
            referencia_externa=pagamento_id,
            idempotency_key=idempotency_key,
        )
        return CobrancaPixRuntime(
            provedor="mercado_pago",
            id_externo=cobranca.pagamento_id,
            status=cobranca.status,
            valor=cobranca.valor,
            pix_copia_cola=cobranca.pix_copia_cola,
            qr_code_base64=cobranca.qr_code_base64,
            qr_code_url=cobranca.ticket_url,
        )

    raise ErroConfiguracaoServico("provedor_pix_nao_suportado")


def consultar_cobranca_pix(
    *,
    fabrica: FabricaPixRuntime,
    contexto: ContextoExecucao,
    configuracao: ConfiguracaoServicoExterno,
    id_externo: str,
) -> CobrancaPixRuntime:
    identificador = id_externo.strip()
    if not identificador:
        raise ValueError("identificador_pix_invalido")

    if configuracao.provedor == "pagbank":
        adapter = fabrica.pagbank(
            contexto=contexto,
            configuracao_id=configuracao.configuracao_id,
        )
        cobranca = adapter.consultar_transacao(identificador)
        if cobranca is None:
            raise ErroConfiguracaoServico("cobranca_pix_nao_encontrada")
        exibicao = dict(cobranca.payload_exibicao)
        return CobrancaPixRuntime(
            provedor="pagbank",
            id_externo=cobranca.id_externo,
            status=cobranca.status,
            valor=cobranca.valor.valor,
            pix_copia_cola=exibicao.get("pix_copia_cola"),
            qr_code_url=exibicao.get("qr_code_png_url"),
        )

    if configuracao.provedor == "mercado_pago":
        adapter = fabrica.mercado_pago(
            contexto=contexto,
            configuracao_id=configuracao.configuracao_id,
        )
        cobranca = adapter.consultar_pagamento(identificador)
        return CobrancaPixRuntime(
            provedor="mercado_pago",
            id_externo=cobranca.pagamento_id,
            status=cobranca.status,
            valor=cobranca.valor,
            pix_copia_cola=cobranca.pix_copia_cola,
            qr_code_base64=cobranca.qr_code_base64,
            qr_code_url=cobranca.ticket_url,
        )

    raise ErroConfiguracaoServico("provedor_pix_nao_suportado")


def _configuracao_pix_do_contexto(
    *,
    repositorio: RepositorioPixRuntime,
    contexto: ContextoExecucao,
) -> ConfiguracaoServicoExterno:
    configuracoes = repositorio.listar(
        tenant_id=contexto.tenant_id,
        unidade_id=contexto.unidade_id,
    )
    return selecionar_integracao_pix(configuracoes)


def criar_cobranca_pix_por_control_plane(
    *,
    repositorio: RepositorioPixRuntime,
    fabrica: FabricaPixRuntime,
    contexto: ContextoExecucao,
    pagamento_id: str,
    valor: Decimal,
    idempotency_key: str,
    pagador: DadosPagadorPix,
) -> CobrancaPixRuntime:
    """Resolve a configuração Pix do escopo autenticado e cria a cobrança."""

    configuracao = _configuracao_pix_do_contexto(
        repositorio=repositorio,
        contexto=contexto,
    )
    return criar_cobranca_pix(
        fabrica=fabrica,
        contexto=contexto,
        configuracao=configuracao,
        pagamento_id=pagamento_id,
        valor=valor,
        idempotency_key=idempotency_key,
        pagador=pagador,
    )


def consultar_cobranca_pix_por_control_plane(
    *,
    repositorio: RepositorioPixRuntime,
    fabrica: FabricaPixRuntime,
    contexto: ContextoExecucao,
    provedor: str,
    id_externo: str,
) -> CobrancaPixRuntime:
    """Consulta a cobrança somente pelo provedor Pix ativo do escopo autenticado."""

    configuracao = _configuracao_pix_do_contexto(
        repositorio=repositorio,
        contexto=contexto,
    )
    if configuracao.provedor != provedor.strip().casefold():
        raise ErroConfiguracaoServico("provedor_pix_divergente")
    return consultar_cobranca_pix(
        fabrica=fabrica,
        contexto=contexto,
        configuracao=configuracao,
        id_externo=id_externo,
    )

