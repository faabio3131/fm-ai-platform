from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.hardening import (
    AmostraSlo,
    ErroHardening,
    EvidenciaGateE,
    MetasSloV1,
    ModoDegradacao,
    NivelEvidencia,
    ResultadoCaos,
    ServicoHardeningGateE,
    SnapshotIntegridade,
    TipoEvidenciaGateE,
    encontrar_campos_sensiveis,
    exigir_destino_nao_producao,
    sanitizar_payload,
)

AGORA = datetime(2026, 8, 11, 22, 0, tzinfo=timezone.utc)
SHA = "a" * 64


def _snapshot() -> SnapshotIntegridade:
    return SnapshotIntegridade(
        contagens={"vendas": 120, "pedidos": 118, "clientes": 70},
        somas_centavos={"vendas_total": 452_340, "cashback": 12_500},
        checksums={"vendas:1-100": "abc123456789", "estoque": "def123456789"},
    )


def _evidencias(nivel: NivelEvidencia) -> tuple[EvidenciaGateE, ...]:
    return tuple(
        EvidenciaGateE(
            evidencia_id=f"ev-{tipo.value}",
            tipo=tipo,
            nivel=nivel,
            aprovado=True,
            coletado_em=AGORA,
            valido_ate=AGORA + timedelta(days=7),
            artefato_ref=f"ci://gate-e/{tipo.value}",
            artefato_sha256=SHA,
        )
        for tipo in TipoEvidenciaGateE
    )


def _slo_ok() -> AmostraSlo:
    return AmostraSlo(
        disponibilidade_pct=99.9,
        latencia_p95_ms=800,
        taxa_erro_pct=0.2,
        dlq_backlog=0,
        dlq_idade_segundos=0,
        rto_segundos=600,
        rpo_segundos=60,
    )


def _caos_ok() -> tuple[ResultadoCaos, ...]:
    return (
        ResultadoCaos(
            cenario="kds_offline",
            modo_esperado=ModoDegradacao.DEGRADADO_SEGURO,
            falha_injetada=True,
            recuperou=True,
            recuperacao_segundos=20,
            limite_recuperacao_segundos=60,
        ),
        ResultadoCaos(
            cenario="marketplace_indisponivel",
            modo_esperado=ModoDegradacao.FAIL_CLOSED,
            falha_injetada=True,
            recuperou=True,
            recuperacao_segundos=30,
            limite_recuperacao_segundos=120,
        ),
    )


def test_slo_aprova_baseline_e_reprova_multiplas_violacoes() -> None:
    servico = ServicoHardeningGateE()
    metas = MetasSloV1()
    aprovado = servico.avaliar_slo(metas, _slo_ok())
    assert aprovado.aprovado is True
    assert aprovado.violacoes == ()

    reprovado = servico.avaliar_slo(
        metas,
        AmostraSlo(
            disponibilidade_pct=98.0,
            latencia_p95_ms=2500,
            taxa_erro_pct=4.0,
            dlq_backlog=3,
            dlq_idade_segundos=1800,
            rto_segundos=2400,
            rpo_segundos=900,
        ),
    )
    assert reprovado.aprovado is False
    assert set(reprovado.violacoes) == {
        "disponibilidade_abaixo_meta",
        "latencia_p95_acima_meta",
        "taxa_erro_acima_meta",
        "dlq_backlog_acima_meta",
        "dlq_antiga_demais",
        "rto_acima_meta",
        "rpo_acima_meta",
    }


def test_restore_exige_contagens_somas_e_checksums_identicos() -> None:
    servico = ServicoHardeningGateE()
    origem = _snapshot()
    assert servico.comparar_restore(origem, _snapshot()).aprovado is True

    divergente = SnapshotIntegridade(
        contagens={"vendas": 119, "pedidos": 118, "clientes": 70},
        somas_centavos={"vendas_total": 452_339, "cashback": 12_500},
        checksums={"vendas:1-100": "zzzz12345678", "estoque": "def123456789"},
    )
    resultado = servico.comparar_restore(origem, divergente)
    assert resultado.aprovado is False
    assert "contagem:vendas:divergente" in resultado.divergencias
    assert "soma_centavos:vendas_total:divergente" in resultado.divergencias
    assert "checksum:vendas:1-100:divergente" in resultado.divergencias


def test_evidencia_sintetica_pode_liberar_homologacao_mas_nunca_release() -> None:
    servico = ServicoHardeningGateE()
    slo = servico.avaliar_slo(MetasSloV1(), _slo_ok())
    restore = servico.comparar_restore(_snapshot(), _snapshot())

    homologacao = servico.avaliar_pronto_para_homologacao(
        evidencias=_evidencias(NivelEvidencia.SINTETICA),
        resultado_slo=slo,
        resultado_restore=restore,
        resultados_caos=_caos_ok(),
        agora=AGORA + timedelta(hours=1),
    )
    assert homologacao.aprovado is True
    assert homologacao.avisos

    release = servico.avaliar_release(
        evidencias=_evidencias(NivelEvidencia.SINTETICA),
        resultado_slo=slo,
        resultado_restore=restore,
        resultados_caos=_caos_ok(),
        agora=AGORA + timedelta(hours=1),
    )
    assert release.aprovado is False
    assert any("evidencia_nivel_insuficiente" in item for item in release.bloqueios)


def test_release_exige_todas_evidencias_validas_de_homologacao() -> None:
    servico = ServicoHardeningGateE()
    slo = servico.avaliar_slo(MetasSloV1(), _slo_ok())
    restore = servico.comparar_restore(_snapshot(), _snapshot())
    decisao = servico.avaliar_release(
        evidencias=_evidencias(NivelEvidencia.HOMOLOGACAO),
        resultado_slo=slo,
        resultado_restore=restore,
        resultados_caos=_caos_ok(),
        agora=AGORA + timedelta(hours=1),
    )
    assert decisao.aprovado is True
    assert set(decisao.evidencias_validas) == set(TipoEvidenciaGateE)


def test_evidencia_expirada_bloqueia_gate() -> None:
    servico = ServicoHardeningGateE()
    evidencias = list(_evidencias(NivelEvidencia.HOMOLOGACAO))
    primeira = evidencias[0]
    evidencias[0] = EvidenciaGateE(
        evidencia_id=primeira.evidencia_id,
        tipo=primeira.tipo,
        nivel=primeira.nivel,
        aprovado=True,
        coletado_em=AGORA - timedelta(days=2),
        valido_ate=AGORA - timedelta(days=1),
        artefato_ref=primeira.artefato_ref,
        artefato_sha256=primeira.artefato_sha256,
    )
    slo = servico.avaliar_slo(MetasSloV1(), _slo_ok())
    restore = servico.comparar_restore(_snapshot(), _snapshot())
    decisao = servico.avaliar_release(
        evidencias=evidencias,
        resultado_slo=slo,
        resultado_restore=restore,
        resultados_caos=_caos_ok(),
        agora=AGORA,
    )
    assert decisao.aprovado is False
    assert f"evidencia_expirada:{primeira.tipo.value}" in decisao.bloqueios


def test_privacidade_encontra_e_redige_pii_e_segredos_recursivos() -> None:
    payload = {
        "pedido_id": "p1",
        "cliente_ref": "hash-ref",
        "contato": {"telefone": "5511999999999", "email_hash": "abc"},
        "auth": {"access_token": "segredo"},
    }
    encontrados = encontrar_campos_sensiveis(payload)
    assert "$.contato.telefone" in encontrados
    assert "$.auth.access_token" in encontrados
    assert "$.contato.email_hash" not in encontrados
    sanitizado = sanitizar_payload(payload)
    assert isinstance(sanitizado, dict)
    assert sanitizado["contato"]["telefone"] == "<redacted>"
    assert sanitizado["auth"]["access_token"] == "<redacted>"


def test_guard_de_ambiente_bloqueia_remoto_producao_e_credencial_embutida() -> None:
    assert exigir_destino_nao_producao("sqlite:///:memory:") == "efemero"
    assert exigir_destino_nao_producao("postgresql://localhost/fm_ai_test") == "local"
    with pytest.raises(ErroHardening, match="destino_banco_bloqueado"):
        exigir_destino_nao_producao("postgresql://db.prod.internal/fm_ai")
    with pytest.raises(ErroHardening, match="url_banco_contem_credencial"):
        exigir_destino_nao_producao("postgresql://user:secret@localhost/fm_ai")
