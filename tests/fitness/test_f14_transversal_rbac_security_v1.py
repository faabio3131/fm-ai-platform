from datetime import UTC, datetime

import pytest

from core.gerente_ia.erros import ErroGerenteIA
from core.gerente_ia.modelos import ToolGerenteIA
from core.gerente_ia.tools import validar_argumentos
from core.seguranca.autorizacao import AutorizarAcao
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import MATRIZ_PADRAO, Papel, Permissao

AGORA = datetime(2026, 9, 6, 4, 0, tzinfo=UTC)
TENANT = "tenant-a"
UNIDADE = "unidade-a"


def contexto(
    *,
    papel: Papel | None = Papel.CAIXA,
    permissoes: frozenset[Permissao] | None = None,
) -> ContextoExecucao:
    papeis = frozenset({papel}) if papel is not None else frozenset()
    efetivas = (
        MATRIZ_PADRAO[papel]
        if permissoes is None and papel is not None
        else permissoes or frozenset()
    )
    return ContextoExecucao(
        TENANT,
        UNIDADE,
        "ator-f14",
        papeis,
        efetivas,
        "corr-f14-rbac",
        AGORA,
        "fitness-f14-rbac",
        unidades_permitidas=frozenset({UNIDADE}),
    )


def test_f14_deny_by_default_sem_role_ou_claim_mapeada() -> None:
    decisao = AutorizarAcao().executar(
        contexto=contexto(papel=None, permissoes=frozenset()),
        permissao=Permissao.PDV_OPERAR,
        recurso="checkout:pdv-42",
        tenant_recurso=TENANT,
        unidade_recurso=UNIDADE,
    )

    assert not decisao.autorizado
    assert decisao.codigo == "permissao_insuficiente"
    assert decisao.politica_aplicada == "deny_by_default"


def test_f14_escopo_tenant_unidade_e_validado_antes_da_permissao() -> None:
    contexto_sem_permissao = contexto(papel=None, permissoes=frozenset())

    decisao = AutorizarAcao().executar(
        contexto=contexto_sem_permissao,
        permissao=Permissao.PDV_OPERAR,
        recurso="checkout:pdv-42",
        tenant_recurso="tenant-b",
        unidade_recurso=UNIDADE,
    )

    assert not decisao.autorizado
    assert decisao.codigo == "recurso_indisponivel"
    assert decisao.motivo == "Recurso indisponivel"


@pytest.mark.parametrize(
    ("dominio", "recurso", "permissao"),
    [
        ("pdv", "checkout:pdv-42", Permissao.PDV_OPERAR),
        ("kds", "producao:kds-42", Permissao.PRODUCAO_VISUALIZAR),
        ("salao", "mesa:salao-42", Permissao.MESA_ABRIR),
        ("crm", "cliente:crm-42", Permissao.CLIENTE_VISUALIZAR),
        ("financeiro", "pagamento:fin-42", Permissao.FINANCEIRO_VISUALIZAR),
    ],
)
def test_f14_idor_cross_tenant_falha_fechado_mesmo_para_admin(
    dominio: str,
    recurso: str,
    permissao: Permissao,
) -> None:
    del dominio
    admin = contexto(papel=Papel.ADMINISTRADOR)

    decisao = AutorizarAcao().executar(
        contexto=admin,
        permissao=permissao,
        recurso=recurso,
        tenant_recurso="tenant-b",
        unidade_recurso=UNIDADE,
    )

    assert not decisao.autorizado
    assert decisao.codigo == "recurso_indisponivel"
    assert decisao.motivo == "Recurso indisponivel"


@pytest.mark.parametrize(
    ("dominio", "recurso", "permissao"),
    [
        ("pdv", "checkout:pdv-42", Permissao.PDV_OPERAR),
        ("kds", "producao:kds-42", Permissao.PRODUCAO_VISUALIZAR),
        ("salao", "mesa:salao-42", Permissao.MESA_ABRIR),
        ("crm", "cliente:crm-42", Permissao.CLIENTE_VISUALIZAR),
        ("financeiro", "pagamento:fin-42", Permissao.FINANCEIRO_VISUALIZAR),
    ],
)
def test_f14_idor_cross_unidade_falha_fechado_mesmo_para_admin(
    dominio: str,
    recurso: str,
    permissao: Permissao,
) -> None:
    del dominio
    admin = contexto(papel=Papel.ADMINISTRADOR)

    decisao = AutorizarAcao().executar(
        contexto=admin,
        permissao=permissao,
        recurso=recurso,
        tenant_recurso=TENANT,
        unidade_recurso="unidade-b",
    )

    assert not decisao.autorizado
    assert decisao.codigo == "recurso_indisponivel"
    assert decisao.motivo == "Recurso indisponivel"


def test_f14_gerente_ia_mantem_menor_privilegio_operacional() -> None:
    permissoes_ia = MATRIZ_PADRAO[Papel.GERENTE_IA]
    assert Permissao.GERENTE_IA_CONSULTAR in permissoes_ia
    assert Permissao.GERENTE_IA_PREPARAR_ACAO in permissoes_ia
    assert Permissao.GERENTE_IA_EXECUTAR_ACAO not in permissoes_ia
    assert Permissao.PDV_OPERAR not in permissoes_ia
    assert Permissao.PAGAMENTO_CONFIRMAR not in permissoes_ia
    assert Permissao.PERMISSAO_GERENCIAR not in permissoes_ia

    consulta = AutorizarAcao().executar(
        contexto=contexto(papel=Papel.GERENTE_IA),
        permissao=Permissao.GERENTE_IA_CONSULTAR,
        recurso="telemetria:operacional",
        tenant_recurso=TENANT,
        unidade_recurso=UNIDADE,
    )
    assert consulta.autorizado

    mutacao = AutorizarAcao().executar(
        contexto=contexto(papel=Papel.GERENTE_IA),
        permissao=Permissao.GERENTE_IA_EXECUTAR_ACAO,
        recurso="acao:mutavel",
        tenant_recurso=TENANT,
        unidade_recurso=UNIDADE,
    )
    assert not mutacao.autorizado
    assert mutacao.codigo == "permissao_insuficiente"


def test_f14_gerente_ia_nao_bypassa_rbac_mesmo_com_permissao_injetada() -> None:
    injetadas = MATRIZ_PADRAO[Papel.GERENTE_IA] | frozenset(
        {Permissao.GERENTE_IA_EXECUTAR_ACAO}
    )
    decisao = AutorizarAcao().executar(
        contexto=contexto(papel=Papel.GERENTE_IA, permissoes=injetadas),
        permissao=Permissao.GERENTE_IA_EXECUTAR_ACAO,
        recurso="acao:mutavel",
        tenant_recurso=TENANT,
        unidade_recurso=UNIDADE,
    )

    assert not decisao.autorizado
    assert decisao.codigo == "confirmacao_exigida"
    assert decisao.confirmacao_exigida
    assert decisao.aprovador_exigido == Papel.GERENTE


@pytest.mark.parametrize(
    "campo",
    [
        "tenant_id",
        "unidade_id",
        "role",
        "papeis",
        "permissoes",
        "token",
        "secret",
        "api_key",
        "authorization",
        "sql",
        "query",
    ],
)
def test_f14_gerente_ia_bloqueia_injecao_de_escopo_roles_segredos_e_bypass(
    campo: str,
) -> None:
    with pytest.raises(ErroGerenteIA) as erro:
        validar_argumentos(ToolGerenteIA.CONSULTAR_PEDIDOS, {campo: "valor-injetado"})

    assert erro.value.codigo == "argumento_de_escopo_proibido"
