from datetime import datetime, timezone
from decimal import Decimal

import pytest

from core.dominio.dinheiro import Dinheiro
from core.integracoes.modelos import AmbienteIntegracao, ConfiguracaoServicoExterno, ErroConfiguracaoServico
from core.pagamentos.adapters import CobrancaProvedor
from core.pagamentos.pagbank import ClientePagBank
from core.seguranca.contexto import ContextoExecucao
from infra.integracoes.pix_runtime import (
    CobrancaPixRuntime,
    DadosPagadorPix,
    criar_cobranca_pix,
    selecionar_integracao_pix,
)


def _config(*, provedor: str, habilitada: bool = True, homologada: bool = True):
    evidencia = "evidencia-real-ref" if homologada else None
    return ConfiguracaoServicoExterno(
        configuracao_id=f"pagamentos.pix--{provedor}",
        tenant_id="tenant-a",
        unidade_id="unidade-a",
        servico="pagamentos.pix",
        provedor=provedor,
        conta_externa="conta-a",
        ambiente=AmbienteIntegracao.HOMOLOGACAO,
        parametros_publicos=(("notification_url", "https://example.invalid/hook"),),
        finalidades_credenciais=(),
        habilitada=habilitada,
        homologada=homologada,
        evidencia_homologacao_ref=evidencia,
        versao=1,
        atualizado_por="teste",
        correlation_id="corr-1",
        atualizado_em=datetime.now(timezone.utc),
    )


class _PagBankFake:
    def criar_pix(self, *, pagamento_id, valor, idempotency_key, cliente: ClientePagBank):
        assert pagamento_id == "pedido-1"
        assert valor == Dinheiro(Decimal("25.50"))
        assert idempotency_key == "idem-1"
        assert cliente.email == "cliente@example.com"
        assert cliente.tax_id == "12345678901"
        return CobrancaProvedor(
            "ORDE_TESTE",
            "pendente",
            valor,
            (("pix_copia_cola", "000201-pagbank"), ("qr_code_png_url", "https://example.invalid/qr.png")),
        )


class _MercadoPagoCobranca:
    pagamento_id = "mp-123"
    status = "pending"
    pix_copia_cola = "000201-mp"
    qr_code_base64 = "base64-qr"
    ticket_url = "https://example.invalid/ticket"


class _MercadoPagoFake:
    def criar_pix(self, *, valor, email_pagador, referencia_externa, idempotency_key):
        assert valor == Decimal("31.90")
        assert email_pagador == "cliente@example.com"
        assert referencia_externa == "pedido-2"
        assert idempotency_key == "idem-2"
        return _MercadoPagoCobranca()


class _FabricaFake:
    def __init__(self):
        self.pagbank_calls = 0
        self.mercado_pago_calls = 0

    def pagbank(self, *, contexto, configuracao_id):
        self.pagbank_calls += 1
        assert contexto.tenant_id == "tenant-a"
        assert contexto.unidade_id == "unidade-a"
        assert configuracao_id == "pagamentos.pix--pagbank"
        return _PagBankFake()

    def mercado_pago(self, *, contexto, configuracao_id):
        self.mercado_pago_calls += 1
        assert contexto.tenant_id == "tenant-a"
        assert contexto.unidade_id == "unidade-a"
        assert configuracao_id == "pagamentos.pix--mercado_pago"
        return _MercadoPagoFake()


def _contexto():
    return ContextoExecucao(
        tenant_id="tenant-a",
        unidade_id="unidade-a",
        usuario_id="usuario-a",
        correlation_id="corr-runtime",
        origem="teste.pix_runtime",
    )


def test_seleciona_somente_um_provedor_pix_habilitado_e_homologado():
    selecionada = selecionar_integracao_pix(
        (_config(provedor="pagbank"), _config(provedor="mercado_pago", homologada=False))
    )
    assert selecionada.provedor == "pagbank"


def test_falha_fechado_sem_provedor_pix_homologado():
    with pytest.raises(ErroConfiguracaoServico, match="pix_sem_provedor_homologado"):
        selecionar_integracao_pix((_config(provedor="pagbank", habilitada=False),))


def test_falha_fechado_com_dois_provedores_pix_homologados():
    with pytest.raises(ErroConfiguracaoServico, match="pix_multiplos_provedores_homologados"):
        selecionar_integracao_pix((_config(provedor="pagbank"), _config(provedor="mercado_pago")))


def test_cria_pix_pagbank_por_adapter_injetado_sem_io_real():
    fabrica = _FabricaFake()
    resultado = criar_cobranca_pix(
        fabrica=fabrica,
        contexto=_contexto(),
        configuracao=_config(provedor="pagbank"),
        pagamento_id="pedido-1",
        valor=Decimal("25.50"),
        idempotency_key="idem-1",
        pagador=DadosPagadorPix(
            nome="Cliente Teste",
            email="cliente@example.com",
            documento="12345678901",
        ),
    )
    assert resultado == CobrancaPixRuntime(
        provedor="pagbank",
        id_externo="ORDE_TESTE",
        status="pendente",
        pix_copia_cola="000201-pagbank",
        qr_code_url="https://example.invalid/qr.png",
    )
    assert fabrica.pagbank_calls == 1
    assert fabrica.mercado_pago_calls == 0


def test_cria_pix_mercado_pago_por_adapter_injetado_sem_io_real():
    fabrica = _FabricaFake()
    resultado = criar_cobranca_pix(
        fabrica=fabrica,
        contexto=_contexto(),
        configuracao=_config(provedor="mercado_pago"),
        pagamento_id="pedido-2",
        valor=Decimal("31.90"),
        idempotency_key="idem-2",
        pagador=DadosPagadorPix(
            nome="Cliente Teste",
            email="cliente@example.com",
        ),
    )
    assert resultado == CobrancaPixRuntime(
        provedor="mercado_pago",
        id_externo="mp-123",
        status="pending",
        pix_copia_cola="000201-mp",
        qr_code_url="https://example.invalid/ticket",
        qr_code_base64="base64-qr",
    )
    assert fabrica.mercado_pago_calls == 1
    assert fabrica.pagbank_calls == 0
