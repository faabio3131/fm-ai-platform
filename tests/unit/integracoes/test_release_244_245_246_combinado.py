"""Fitness de composição — PRs 244, 245 e 246 na mesma árvore de produção.

Previne regressão por sobreposição do catálogo de integrações ao consolidar
as capacidades fiscais, marketplaces e financeiras do piloto Kordena.
"""
from __future__ import annotations

from core.integracoes.catalogo import CATALOGO_V1, EscopoGestaoIntegracao


def test_release_piloto_preserva_tres_capacidades_sem_duplicar_chave() -> None:
    catalogo = CATALOGO_V1.listar()
    chaves = [(item.servico, item.provedor) for item in catalogo]
    assert len(chaves) == len(set(chaves))

    food99 = CATALOGO_V1.obter("marketplace.pedidos", "99food")
    assert food99.escopo_gestao is EscopoGestaoIntegracao.TENANT_MANAGED

    fiscal = CATALOGO_V1.obter("fiscal.documentos", "nfcore")
    assert fiscal.parametros_obrigatorios == {"host_namespace"}
    assert fiscal.credenciais_obrigatorias == {
        "bearer_token", "workload_credential_id"
    }

    assert not CATALOGO_V1.obter("pagamentos.pix", "asaas").runtime_operacional
    assert not CATALOGO_V1.obter("pagamentos.pix", "picpay").runtime_operacional
    assert not CATALOGO_V1.obter("pagamentos.cartao", "cielo").runtime_operacional
    banco = CATALOGO_V1.obter("financeiro.conta_bancaria", "inter")
    assert not banco.runtime_operacional
    assert banco.credenciais_opcionais == {"chave_pix", "digito_conta"}

    # PagBank e Mercado Pago Pix já possuem runtime existente; não rebaixar.
    assert CATALOGO_V1.obter("pagamentos.pix", "pagbank").runtime_operacional
    assert CATALOGO_V1.obter("pagamentos.pix", "mercado_pago").runtime_operacional

    # Preservar núcleo fiscal próprio e configurações SEFAZ preexistentes.
    sefaz = CATALOGO_V1.obter("fiscal.documentos", "sefaz")
    assert {"certificate_pfx", "certificate_password"} <= sefaz.credenciais_obrigatorias
