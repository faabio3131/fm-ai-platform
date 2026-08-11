"""Repository SQLAlchemy escopado para o spool de impressão V1."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, cast

from sqlalchemy import CursorResult, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .erros import ErroImpressao
from .modelos import JobImpressao, StatusImpressao
from .modelos_orm import JobImpressaoORM


def _utc(valor: object) -> datetime:
    instante = cast(datetime, valor)
    if instante.tzinfo is None:
        return instante.replace(tzinfo=timezone.utc)
    return instante.astimezone(timezone.utc)


class RepositorioSpoolSQLAlchemy:
    """Persistência durável do spool; commit pertence ao chamador."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def buscar(
        self, tenant_id: str, unidade_id: str, job_id: str
    ) -> JobImpressao | None:
        row = self.session.scalar(
            select(JobImpressaoORM).where(
                JobImpressaoORM.tenant_id == tenant_id,
                JobImpressaoORM.unidade_id == unidade_id,
                JobImpressaoORM.id == job_id,
            )
        )
        return self._dominio(row) if row else None

    def buscar_por_dedup(
        self, tenant_id: str, unidade_id: str, dedup_key: str
    ) -> JobImpressao | None:
        row = self.session.scalar(
            select(JobImpressaoORM).where(
                JobImpressaoORM.tenant_id == tenant_id,
                JobImpressaoORM.unidade_id == unidade_id,
                JobImpressaoORM.dedup_key == dedup_key,
            )
        )
        return self._dominio(row) if row else None

    def adicionar(self, job: JobImpressao) -> JobImpressao:
        self.session.add(
            JobImpressaoORM(
                id=job.job_id,
                tenant_id=job.tenant_id,
                unidade_id=job.unidade_id,
                setor_id=job.setor_id,
                producao_id=job.producao_id,
                pedido_id=job.pedido_id,
                pedido_item_id=job.pedido_item_id,
                impressora_id=job.impressora_id,
                dedup_key=job.dedup_key,
                documento_hash=job.documento_hash,
                conteudo=job.conteudo,
                status=job.status.value,
                tentativa=job.tentativa,
                max_tentativas=job.max_tentativas,
                versao=job.versao,
                criado_em=job.criado_em,
                atualizado_em=job.atualizado_em,
                ultimo_erro=job.ultimo_erro,
                reimpressao_de=job.reimpressao_de,
                motivo_reimpressao=job.motivo_reimpressao,
            )
        )
        try:
            self.session.flush()
        except IntegrityError as exc:
            raise ErroImpressao("conflito_idempotencia_impressao") from exc
        return job

    def atualizar(
        self, job: JobImpressao, *, versao_esperada: int
    ) -> JobImpressao:
        resultado = cast(
            CursorResult[Any],
            self.session.execute(
                update(JobImpressaoORM)
                .where(
                    JobImpressaoORM.tenant_id == job.tenant_id,
                    JobImpressaoORM.unidade_id == job.unidade_id,
                    JobImpressaoORM.id == job.job_id,
                    JobImpressaoORM.versao == versao_esperada,
                )
                .values(
                    status=job.status.value,
                    tentativa=job.tentativa,
                    max_tentativas=job.max_tentativas,
                    versao=job.versao,
                    atualizado_em=job.atualizado_em,
                    ultimo_erro=job.ultimo_erro,
                    reimpressao_de=job.reimpressao_de,
                    motivo_reimpressao=job.motivo_reimpressao,
                )
            ),
        )
        if resultado.rowcount != 1:
            raise ErroImpressao("job_impressao_concorrente")
        self.session.flush()
        return job

    def listar(self, tenant_id: str, unidade_id: str) -> tuple[JobImpressao, ...]:
        rows = self.session.scalars(
            select(JobImpressaoORM)
            .where(
                JobImpressaoORM.tenant_id == tenant_id,
                JobImpressaoORM.unidade_id == unidade_id,
            )
            .order_by(JobImpressaoORM.criado_em, JobImpressaoORM.id)
        ).all()
        return tuple(self._dominio(row) for row in rows)

    @staticmethod
    def _dominio(row: JobImpressaoORM) -> JobImpressao:
        return JobImpressao(
            job_id=row.id,
            tenant_id=row.tenant_id,
            unidade_id=row.unidade_id,
            setor_id=row.setor_id,
            producao_id=row.producao_id,
            pedido_id=row.pedido_id,
            pedido_item_id=row.pedido_item_id,
            impressora_id=row.impressora_id,
            dedup_key=row.dedup_key,
            documento_hash=row.documento_hash,
            conteudo=row.conteudo,
            status=StatusImpressao(row.status),
            tentativa=row.tentativa,
            max_tentativas=row.max_tentativas,
            versao=row.versao,
            criado_em=_utc(row.criado_em),
            atualizado_em=_utc(row.atualizado_em),
            ultimo_erro=row.ultimo_erro,
            reimpressao_de=row.reimpressao_de,
            motivo_reimpressao=row.motivo_reimpressao,
        )
