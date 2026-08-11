"""Avaliação determinística de SLO, restore e Gate E."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime, timezone

from .modelos import (
    TIPOS_OBRIGATORIOS_GATE_E,
    AmostraSlo,
    DecisaoGateE,
    EvidenciaGateE,
    MetasSloV1,
    NivelEvidencia,
    ResultadoCaos,
    ResultadoRestore,
    ResultadoSlo,
    SnapshotIntegridade,
    TipoEvidenciaGateE,
)


class ServicoHardeningGateE:
    def avaliar_slo(self, metas: MetasSloV1, amostra: AmostraSlo) -> ResultadoSlo:
        violacoes: list[str] = []
        if amostra.disponibilidade_pct < metas.disponibilidade_min_pct:
            violacoes.append("disponibilidade_abaixo_meta")
        if amostra.latencia_p95_ms > metas.latencia_p95_max_ms:
            violacoes.append("latencia_p95_acima_meta")
        if amostra.taxa_erro_pct > metas.taxa_erro_max_pct:
            violacoes.append("taxa_erro_acima_meta")
        if amostra.dlq_backlog > metas.dlq_backlog_max:
            violacoes.append("dlq_backlog_acima_meta")
        if amostra.dlq_idade_segundos > metas.dlq_idade_max_segundos:
            violacoes.append("dlq_antiga_demais")
        if amostra.rto_segundos > metas.rto_max_segundos:
            violacoes.append("rto_acima_meta")
        if amostra.rpo_segundos > metas.rpo_max_segundos:
            violacoes.append("rpo_acima_meta")
        return ResultadoSlo(aprovado=not violacoes, violacoes=tuple(violacoes))

    def comparar_restore(
        self,
        origem: SnapshotIntegridade,
        restaurado: SnapshotIntegridade,
    ) -> ResultadoRestore:
        divergencias: list[str] = []
        self._comparar_mapa(
            "contagem", origem.contagens, restaurado.contagens, divergencias
        )
        self._comparar_mapa(
            "soma_centavos",
            origem.somas_centavos,
            restaurado.somas_centavos,
            divergencias,
        )
        self._comparar_mapa(
            "checksum", origem.checksums, restaurado.checksums, divergencias
        )
        return ResultadoRestore(aprovado=not divergencias, divergencias=tuple(divergencias))

    @staticmethod
    def _comparar_mapa(
        prefixo: str,
        esperado: Mapping[str, object],
        obtido: Mapping[str, object],
        divergencias: list[str],
    ) -> None:
        chaves = sorted(set(esperado) | set(obtido))
        for chave in chaves:
            if chave not in esperado:
                divergencias.append(f"{prefixo}:{chave}:extra_no_restore")
            elif chave not in obtido:
                divergencias.append(f"{prefixo}:{chave}:ausente_no_restore")
            elif esperado[chave] != obtido[chave]:
                divergencias.append(f"{prefixo}:{chave}:divergente")

    def avaliar_pronto_para_homologacao(
        self,
        *,
        evidencias: Iterable[EvidenciaGateE],
        resultado_slo: ResultadoSlo,
        resultado_restore: ResultadoRestore,
        resultados_caos: Iterable[ResultadoCaos],
        agora: datetime | None = None,
    ) -> DecisaoGateE:
        return self._avaliar_gate(
            evidencias=evidencias,
            resultado_slo=resultado_slo,
            resultado_restore=resultado_restore,
            resultados_caos=resultados_caos,
            nivel_minimo=NivelEvidencia.SINTETICA,
            agora=agora,
            release=False,
        )

    def avaliar_release(
        self,
        *,
        evidencias: Iterable[EvidenciaGateE],
        resultado_slo: ResultadoSlo,
        resultado_restore: ResultadoRestore,
        resultados_caos: Iterable[ResultadoCaos],
        agora: datetime | None = None,
    ) -> DecisaoGateE:
        """Gate de release fail-closed: exige evidência de homologação ou produção."""
        return self._avaliar_gate(
            evidencias=evidencias,
            resultado_slo=resultado_slo,
            resultado_restore=resultado_restore,
            resultados_caos=resultados_caos,
            nivel_minimo=NivelEvidencia.HOMOLOGACAO,
            agora=agora,
            release=True,
        )

    def _avaliar_gate(
        self,
        *,
        evidencias: Iterable[EvidenciaGateE],
        resultado_slo: ResultadoSlo,
        resultado_restore: ResultadoRestore,
        resultados_caos: Iterable[ResultadoCaos],
        nivel_minimo: NivelEvidencia,
        agora: datetime | None,
        release: bool,
    ) -> DecisaoGateE:
        instante = (agora or datetime.now(timezone.utc)).astimezone(timezone.utc)
        ordem_nivel = {
            NivelEvidencia.SINTETICA: 0,
            NivelEvidencia.HOMOLOGACAO: 1,
            NivelEvidencia.PRODUCAO: 2,
        }
        por_tipo: dict[TipoEvidenciaGateE, EvidenciaGateE] = {}
        for evidencia in evidencias:
            atual = por_tipo.get(evidencia.tipo)
            if atual is None or evidencia.coletado_em > atual.coletado_em:
                por_tipo[evidencia.tipo] = evidencia

        bloqueios: list[str] = []
        avisos: list[str] = []
        validas: list[TipoEvidenciaGateE] = []
        for tipo in TIPOS_OBRIGATORIOS_GATE_E:
            evidencia = por_tipo.get(tipo)
            if evidencia is None:
                bloqueios.append(f"evidencia_ausente:{tipo.value}")
                continue
            if not evidencia.aprovado:
                bloqueios.append(f"evidencia_reprovada:{tipo.value}")
                continue
            if evidencia.expirada(instante):
                bloqueios.append(f"evidencia_expirada:{tipo.value}")
                continue
            if ordem_nivel[evidencia.nivel] < ordem_nivel[nivel_minimo]:
                bloqueios.append(f"evidencia_nivel_insuficiente:{tipo.value}")
                continue
            validas.append(tipo)

        if not resultado_slo.aprovado:
            bloqueios.extend(f"slo:{violacao}" for violacao in resultado_slo.violacoes)
        if not resultado_restore.aprovado:
            bloqueios.extend(f"restore:{item}" for item in resultado_restore.divergencias)

        caos = tuple(resultados_caos)
        if not caos:
            bloqueios.append("caos_sem_cenarios")
        for resultado in caos:
            if not resultado.aprovado:
                bloqueios.append(f"caos_reprovado:{resultado.cenario}")

        if not release:
            avisos.append(
                "evidencia_sintetica_nao_autoriza_release; executar restore, rollback, carga, "
                "seguranca, privacidade, acessibilidade e SLO em homologacao"
            )
        return DecisaoGateE(
            aprovado=not bloqueios,
            bloqueios=tuple(sorted(set(bloqueios))),
            avisos=tuple(avisos),
            evidencias_validas=tuple(validas),
        )
