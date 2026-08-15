from __future__ import annotations

from core.seguranca.autenticacao import IdentidadeUsuario
from core.seguranca.permissoes import Papel, Permissao
from infra.streamlit_app.auth_ui import can_access_sensitive_area


def _identity(*papeis: Papel, ativo: bool = True) -> IdentidadeUsuario:
    return IdentidadeUsuario(
        usuario_id="user-1",
        email="user@example.com",
        senha_hash="hash-nao-usado-neste-teste",
        tenant_id="tenant-1",
        unidade_id="loja-a",
        papeis=frozenset(papeis),
        unidades_permitidas=frozenset({"loja-a"}),
        ativo=ativo,
    )


def test_administrador_e_gerente_podem_entrar_no_shell_administrativo() -> None:
    assert can_access_sensitive_area(_identity(Papel.ADMINISTRADOR)) is True
    assert can_access_sensitive_area(_identity(Papel.GERENTE)) is True


def test_perfis_operacionais_nao_entram_no_shell_administrativo() -> None:
    for papel in (
        Papel.CAIXA,
        Papel.GARCOM,
        Papel.COZINHA,
        Papel.EXPEDICAO,
        Papel.ENTREGADOR,
        Papel.ATENDIMENTO,
        Papel.FINANCEIRO,
        Papel.GERENTE_IA,
    ):
        assert can_access_sensitive_area(_identity(papel)) is False


def test_subsecao_exige_permissao_especifica_alem_do_papel() -> None:
    administrador = _identity(Papel.ADMINISTRADOR)
    gerente = _identity(Papel.GERENTE)
    caixa = _identity(Papel.CAIXA)

    assert (
        can_access_sensitive_area(
            administrador,
            required_permission=Permissao.INTEGRACAO_GERENCIAR,
        )
        is True
    )
    assert (
        can_access_sensitive_area(
            gerente,
            required_permission=Permissao.INTEGRACAO_GERENCIAR,
        )
        is True
    )
    assert (
        can_access_sensitive_area(
            caixa,
            required_permission=Permissao.INTEGRACAO_GERENCIAR,
        )
        is False
    )


def test_usuario_inativo_falha_fechado_mesmo_com_papel_privilegiado() -> None:
    assert can_access_sensitive_area(_identity(Papel.ADMINISTRADOR, ativo=False)) is False
