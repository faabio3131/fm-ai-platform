"""F4-G: campanha só vira publicável após gate humano e sem despacho externo."""

from __future__ import annotations

import inspect

from application import campanhas_governadas
from core.gerente_ia import adapters, modelos, servicos
from infra.gerente_ia import campanhas_governadas_sqlalchemy


def test_f4g_campanha_ref_e_opaca_e_versionada() -> None:
    fonte = inspect.getsource(modelos.CampanhaRef)

    assert "campanha://v1/" in fonte
    assert "campanha_ref_invalida" in fonte


def test_f4g_publicacao_nao_e_tool_autonoma_nem_chama_provedor() -> None:
    nomes = {tool.value for tool in modelos.ToolGerenteIA}

    assert "aprovar_campanha" not in nomes
    assert "publicar_campanha" not in nomes

    fonte = inspect.getsource(servicos.ServicoGerenteIA.publicar_campanha)
    assert "GERENTE_IA_APROVAR_CAMPANHA" in inspect.getsource(
        servicos.ServicoGerenteIA._exigir_humano_campanha
    )
    assert "Meta" not in fonte
    assert "whatsapp" not in fonte.casefold()
    assert "enviar" not in fonte.casefold()


def test_f4g_governanca_e_capacidade_separada_do_adapter_de_rascunho() -> None:
    assert issubclass(
        adapters.PortaCampanhasGovernadas,
        adapters.PortaCampanhasGerenciais,
    )
    fonte = inspect.getsource(servicos.ServicoGerenteIA.aprovar_campanha)
    assert "campanha_governanca_indisponivel" in fonte


def test_f4g_auditoria_e_eventos_nao_carregam_conteudo_da_campanha() -> None:
    fonte_servico = inspect.getsource(
        servicos.ServicoGerenteIA.publicar_campanha
    )
    fonte_adapter = inspect.getsource(
        campanhas_governadas_sqlalchemy.CampanhasGovernadasSQLAlchemy
    )

    assert '"texto_base"' not in fonte_servico
    assert '"telefone"' not in fonte_servico
    assert '"campanha_ref"' in fonte_servico
    assert '"texto_base"' not in fonte_adapter
    assert '"telefone"' not in fonte_adapter


def test_f4g_boundary_apenas_torna_publicavel_sem_despacho() -> None:
    fonte = inspect.getsource(campanhas_governadas.publicar_campanha_v1)

    assert "publicar_campanha" in fonte
    assert "enviar" not in fonte.casefold()
    assert "meta" not in fonte.casefold()
