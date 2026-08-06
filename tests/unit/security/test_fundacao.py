from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from core.dominio.dinheiro import Dinheiro
from core.seguranca.auditoria import EventoAuditoria, sanitizar_metadata
from core.seguranca.autorizacao import AutorizarAcao, recurso_no_escopo
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.erros import (
    ContextoAusente,
    IdentidadeSistemaInvalida,
    TenantNaoAutorizado,
    UnidadeNaoAutorizada,
)
from core.seguranca.permissoes import MATRIZ_PADRAO, Papel, Permissao
from core.seguranca.politicas import PoliticaAlcada
from core.seguranca.resolucao import (
    ResolvedorIdentidadeEmMemoria,
    VinculoUsuarioTenant,
    VinculoUsuarioUnidade,
)

AGORA = datetime(2026, 1, 1, tzinfo=timezone.utc)


def contexto(
    *, tenant="tenant-a", unidade="unidade-a", papel=Papel.CAIXA, permissoes=None
):
    return ContextoExecucao(
        tenant,
        unidade,
        "user-1",
        frozenset({papel}),
        permissoes if permissoes is not None else MATRIZ_PADRAO[papel],
        "corr-1",
        AGORA,
        "teste",
        unidades_permitidas=frozenset({unidade}),
    )


def test_contexto_rejeita_tenant_vazio_e_datetime_ingenuo():
    with pytest.raises(ContextoAusente):
        contexto(tenant="")
    with pytest.raises(ContextoAusente):
        ContextoExecucao(
            "t", "u", "x", frozenset(), frozenset(), "c", datetime(2026, 1, 1), "teste"
        )


def test_tenant_da_ui_so_e_aceito_com_vinculo():
    resolvedor = ResolvedorIdentidadeEmMemoria((VinculoUsuarioTenant("u", "a"),), ())
    assert resolvedor.resolver("u", "a") == "a"
    with pytest.raises(TenantNaoAutorizado):
        resolvedor.resolver("u", "b")


def test_unidade_padrao_troca_e_outro_tenant_bloqueado():
    r = ResolvedorIdentidadeEmMemoria(
        (VinculoUsuarioTenant("u", "a"),), (VinculoUsuarioUnidade("u", "a", "1", True),)
    )
    assert r.resolver_unidade("u", "a") == "1"
    with pytest.raises(UnidadeNaoAutorizada):
        r.resolver_unidade("u", "a", "2")


@pytest.mark.parametrize(
    "papel,proibida",
    [
        (Papel.COZINHA, Permissao.FINANCEIRO_VISUALIZAR),
        (Papel.GARCOM, Permissao.ESTOQUE_AJUSTAR),
        (Papel.GERENTE_IA, Permissao.CAIXA_ABRIR),
    ],
)
def test_matriz_aplica_menor_privilegio(papel, proibida):
    assert proibida not in MATRIZ_PADRAO[papel]


def test_tenant_e_unidade_impedem_idor_inclusive_para_admin():
    servico = AutorizarAcao()
    admin = contexto(papel=Papel.ADMINISTRADOR)
    for tenant, unidade in (("tenant-b", "unidade-a"), ("tenant-a", "unidade-b")):
        decisao = servico.executar(
            contexto=admin,
            permissao=Permissao.PEDIDO_VISUALIZAR,
            recurso="id-valido",
            tenant_recurso=tenant,
            unidade_recurso=unidade,
        )
        assert not decisao.autorizado
        assert decisao.codigo == "recurso_indisponivel"
        assert decisao.motivo == "Recurso indisponivel"
    assert not recurso_no_escopo(admin, "tenant-b", "unidade-a")


def test_permissao_ausente_e_politica_desconhecida_negam():
    decisao = AutorizarAcao().executar(
        contexto=contexto(permissoes=frozenset()),
        permissao=Permissao.PEDIDO_CRIAR,
        recurso="x",
        tenant_recurso="tenant-a",
        unidade_recurso="unidade-a",
    )
    assert not decisao.autorizado and decisao.politica_aplicada == "deny_by_default"


def test_desconto_acima_da_alcada_exige_aprovacao():
    politica = PoliticaAlcada({Permissao.DESCONTO_APLICAR: Dinheiro("10")})
    decisao = AutorizarAcao(politica).executar(
        contexto=contexto(),
        permissao=Permissao.DESCONTO_APLICAR,
        recurso="venda",
        tenant_recurso="tenant-a",
        unidade_recurso="unidade-a",
        valor=Dinheiro("10.01"),
    )
    assert not decisao.autorizado and decisao.confirmacao_exigida
    assert decisao.aprovador_exigido == Papel.GERENTE


def test_caixa_nao_estorna_acima_do_limite():
    politica = PoliticaAlcada({Permissao.PAGAMENTO_ESTORNAR: Dinheiro("50")})
    decisao = AutorizarAcao(politica).executar(
        contexto=contexto(),
        permissao=Permissao.PAGAMENTO_ESTORNAR,
        recurso="pagamento",
        tenant_recurso="tenant-a",
        unidade_recurso="unidade-a",
        valor=Dinheiro("51"),
    )
    assert not decisao.autorizado


def test_gerente_ia_mutacao_exige_confirmacao_mesmo_com_permissao():
    ctx = contexto(
        papel=Papel.GERENTE_IA,
        permissoes=frozenset({Permissao.GERENTE_IA_EXECUTAR_ACAO}),
    )
    decisao = AutorizarAcao().executar(
        contexto=ctx,
        permissao=Permissao.GERENTE_IA_EXECUTAR_ACAO,
        recurso="acao",
        tenant_recurso="tenant-a",
        unidade_recurso="unidade-a",
    )
    assert not decisao.autorizado and decisao.confirmacao_exigida


def test_contexto_sistema_exige_identidade_e_motivo():
    with pytest.raises(IdentidadeSistemaInvalida):
        ContextoExecucao.sistema(
            identidade="job",
            motivo="",
            tenant_id="t",
            unidade_id="u",
            correlation_id="c",
            solicitado_em=AGORA,
        )
    assert ContextoExecucao.sistema(
        identidade="job",
        motivo="reconciliar",
        tenant_id="t",
        unidade_id="u",
        correlation_id="c",
        solicitado_em=AGORA,
    ).identidade_sistema


def test_auditoria_remove_segredos_preserva_correlacao_e_serializa():
    metadata = sanitizar_metadata({"token": "segredo", "api_key": "x", "pedido": "42"})
    evento = EventoAuditoria(
        "a",
        "t",
        "u",
        "user",
        Papel.CAIXA,
        "consultar",
        "pedido",
        "hash:42",
        "negado",
        "seguro",
        "corr-1",
        AGORA,
        "teste",
        "deny",
        metadata=metadata,
    )
    dados = evento.para_dict()
    assert dados["metadata"] == {"pedido": "42"}
    assert dados["correlation_id"] == "corr-1"
    with pytest.raises(FrozenInstanceError):
        evento.motivo = "alterado"


def test_contexto_imutavel_e_serializavel():
    ctx = contexto()
    assert ctx.para_dict()["solicitado_em"].endswith("Z")
    with pytest.raises(FrozenInstanceError):
        ctx.tenant_id = "outro"


def test_recurso_inexistente_e_proibido_usam_resposta_indistinguivel():
    admin = contexto(papel=Papel.ADMINISTRADOR)
    proibido = AutorizarAcao().executar(
        contexto=admin,
        permissao=Permissao.PEDIDO_VISUALIZAR,
        recurso="existente",
        tenant_recurso="outro",
        unidade_recurso="unidade-a",
    )
    inexistente = AutorizarAcao().executar(
        contexto=admin,
        permissao=Permissao.PEDIDO_VISUALIZAR,
        recurso="inexistente",
        tenant_recurso="outro",
        unidade_recurso="unidade-a",
    )
    assert (proibido.codigo, proibido.motivo) == (
        inexistente.codigo,
        inexistente.motivo,
    )


def test_valores_das_permissoes_sao_estaveis_e_unicos():
    assert Permissao.PEDIDO_CRIAR.value == "pedido.criar"
    assert len({p.value for p in Permissao}) == len(Permissao)
