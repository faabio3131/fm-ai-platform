from datetime import datetime, timezone
from decimal import Decimal

import pytest

from core.impressao import (
    DestinoImpressao,
    ErroImpressao,
    ImpressoraFake,
    RepositorioSpoolEmMemoria,
    ServicoSpoolImpressao,
    StatusImpressao,
    impressao_v1_enabled,
)
from core.kds.modelos import ProducaoItem, SetorProducao
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Papel, Permissao

AGORA = datetime(2026, 8, 11, 16, 30, tzinfo=timezone.utc)


def _contexto(*, permissao_reimpressao: bool = True) -> ContextoExecucao:
    permissoes = {Permissao.PRODUCAO_VISUALIZAR}
    if permissao_reimpressao:
        permissoes.add(Permissao.IMPRESSAO_REIMPRIMIR)
    return ContextoExecucao(
        tenant_id="tenant-1",
        unidade_id="unidade-1",
        usuario_id="cozinha-1",
        papeis=frozenset({Papel.COZINHA}),
        permissoes=frozenset(permissoes),
        correlation_id="corr-impressao-1",
        solicitado_em=AGORA,
        origem="teste",
        unidades_permitidas=frozenset({"unidade-1"}),
    )


def _setor() -> SetorProducao:
    return SetorProducao(
        setor_id="setor-chapa",
        tenant_id="tenant-1",
        unidade_id="unidade-1",
        codigo="CHAPA",
        nome="Chapa",
        ordem=1,
        sla_segundos=900,
        ativo=True,
        criado_em=AGORA,
        atualizado_em=AGORA,
    )


def _producao() -> ProducaoItem:
    return ProducaoItem(
        producao_id="producao-1",
        tenant_id="tenant-1",
        unidade_id="unidade-1",
        pedido_id="pedido-100",
        pedido_item_id="item-10",
        setor_id="setor-chapa",
        status="aguardando",
        prioridade=0,
        quantidade=Decimal("2"),
        tentativa=1,
        versao=1,
        criado_em=AGORA,
        atualizado_em=AGORA,
    )


def _servico(*, falhar: bool = False, max_tentativas: int = 3):
    repositorio = RepositorioSpoolEmMemoria()
    impressora = ImpressoraFake(falhar=falhar)
    destino = DestinoImpressao(
        tenant_id="tenant-1",
        unidade_id="unidade-1",
        setor_id="setor-chapa",
        impressora_id="printer-chapa",
        max_tentativas=max_tentativas,
    )
    servico = ServicoSpoolImpressao(
        repositorio=repositorio,
        impressora=impressora,
        destinos=(destino,),
    )
    return servico, repositorio, impressora


def _enfileirar(servico: ServicoSpoolImpressao, chave: str = "evt-1"):
    return servico.enfileirar_item_kds(
        contexto=_contexto(),
        producao=_producao(),
        setor=_setor(),
        idempotency_key=chave,
        descricao_item="X-Burger",
        observacao="sem cebola",
        timestamp=AGORA,
    )


def test_flag_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FM_AI_TEST_MODE", raising=False)
    monkeypatch.delenv("FM_AI_PRINT_V1", raising=False)
    assert not impressao_v1_enabled()

    monkeypatch.setenv("FM_AI_PRINT_V1", "1")
    assert not impressao_v1_enabled()

    monkeypatch.setenv("FM_AI_TEST_MODE", "1")
    assert impressao_v1_enabled()


def test_enfileira_por_setor_e_deduplica() -> None:
    servico, repositorio, _ = _servico()

    primeiro = _enfileirar(servico)
    repetido = _enfileirar(servico)

    assert primeiro.enfileirado
    assert primeiro.job is not None
    assert repetido.deduplicado
    assert repetido.job == primeiro.job
    assert len(repositorio.listar("tenant-1", "unidade-1")) == 1
    assert "SETOR: Chapa" in primeiro.job.conteudo
    assert "PEDIDO: pedido-100" in primeiro.job.conteudo
    assert "QTD: 2" in primeiro.job.conteudo


def test_mesma_idempotencia_com_documento_diferente_e_conflito() -> None:
    servico, _, _ = _servico()
    _enfileirar(servico)

    with pytest.raises(ErroImpressao) as exc:
        servico.enfileirar_item_kds(
            contexto=_contexto(),
            producao=_producao(),
            setor=_setor(),
            idempotency_key="evt-1",
            descricao_item="Produto alterado",
            timestamp=AGORA,
        )

    assert exc.value.codigo == "conflito_idempotencia_impressao"


def test_processamento_com_sucesso_e_idempotente() -> None:
    servico, _, impressora = _servico()
    enfileirado = _enfileirar(servico)
    assert enfileirado.job is not None

    primeiro = servico.processar(
        contexto=_contexto(), job_id=enfileirado.job.job_id, timestamp=AGORA
    )
    repetido = servico.processar(
        contexto=_contexto(), job_id=enfileirado.job.job_id, timestamp=AGORA
    )

    assert primeiro.impresso
    assert primeiro.job.status is StatusImpressao.IMPRESSO
    assert repetido.impresso
    assert len(impressora.impressoes) == 1


def test_falha_vira_contingencia_sem_alterar_kds() -> None:
    servico, _, _ = _servico(falhar=True, max_tentativas=2)
    producao = _producao()
    resultado = servico.enfileirar_item_kds(
        contexto=_contexto(),
        producao=producao,
        setor=_setor(),
        idempotency_key="evt-falha",
        descricao_item="X-Burger",
        timestamp=AGORA,
    )
    assert resultado.job is not None

    primeira = servico.processar(
        contexto=_contexto(), job_id=resultado.job.job_id, timestamp=AGORA
    )
    segunda = servico.processar(
        contexto=_contexto(), job_id=resultado.job.job_id, timestamp=AGORA
    )

    assert primeira.job.status is StatusImpressao.FALHOU
    assert not primeira.contingencia
    assert segunda.job.status is StatusImpressao.CONTINGENCIA
    assert segunda.contingencia
    assert segunda.job.ultimo_erro == "impressora_indisponivel"
    assert producao.status == "aguardando"
    assert producao.versao == 1


def test_reimpressao_e_idempotente_e_auditada() -> None:
    servico, repositorio, _ = _servico()
    original = _enfileirar(servico)
    assert original.job is not None

    reimpresso, auditoria = servico.reimprimir(
        contexto=_contexto(),
        job_id=original.job.job_id,
        motivo="ticket ficou ilegivel",
        idempotency_key="reprint-1",
        timestamp=AGORA,
    )
    repetido, auditoria_repetida = servico.reimprimir(
        contexto=_contexto(),
        job_id=original.job.job_id,
        motivo="ticket ficou ilegivel",
        idempotency_key="reprint-1",
        timestamp=AGORA,
    )

    assert reimpresso.reimpressao_de == original.job.job_id
    assert reimpresso.conteudo == original.job.conteudo
    assert repetido == reimpresso
    assert auditoria is not None
    assert auditoria.acao == "impressao.reimprimir"
    assert auditoria_repetida is None
    assert len(repositorio.listar("tenant-1", "unidade-1")) == 2


def test_reimpressao_sem_permissao_e_negada() -> None:
    servico, _, _ = _servico()
    original = _enfileirar(servico)
    assert original.job is not None

    with pytest.raises(ErroImpressao) as exc:
        servico.reimprimir(
            contexto=_contexto(permissao_reimpressao=False),
            job_id=original.job.job_id,
            motivo="ticket ficou ilegivel",
            idempotency_key="reprint-negada",
            timestamp=AGORA,
        )

    assert exc.value.codigo == "permissao_insuficiente"


def test_escopo_multiempresa_e_setor_sao_validados() -> None:
    servico, _, _ = _servico()
    producao = _producao()
    setor = _setor()

    outro_contexto = ContextoExecucao(
        tenant_id="outro-tenant",
        unidade_id="unidade-1",
        usuario_id="cozinha-2",
        papeis=frozenset({Papel.COZINHA}),
        permissoes=frozenset({Permissao.PRODUCAO_VISUALIZAR}),
        correlation_id="corr-outro",
        solicitado_em=AGORA,
        origem="teste",
        unidades_permitidas=frozenset({"unidade-1"}),
    )
    with pytest.raises(ErroImpressao) as exc:
        servico.enfileirar_item_kds(
            contexto=outro_contexto,
            producao=producao,
            setor=setor,
            idempotency_key="evt-outro",
            descricao_item="X-Burger",
            timestamp=AGORA,
        )
    assert exc.value.codigo == "recurso_indisponivel"

    setor_divergente = SetorProducao(
        setor_id="setor-fritura",
        tenant_id="tenant-1",
        unidade_id="unidade-1",
        codigo="FRITURA",
        nome="Fritura",
        ordem=2,
        sla_segundos=900,
        ativo=True,
        criado_em=AGORA,
        atualizado_em=AGORA,
    )
    with pytest.raises(ErroImpressao) as exc:
        servico.enfileirar_item_kds(
            contexto=_contexto(),
            producao=producao,
            setor=setor_divergente,
            idempotency_key="evt-setor",
            descricao_item="X-Burger",
            timestamp=AGORA,
        )
    assert exc.value.codigo == "setor_producao_divergente"
