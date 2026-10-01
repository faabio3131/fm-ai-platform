"""Read/write adapter Web para o aggregate canônico de campanhas do Gerente IA."""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from typing import Any

from sqlalchemy import select

from core.gerente_ia.erros import ErroGerenteIA
from core.gerente_ia.modelos import fingerprint_campanha
from infra.gerente_ia.campanhas_governadas_sqlalchemy import (
    CampanhasGovernadasSQLAlchemy,
)
from infra.gerente_ia.modelos_orm import EventoCoreORM, RascunhoCampanhaORM


class CampanhasWebSQLAlchemy(CampanhasGovernadasSQLAlchemy):
    """Expõe o lifecycle Web sem criar uma segunda autoridade de campanha."""

    def listar(self, *, tenant_id: str, unidade_id: str) -> tuple[RascunhoCampanhaORM, ...]:
        return tuple(
            self._session_governada.scalars(
                select(RascunhoCampanhaORM)
                .where(
                    RascunhoCampanhaORM.tenant_id == tenant_id,
                    RascunhoCampanhaORM.unidade_id == unidade_id,
                )
                .order_by(RascunhoCampanhaORM.criado_em.desc())
                .limit(200)
            )
        )

    def obter_web(
        self, *, tenant_id: str, unidade_id: str, campanha_id: str
    ) -> RascunhoCampanhaORM:
        return self._row(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            campanha_id=campanha_id,
        )

    def obter_por_criacao_idempotente(
        self, *, tenant_id: str, unidade_id: str, idempotency_key: str
    ) -> RascunhoCampanhaORM | None:
        return self._session_governada.scalar(
            select(RascunhoCampanhaORM).where(
                RascunhoCampanhaORM.tenant_id == tenant_id,
                RascunhoCampanhaORM.unidade_id == unidade_id,
                RascunhoCampanhaORM.idempotency_key == idempotency_key,
            )
        )

    @staticmethod
    def request_hash(*values: str) -> str:
        material = "\x1f".join(values).encode()
        return sha256(material).hexdigest()

    @staticmethod
    def fingerprint(row: RascunhoCampanhaORM) -> str:
        return fingerprint_campanha(
            campanha_id=row.rascunho_id,
            tenant_id=row.tenant_id,
            unidade_id=row.unidade_id,
            canal=row.canal,
            finalidade=row.finalidade,
            objetivo=row.objetivo,
            texto_base=row.texto_base,
            audiencia_elegivel=row.audiencia_elegivel,
        )

    def fingerprint_web(self, row: RascunhoCampanhaORM) -> str:
        """Vincula a revisão Web ao conteúdo e aos destinatários selecionados."""

        audiencia = "\n".join(
            sorted(
                self.audiencia_ids(
                    tenant_id=row.tenant_id,
                    unidade_id=row.unidade_id,
                    campanha_id=row.rascunho_id,
                )
            )
        )
        material = f"{self.fingerprint(row)}\n{audiencia}".encode()
        return sha256(material).hexdigest()

    def _replay(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        campanha_id: str,
        idempotency_key: str,
        event_type: str,
        request_hash: str | None = None,
    ) -> EventoCoreORM | None:
        evento = self._evento_idempotente(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            idempotency_key=idempotency_key,
        )
        if evento is None:
            return None
        if evento.event_type != event_type or evento.aggregate_id != campanha_id:
            raise ErroGerenteIA("conflito_idempotencia")
        if request_hash is not None:
            registrado = dict(evento.payload_seguro).get("request_hash")
            if registrado != request_hash:
                raise ErroGerenteIA("conflito_idempotencia")
        return evento

    def atualizar_rascunho(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        campanha_id: str,
        canal: str,
        finalidade: str,
        objetivo: str,
        texto_base: str,
        usuario_id: str,
        correlation_id: str,
        idempotency_key: str,
        agora: datetime,
    ) -> RascunhoCampanhaORM:
        request_hash = self.request_hash(canal, finalidade, objetivo, texto_base)
        replay = self._replay(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            campanha_id=campanha_id,
            idempotency_key=idempotency_key,
            event_type="campanha.rascunho_atualizado",
            request_hash=request_hash,
        )
        row = self._row(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            campanha_id=campanha_id,
        )
        if replay is not None:
            return row
        if row.status != "rascunho":
            raise ErroGerenteIA("campanha_nao_editavel")
        escopo_audiencia_mudou = (
            row.canal != canal or row.finalidade != finalidade
        )
        row.canal = canal
        row.finalidade = finalidade
        row.objetivo = objetivo
        row.texto_base = texto_base
        if escopo_audiencia_mudou:
            row.audiencia_elegivel = 0
            self._registrar_transicao(
                tenant_id=tenant_id,
                unidade_id=unidade_id,
                campanha_id=campanha_id,
                event_type="campanha.audiencia_definida",
                correlation_id=correlation_id,
                idempotency_key=f"{idempotency_key}:audiencia-invalidada",
                ocorrido_em=agora,
                payload={
                    "campanha_id": campanha_id,
                    "cliente_ids": [],
                    "quantidade": 0,
                    "definido_por": usuario_id,
                    "motivo": "escopo_da_campanha_alterado",
                    "fingerprint": self.fingerprint(row),
                },
                versao=1,
            )
        self._registrar_transicao(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            campanha_id=campanha_id,
            event_type="campanha.rascunho_atualizado",
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            ocorrido_em=agora,
            payload={
                "campanha_id": campanha_id,
                "atualizado_por": usuario_id,
                "audiencia_invalidada": escopo_audiencia_mudou,
                "request_hash": request_hash,
                "fingerprint": self.fingerprint(row),
            },
            versao=1,
        )
        self._session_governada.flush()
        return row

    def definir_audiencia(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        campanha_id: str,
        cliente_ids: tuple[str, ...],
        usuario_id: str,
        correlation_id: str,
        idempotency_key: str,
        agora: datetime,
    ) -> RascunhoCampanhaORM:
        request_hash = self.request_hash(*sorted(cliente_ids))
        replay = self._replay(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            campanha_id=campanha_id,
            idempotency_key=idempotency_key,
            event_type="campanha.audiencia_definida",
            request_hash=request_hash,
        )
        row = self._row(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            campanha_id=campanha_id,
        )
        if replay is not None:
            return row
        if row.status != "rascunho":
            raise ErroGerenteIA("campanha_nao_editavel")
        row.audiencia_elegivel = len(cliente_ids)
        self._registrar_transicao(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            campanha_id=campanha_id,
            event_type="campanha.audiencia_definida",
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            ocorrido_em=agora,
            payload={
                "campanha_id": campanha_id,
                "cliente_ids": list(cliente_ids),
                "quantidade": len(cliente_ids),
                "definido_por": usuario_id,
                "request_hash": request_hash,
                "fingerprint": self.fingerprint(row),
            },
            versao=1,
        )
        self._session_governada.flush()
        return row

    def audiencia_ids(
        self, *, tenant_id: str, unidade_id: str, campanha_id: str
    ) -> tuple[str, ...]:
        evento = self._session_governada.scalar(
            select(EventoCoreORM)
            .where(
                EventoCoreORM.tenant_id == tenant_id,
                EventoCoreORM.unidade_id == unidade_id,
                EventoCoreORM.aggregate_type == "campanha",
                EventoCoreORM.aggregate_id == campanha_id,
                EventoCoreORM.event_type == "campanha.audiencia_definida",
            )
            .order_by(EventoCoreORM.ocorrido_em.desc(), EventoCoreORM.event_id.desc())
            .limit(1)
        )
        if evento is None:
            return ()
        raw = dict(evento.payload_seguro).get("cliente_ids", [])
        if not isinstance(raw, list):
            raise ErroGerenteIA("campanha_audiencia_inconsistente")
        return tuple(str(item) for item in raw if str(item).strip())

    def submeter(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        campanha_id: str,
        usuario_id: str,
        correlation_id: str,
        idempotency_key: str,
        agora: datetime,
    ) -> RascunhoCampanhaORM:
        replay = self._replay(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            campanha_id=campanha_id,
            idempotency_key=idempotency_key,
            event_type="campanha.submetida",
        )
        row = self._row(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            campanha_id=campanha_id,
        )
        if replay is not None:
            return row
        if row.status != "rascunho":
            raise ErroGerenteIA("campanha_nao_esta_em_rascunho")
        if not self.audiencia_ids(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            campanha_id=campanha_id,
        ):
            raise ErroGerenteIA("campanha_audiencia_obrigatoria")
        row.status = "aguardando_aprovacao"
        self._registrar_transicao(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            campanha_id=campanha_id,
            event_type="campanha.submetida",
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            ocorrido_em=agora,
            payload={
                "campanha_id": campanha_id,
                "submetido_por": usuario_id,
                "fingerprint": self.fingerprint(row),
            },
            versao=1,
        )
        self._session_governada.flush()
        return row

    def historico(
        self, *, tenant_id: str, unidade_id: str, campanha_id: str
    ) -> tuple[EventoCoreORM, ...]:
        self._row(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            campanha_id=campanha_id,
        )
        return tuple(
            self._session_governada.scalars(
                select(EventoCoreORM)
                .where(
                    EventoCoreORM.tenant_id == tenant_id,
                    EventoCoreORM.unidade_id == unidade_id,
                    EventoCoreORM.aggregate_type == "campanha",
                    EventoCoreORM.aggregate_id == campanha_id,
                )
                .order_by(EventoCoreORM.ocorrido_em, EventoCoreORM.event_id)
            )
        )

    def campanha_ref(
        self, *, tenant_id: str, unidade_id: str, campanha_id: str
    ) -> str | None:
        evento = self._session_governada.scalar(
            select(EventoCoreORM)
            .where(
                EventoCoreORM.tenant_id == tenant_id,
                EventoCoreORM.unidade_id == unidade_id,
                EventoCoreORM.aggregate_type == "campanha",
                EventoCoreORM.aggregate_id == campanha_id,
                EventoCoreORM.event_type == "campanha.publicavel",
            )
            .order_by(EventoCoreORM.ocorrido_em.desc())
            .limit(1)
        )
        if evento is None:
            return None
        value = dict(evento.payload_seguro).get("campanha_ref")
        return str(value) if isinstance(value, str) and value else None

    def registrar_despacho(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        campanha_id: str,
        resultados: tuple[dict[str, Any], ...],
        usuario_id: str,
        correlation_id: str,
        idempotency_key: str,
        agora: datetime,
    ) -> EventoCoreORM:
        replay = self._replay(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            campanha_id=campanha_id,
            idempotency_key=idempotency_key,
            event_type="campanha.despacho_registrado",
        )
        if replay is not None:
            return replay
        enviados = sum(bool(item.get("enviado")) for item in resultados)
        self._registrar_transicao(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            campanha_id=campanha_id,
            event_type="campanha.despacho_registrado",
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            ocorrido_em=agora,
            payload={
                "campanha_id": campanha_id,
                "resultados": list(resultados),
                "total": len(resultados),
                "enviados": enviados,
                "bloqueados_ou_falhos": len(resultados) - enviados,
                "despachado_por": usuario_id,
            },
            versao=3,
        )
        self._session_governada.flush()
        evento = self._evento_idempotente(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            idempotency_key=idempotency_key,
        )
        if evento is None:
            raise ErroGerenteIA("campanha_despacho_inconsistente")
        return evento
