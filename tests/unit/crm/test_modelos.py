from datetime import datetime, timedelta, timezone

import pytest

from core.crm.erros import ErroCRM
from core.crm.flags import crm_v1_enabled
from core.crm.modelos import (
    BaseLegalMarketing,
    CanalMarketing,
    ClienteMarketplaceRestrito,
    ConsentimentoMarketing,
    ContatoCRM,
    FinalidadeMarketing,
    StatusConsentimento,
)
from core.marketplaces.modelos import PlataformaMarketplace


def test_flag_crm_e_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FM_AI_TEST_MODE", raising=False)
    monkeypatch.setenv("FM_AI_CRM_V1", "1")
    assert crm_v1_enabled() is False
    monkeypatch.setenv("FM_AI_TEST_MODE", "1")
    assert crm_v1_enabled() is True


def test_contato_exige_referencia_segura_e_nao_pii_crua() -> None:
    with pytest.raises(ErroCRM, match="contato_deve_ser_referencia_segura"):
        ContatoCRM(CanalMarketing.WHATSAPP, "raw-whatsapp-value")
    contato = ContatoCRM(CanalMarketing.WHATSAPP, "contact://cliente-1/whatsapp")
    assert contato.referencia == "contact://cliente-1/whatsapp"


def test_cliente_marketplace_armazena_hash_e_ttl() -> None:
    agora = datetime.now(timezone.utc)
    cliente = ClienteMarketplaceRestrito(
        marketplace_cliente_id="mkt-1",
        tenant_id="tenant-1",
        unidade_id="unidade-1",
        integracao_id="int-1",
        plataforma=PlataformaMarketplace.IFOOD,
        id_externo_hash="a" * 64,
        criado_em=agora,
        expira_em=agora + timedelta(days=90),
        apelido="  Cliente   iFood  ",
    )
    assert cliente.id_externo_hash == "a" * 64
    assert cliente.apelido == "Cliente iFood"


def test_cliente_marketplace_rejeita_identidade_nao_hash() -> None:
    agora = datetime.now(timezone.utc)
    with pytest.raises(ErroCRM, match="hash_identidade_marketplace_invalido"):
        ClienteMarketplaceRestrito(
            marketplace_cliente_id="mkt-1",
            tenant_id="tenant-1",
            unidade_id="unidade-1",
            integracao_id="int-1",
            plataforma=PlataformaMarketplace.IFOOD,
            id_externo_hash="id-externo-cru",
            criado_em=agora,
            expira_em=agora + timedelta(days=1),
        )


def test_consentimento_concedido_exige_prova_e_timestamp_coerente() -> None:
    agora = datetime.now(timezone.utc)
    consentimento = ConsentimentoMarketing(
        consentimento_id="cons-1",
        tenant_id="tenant-1",
        unidade_id="unidade-1",
        cliente_id="cliente-1",
        canal=CanalMarketing.WHATSAPP,
        finalidade=FinalidadeMarketing.PROMOCOES,
        status=StatusConsentimento.CONCEDIDO,
        base_legal=BaseLegalMarketing.CONSENTIMENTO,
        texto_versao="marketing-v1",
        origem="self_service",
        prova_hash="b" * 64,
        ocorrido_em=agora,
        idempotency_key="idem-1",
        correlation_id="corr-1",
        concedido_em=agora,
    )
    assert consentimento.revogado_em is None
    with pytest.raises(ErroCRM, match="consentimento_concedido_inconsistente"):
        ConsentimentoMarketing(
            consentimento_id="cons-2",
            tenant_id="tenant-1",
            unidade_id="unidade-1",
            cliente_id="cliente-1",
            canal=CanalMarketing.WHATSAPP,
            finalidade=FinalidadeMarketing.PROMOCOES,
            status=StatusConsentimento.CONCEDIDO,
            base_legal=BaseLegalMarketing.CONSENTIMENTO,
            texto_versao="marketing-v1",
            origem="self_service",
            prova_hash="c" * 64,
            ocorrido_em=agora,
            idempotency_key="idem-2",
            correlation_id="corr-2",
        )


def test_revogacao_exige_timestamp_de_revogacao() -> None:
    agora = datetime.now(timezone.utc)
    with pytest.raises(ErroCRM, match="revogacao_sem_timestamp"):
        ConsentimentoMarketing(
            consentimento_id="cons-3",
            tenant_id="tenant-1",
            unidade_id="unidade-1",
            cliente_id="cliente-1",
            canal=CanalMarketing.EMAIL,
            finalidade=FinalidadeMarketing.FIDELIDADE,
            status=StatusConsentimento.REVOGADO,
            base_legal=BaseLegalMarketing.CONSENTIMENTO,
            texto_versao="marketing-v1",
            origem="self_service",
            prova_hash="d" * 64,
            ocorrido_em=agora,
            idempotency_key="idem-3",
            correlation_id="corr-3",
        )
