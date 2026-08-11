from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from core.crm.erros import ErroCRM
from core.crm.modelos import (
    CanalMarketing,
    ContatoCRM,
    FinalidadeMarketing,
    OrigemClienteCRM,
    StatusConsentimento,
    TipoBeneficioCRM,
)
from core.crm.runtime_teste import RuntimeCRMTeste
from core.marketplaces.modelos import PlataformaMarketplace

TENANT = "tenant-1"
UNIDADE = "unidade-1"
CLIENTE = "cliente-1"


def _contato(canal: CanalMarketing = CanalMarketing.WHATSAPP) -> ContatoCRM:
    return ContatoCRM(canal, f"contact://{CLIENTE}/{canal.value}")


def _registrar_regular(runtime: RuntimeCRMTeste, *, cliente_id: str = CLIENTE) -> None:
    runtime.servico.registrar_cliente(
        cliente_id=cliente_id,
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        origem=OrigemClienteCRM.DELIVERY_PROPRIO,
        contatos=(ContatoCRM(CanalMarketing.WHATSAPP, f"contact://{cliente_id}/whatsapp"),),
    )


def _consentir(
    runtime: RuntimeCRMTeste,
    *,
    cliente_id: str = CLIENTE,
    idem: str = "consent-1",
    agora: datetime | None = None,
):
    return runtime.servico.conceder_consentimento(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        cliente_id=cliente_id,
        canal=CanalMarketing.WHATSAPP,
        finalidade=FinalidadeMarketing.PROMOCOES,
        texto_versao="marketing-v1",
        origem="self_service",
        prova=f"prova:{idem}",
        idempotency_key=idem,
        correlation_id=f"corr:{idem}",
        agora=agora,
    )


def test_marketing_e_negado_por_padrao() -> None:
    runtime = RuntimeCRMTeste()
    _registrar_regular(runtime)
    assert runtime.servico.pode_enviar_marketing(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        cliente_id=CLIENTE,
        canal=CanalMarketing.WHATSAPP,
        finalidade=FinalidadeMarketing.PROMOCOES,
    ) is False
    assert runtime.servico.listar_elegiveis(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        canal=CanalMarketing.WHATSAPP,
        finalidade=FinalidadeMarketing.PROMOCOES,
    ) == ()


def test_consentimento_libera_apenas_canal_e_finalidade_exatos() -> None:
    runtime = RuntimeCRMTeste()
    _registrar_regular(runtime)
    consentimento = _consentir(runtime)
    assert consentimento.status is StatusConsentimento.CONCEDIDO
    assert runtime.servico.pode_enviar_marketing(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        cliente_id=CLIENTE,
        canal=CanalMarketing.WHATSAPP,
        finalidade=FinalidadeMarketing.PROMOCOES,
    ) is True
    assert runtime.servico.pode_enviar_marketing(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        cliente_id=CLIENTE,
        canal=CanalMarketing.WHATSAPP,
        finalidade=FinalidadeMarketing.FIDELIDADE,
    ) is False
    assert runtime.servico.pode_enviar_marketing(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        cliente_id=CLIENTE,
        canal=CanalMarketing.EMAIL,
        finalidade=FinalidadeMarketing.PROMOCOES,
    ) is False


def test_outbox_e_auditoria_nao_carregam_prova_ou_contato_cru() -> None:
    runtime = RuntimeCRMTeste()
    _registrar_regular(runtime)
    _consentir(runtime)
    pendentes = runtime.outbox.listar_pendentes()
    assert len(pendentes) == 1
    mensagem = pendentes[0].mensagem.para_dict()
    assert mensagem["event_type"] == "cliente.consentiu_marketing"
    payload = mensagem["payload"]
    assert set(payload) == {
        "cliente_id",
        "canal",
        "finalidade",
        "texto_versao",
        "status",
    }
    serializado = repr(mensagem) + repr(runtime.auditoria.eventos)
    assert "prova:consent-1" not in serializado
    assert "contact://" not in serializado


def test_revogacao_imediata_remove_elegibilidade_e_bloqueia_envio() -> None:
    runtime = RuntimeCRMTeste()
    _registrar_regular(runtime)
    _consentir(runtime)
    elegiveis_antes = runtime.servico.listar_elegiveis(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        canal=CanalMarketing.WHATSAPP,
        finalidade=FinalidadeMarketing.PROMOCOES,
    )
    assert elegiveis_antes == (CLIENTE,)
    runtime.servico.revogar_consentimento(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        cliente_id=CLIENTE,
        canal=CanalMarketing.WHATSAPP,
        finalidade=FinalidadeMarketing.PROMOCOES,
        origem="self_service",
        prova="pedido-de-optout",
        idempotency_key="revoke-1",
        correlation_id="corr-revoke-1",
    )
    assert runtime.servico.pode_enviar_marketing(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        cliente_id=CLIENTE,
        canal=CanalMarketing.WHATSAPP,
        finalidade=FinalidadeMarketing.PROMOCOES,
    ) is False
    assert runtime.servico.listar_elegiveis(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        canal=CanalMarketing.WHATSAPP,
        finalidade=FinalidadeMarketing.PROMOCOES,
    ) == ()
    resultado = runtime.servico.despachar_marketing(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        cliente_id=elegiveis_antes[0],
        canal=CanalMarketing.WHATSAPP,
        finalidade=FinalidadeMarketing.PROMOCOES,
        campanha_ref="campanha://teste",
        idempotency_key="send-after-revoke",
        envio=runtime.envio,
    )
    assert resultado.enviado is False
    assert runtime.envio.envios == []
    assert runtime.outbox.listar_pendentes()[-1].mensagem.event_type == "cliente.cancelou_marketing"


def test_optout_sem_optin_anterior_tambem_suprime() -> None:
    runtime = RuntimeCRMTeste()
    _registrar_regular(runtime)
    revogacao = runtime.servico.revogar_consentimento(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        cliente_id=CLIENTE,
        canal=CanalMarketing.WHATSAPP,
        finalidade=FinalidadeMarketing.PROMOCOES,
        origem="self_service",
        prova="optout-sem-optin",
        idempotency_key="revoke-sem-optin",
        correlation_id="corr-revoke-sem-optin",
    )
    assert revogacao.status is StatusConsentimento.REVOGADO
    assert runtime.servico.pode_enviar_marketing(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        cliente_id=CLIENTE,
        canal=CanalMarketing.WHATSAPP,
        finalidade=FinalidadeMarketing.PROMOCOES,
    ) is False


def test_novo_optin_posterior_pode_reabilitar_de_forma_explicita() -> None:
    runtime = RuntimeCRMTeste()
    _registrar_regular(runtime)
    base = datetime(2026, 8, 11, 20, 0, tzinfo=timezone.utc)
    _consentir(runtime, idem="grant-old", agora=base)
    runtime.servico.revogar_consentimento(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        cliente_id=CLIENTE,
        canal=CanalMarketing.WHATSAPP,
        finalidade=FinalidadeMarketing.PROMOCOES,
        origem="self_service",
        prova="revogacao",
        idempotency_key="revoke-mid",
        correlation_id="corr-revoke-mid",
        agora=base + timedelta(minutes=1),
    )
    _consentir(runtime, idem="grant-new", agora=base + timedelta(minutes=2))
    assert runtime.servico.pode_enviar_marketing(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        cliente_id=CLIENTE,
        canal=CanalMarketing.WHATSAPP,
        finalidade=FinalidadeMarketing.PROMOCOES,
    ) is True


def test_evento_antigo_fora_de_ordem_nao_reabilita_apos_revogacao() -> None:
    runtime = RuntimeCRMTeste()
    _registrar_regular(runtime)
    base = datetime(2026, 8, 11, 20, 0, tzinfo=timezone.utc)
    runtime.servico.revogar_consentimento(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        cliente_id=CLIENTE,
        canal=CanalMarketing.WHATSAPP,
        finalidade=FinalidadeMarketing.PROMOCOES,
        origem="self_service",
        prova="revogacao-mais-nova",
        idempotency_key="revoke-newer",
        correlation_id="corr-revoke-newer",
        agora=base + timedelta(minutes=2),
    )
    _consentir(runtime, idem="grant-late-arrival", agora=base)
    atual = runtime.consentimentos.atual(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        cliente_id=CLIENTE,
        canal=CanalMarketing.WHATSAPP,
        finalidade=FinalidadeMarketing.PROMOCOES,
    )
    assert atual is not None
    assert atual.status is StatusConsentimento.REVOGADO


def test_cliente_marketplace_restrito_e_hash_hmac_sem_marketing() -> None:
    runtime = RuntimeCRMTeste()
    externo = "order-customer-external-abc"
    restrito = runtime.servico.registrar_cliente_marketplace_restrito(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        integracao_id="int-ifood-1",
        plataforma=PlataformaMarketplace.IFOOD,
        id_externo=externo,
        apelido="Cliente marketplace",
        idempotency_key="mkt-1",
    )
    assert restrito.id_externo_hash != externo
    assert len(restrito.id_externo_hash) == 64
    assert externo not in repr(restrito)
    assert runtime.servico.pode_enviar_marketing(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        cliente_id=restrito.marketplace_cliente_id,
        canal=CanalMarketing.WHATSAPP,
        finalidade=FinalidadeMarketing.PROMOCOES,
    ) is False


def test_conversao_marketplace_exige_optin_e_cria_cliente_regular() -> None:
    runtime = RuntimeCRMTeste()
    agora = datetime(2026, 8, 11, 20, 0, tzinfo=timezone.utc)
    restrito = runtime.servico.registrar_cliente_marketplace_restrito(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        integracao_id="int-ifood-1",
        plataforma=PlataformaMarketplace.IFOOD,
        id_externo="external-customer-1",
        apelido=None,
        idempotency_key="mkt-convert",
        agora=agora,
    )
    resultado = runtime.servico.converter_cliente_marketplace(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        marketplace_cliente_id=restrito.marketplace_cliente_id,
        cliente_id=CLIENTE,
        contato=_contato(),
        finalidade=FinalidadeMarketing.PROMOCOES,
        texto_versao="marketing-v1",
        origem_consentimento="landing_page_propria",
        prova="checkbox-explicito-v1",
        idempotency_key="convert-1",
        correlation_id="corr-convert-1",
        agora=agora + timedelta(minutes=1),
    )
    assert resultado.cliente.origem is OrigemClienteCRM.MARKETPLACE_CONVERTIDO
    assert resultado.consentimento.status is StatusConsentimento.CONCEDIDO
    salvo = runtime.marketplace_clientes.obter(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        marketplace_cliente_id=restrito.marketplace_cliente_id,
    )
    assert salvo is not None
    assert salvo.convertido_cliente_id == CLIENTE
    assert runtime.servico.pode_enviar_marketing(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        cliente_id=CLIENTE,
        canal=CanalMarketing.WHATSAPP,
        finalidade=FinalidadeMarketing.PROMOCOES,
    ) is True


def test_conversao_expirada_e_bloqueada_e_expurgo_remove_temporario() -> None:
    runtime = RuntimeCRMTeste()
    base = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
    restrito = runtime.servico.registrar_cliente_marketplace_restrito(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        integracao_id="int-keeta-1",
        plataforma=PlataformaMarketplace.KEETA,
        id_externo="external-expired",
        apelido=None,
        idempotency_key="mkt-expired",
        ttl_dias=1,
        agora=base,
    )
    with pytest.raises(ErroCRM, match="cliente_marketplace_expirado"):
        runtime.servico.converter_cliente_marketplace(
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            marketplace_cliente_id=restrito.marketplace_cliente_id,
            cliente_id=CLIENTE,
            contato=_contato(),
            finalidade=FinalidadeMarketing.PROMOCOES,
            texto_versao="marketing-v1",
            origem_consentimento="landing_page_propria",
            prova="prova",
            idempotency_key="convert-expired",
            correlation_id="corr-expired",
            agora=base + timedelta(days=2),
        )
    assert runtime.servico.expurgar_marketplace_expirados(
        agora=base + timedelta(days=2)
    ) == 1
    assert runtime.marketplace_clientes.obter(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        marketplace_cliente_id=restrito.marketplace_cliente_id,
    ) is None


def test_escopo_multiempresa_e_fail_closed() -> None:
    runtime = RuntimeCRMTeste()
    _registrar_regular(runtime)
    _consentir(runtime)
    assert runtime.servico.pode_enviar_marketing(
        tenant_id="outro-tenant",
        unidade_id=UNIDADE,
        cliente_id=CLIENTE,
        canal=CanalMarketing.WHATSAPP,
        finalidade=FinalidadeMarketing.PROMOCOES,
    ) is False
    with pytest.raises(ErroCRM, match="recurso_indisponivel"):
        runtime.servico.revogar_consentimento(
            tenant_id="outro-tenant",
            unidade_id=UNIDADE,
            cliente_id=CLIENTE,
            canal=CanalMarketing.WHATSAPP,
            finalidade=FinalidadeMarketing.PROMOCOES,
            origem="self_service",
            prova="prova",
            idempotency_key="scope-revoke",
            correlation_id="scope-corr",
        )


def test_beneficio_de_conversao_exige_consentimento_e_e_idempotente() -> None:
    runtime = RuntimeCRMTeste()
    restrito = runtime.servico.registrar_cliente_marketplace_restrito(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        integracao_id="int-99-1",
        plataforma=PlataformaMarketplace.FOOD99,
        id_externo="external-99-1",
        apelido=None,
        idempotency_key="mkt-benefit",
    )
    runtime.servico.converter_cliente_marketplace(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        marketplace_cliente_id=restrito.marketplace_cliente_id,
        cliente_id=CLIENTE,
        contato=_contato(),
        finalidade=FinalidadeMarketing.PROMOCOES,
        texto_versao="marketing-v1",
        origem_consentimento="landing_page_propria",
        prova="optin-benefit",
        idempotency_key="convert-benefit",
        correlation_id="corr-convert-benefit",
    )
    primeiro = runtime.servico.emitir_beneficio_conversao(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        cliente_id=CLIENTE,
        canal=CanalMarketing.WHATSAPP,
        finalidade=FinalidadeMarketing.PROMOCOES,
        tipo=TipoBeneficioCRM.CUPOM,
        valor=Decimal("10"),
        idempotency_key="benefit-1",
        correlation_id="corr-benefit-1",
    )
    segundo = runtime.servico.emitir_beneficio_conversao(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        cliente_id=CLIENTE,
        canal=CanalMarketing.WHATSAPP,
        finalidade=FinalidadeMarketing.PROMOCOES,
        tipo=TipoBeneficioCRM.CUPOM,
        valor=Decimal("10"),
        idempotency_key="benefit-1",
        correlation_id="corr-benefit-1-retry",
    )
    assert primeiro == segundo
    runtime.servico.revogar_consentimento(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        cliente_id=CLIENTE,
        canal=CanalMarketing.WHATSAPP,
        finalidade=FinalidadeMarketing.PROMOCOES,
        origem="self_service",
        prova="optout-after-benefit",
        idempotency_key="revoke-after-benefit",
        correlation_id="corr-revoke-after-benefit",
    )
    with pytest.raises(ErroCRM, match="beneficio_conversao_sem_consentimento"):
        runtime.servico.emitir_beneficio_conversao(
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            cliente_id=CLIENTE,
            canal=CanalMarketing.WHATSAPP,
            finalidade=FinalidadeMarketing.PROMOCOES,
            tipo=TipoBeneficioCRM.CASHBACK,
            valor=Decimal("5"),
            idempotency_key="benefit-after-revoke",
            correlation_id="corr-benefit-after-revoke",
        )


def test_despacho_revalida_consentimento_no_momento_do_envio() -> None:
    runtime = RuntimeCRMTeste()
    _registrar_regular(runtime)
    _consentir(runtime)
    enviado = runtime.servico.despachar_marketing(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        cliente_id=CLIENTE,
        canal=CanalMarketing.WHATSAPP,
        finalidade=FinalidadeMarketing.PROMOCOES,
        campanha_ref="campanha://1",
        idempotency_key="send-1",
        envio=runtime.envio,
    )
    assert enviado.enviado is True
    assert len(runtime.envio.envios) == 1
    runtime.servico.revogar_consentimento(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        cliente_id=CLIENTE,
        canal=CanalMarketing.WHATSAPP,
        finalidade=FinalidadeMarketing.PROMOCOES,
        origem="self_service",
        prova="revogar-antes-segundo-envio",
        idempotency_key="revoke-before-send-2",
        correlation_id="corr-revoke-before-send-2",
    )
    bloqueado = runtime.servico.despachar_marketing(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        cliente_id=CLIENTE,
        canal=CanalMarketing.WHATSAPP,
        finalidade=FinalidadeMarketing.PROMOCOES,
        campanha_ref="campanha://2",
        idempotency_key="send-2",
        envio=runtime.envio,
    )
    assert bloqueado.enviado is False
    assert len(runtime.envio.envios) == 1


def test_idempotencia_consentimento_retorna_mesma_prova_e_conflito_falha() -> None:
    runtime = RuntimeCRMTeste()
    _registrar_regular(runtime)
    primeiro = _consentir(runtime, idem="idem-same")
    segundo = _consentir(runtime, idem="idem-same")
    assert primeiro == segundo
    with pytest.raises(ErroCRM, match="conflito_idempotencia_consentimento"):
        runtime.servico.conceder_consentimento(
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            cliente_id=CLIENTE,
            canal=CanalMarketing.WHATSAPP,
            finalidade=FinalidadeMarketing.PROMOCOES,
            texto_versao="marketing-v1",
            origem="self_service",
            prova="prova-diferente",
            idempotency_key="idem-same",
            correlation_id="corr-different",
        )


def test_resumo_funil_e_minimizado_e_idempotente() -> None:
    runtime = RuntimeCRMTeste()
    restrito = runtime.servico.registrar_cliente_marketplace_restrito(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        integracao_id="int-funnel",
        plataforma=PlataformaMarketplace.IFOOD,
        id_externo="external-funnel",
        apelido=None,
        idempotency_key="funnel-mkt",
    )
    runtime.servico.converter_cliente_marketplace(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        marketplace_cliente_id=restrito.marketplace_cliente_id,
        cliente_id=CLIENTE,
        contato=_contato(),
        finalidade=FinalidadeMarketing.PROMOCOES,
        texto_versao="marketing-v1",
        origem_consentimento="landing",
        prova="funnel-optin",
        idempotency_key="funnel-convert",
        correlation_id="corr-funnel-convert",
    )
    runtime.servico.emitir_beneficio_conversao(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        cliente_id=CLIENTE,
        canal=CanalMarketing.WHATSAPP,
        finalidade=FinalidadeMarketing.PROMOCOES,
        tipo=TipoBeneficioCRM.CASHBACK,
        valor=Decimal("3"),
        idempotency_key="funnel-benefit",
        correlation_id="corr-funnel-benefit",
    )
    runtime.servico.revogar_consentimento(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        cliente_id=CLIENTE,
        canal=CanalMarketing.WHATSAPP,
        finalidade=FinalidadeMarketing.PROMOCOES,
        origem="self_service",
        prova="funnel-optout",
        idempotency_key="funnel-optout",
        correlation_id="corr-funnel-optout",
    )
    resumo = runtime.servico.resumo_funil(tenant_id=TENANT, unidade_id=UNIDADE)
    assert resumo.marketplace_restritos == 1
    assert resumo.consentimentos_concedidos == 1
    assert resumo.convertidos == 1
    assert resumo.beneficios_emitidos == 1
    assert resumo.opt_outs == 1
