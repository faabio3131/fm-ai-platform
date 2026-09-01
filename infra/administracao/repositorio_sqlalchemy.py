"""Repositório SQLAlchemy do cadastro administrativo da Fase 5."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from core.administracao import (
    ConfiguracaoEstabelecimento,
    EmpresaAdministrativa,
    UnidadeAdministrativa,
)

from .modelos_orm import (
    ConfiguracaoEstabelecimentoORM,
    EmpresaAdminORM,
    UnidadeAdminORM,
)


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class RepositorioAdministracaoSQLAlchemy:
    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def _empresa(row: EmpresaAdminORM) -> EmpresaAdministrativa:
        return EmpresaAdministrativa(
            tenant_id=row.tenant_id,
            nome_exibicao=row.nome_exibicao,
            moeda=row.moeda,
            timezone=row.timezone,
            ativa=bool(row.ativa),
            versao=int(row.versao),
            criado_em=_utc(row.criado_em),
            atualizado_em=_utc(row.atualizado_em),
        )

    @staticmethod
    def _unidade(row: UnidadeAdminORM) -> UnidadeAdministrativa:
        return UnidadeAdministrativa(
            tenant_id=row.tenant_id,
            unidade_id=row.unidade_id,
            codigo=row.codigo,
            nome_fantasia=row.nome_fantasia,
            tipo=row.tipo,
            documento_fiscal=row.documento_fiscal,
            telefone=row.telefone,
            email=row.email,
            endereco=dict(row.endereco or {}),
            horarios=dict(row.horarios or {}),
            ativa=bool(row.ativa),
            versao=int(row.versao),
            criado_em=_utc(row.criado_em),
            atualizado_em=_utc(row.atualizado_em),
        )

    @staticmethod
    def _config(row: ConfiguracaoEstabelecimentoORM) -> ConfiguracaoEstabelecimento:
        return ConfiguracaoEstabelecimento(
            tenant_id=row.tenant_id,
            unidade_id=row.unidade_id,
            formas_pagamento=tuple(row.formas_pagamento or ()),
            taxa_servico_percentual=Decimal(row.taxa_servico_percentual),
            parametros_operacionais=dict(row.parametros_operacionais or {}),
            politica_financeira=dict(row.politica_financeira or {}),
            versao=int(row.versao),
            atualizado_em=_utc(row.atualizado_em),
        )

    def garantir_escopo(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        nome_empresa: str | None = None,
        nome_unidade: str | None = None,
        agora: datetime | None = None,
    ) -> None:
        tenant = tenant_id.strip()
        unidade = unidade_id.strip()
        if not tenant or not unidade:
            raise ValueError("escopo_admin_invalido")
        instante = agora or datetime.now(timezone.utc)
        if self._session.get(EmpresaAdminORM, tenant) is None:
            self._session.add(
                EmpresaAdminORM(
                    tenant_id=tenant,
                    nome_exibicao=(nome_empresa or tenant).strip() or tenant,
                    moeda="BRL",
                    timezone="America/Sao_Paulo",
                    ativa=True,
                    versao=1,
                    criado_em=instante,
                    atualizado_em=instante,
                )
            )
        if self._session.get(UnidadeAdminORM, (tenant, unidade)) is None:
            self._session.add(
                UnidadeAdminORM(
                    tenant_id=tenant,
                    unidade_id=unidade,
                    codigo=unidade,
                    nome_fantasia=(nome_unidade or unidade).strip() or unidade,
                    tipo="unidade",
                    documento_fiscal=None,
                    telefone=None,
                    email=None,
                    endereco={},
                    horarios={},
                    ativa=True,
                    versao=1,
                    criado_em=instante,
                    atualizado_em=instante,
                )
            )
        if self._session.get(
            ConfiguracaoEstabelecimentoORM,
            (tenant, unidade),
        ) is None:
            self._session.add(
                ConfiguracaoEstabelecimentoORM(
                    tenant_id=tenant,
                    unidade_id=unidade,
                    formas_pagamento=[],
                    taxa_servico_percentual=Decimal("0"),
                    parametros_operacionais={},
                    politica_financeira={},
                    versao=1,
                    atualizado_em=instante,
                )
            )
        self._session.flush()

    def obter_empresa(self, *, tenant_id: str) -> EmpresaAdministrativa | None:
        row = self._session.get(EmpresaAdminORM, tenant_id)
        return self._empresa(row) if row is not None else None

    def listar_unidades(
        self,
        *,
        tenant_id: str,
        incluir_inativas: bool = True,
    ) -> tuple[UnidadeAdministrativa, ...]:
        stmt = select(UnidadeAdminORM).where(UnidadeAdminORM.tenant_id == tenant_id)
        if not incluir_inativas:
            stmt = stmt.where(UnidadeAdminORM.ativa.is_(True))
        rows = self._session.scalars(
            stmt.order_by(UnidadeAdminORM.nome_fantasia, UnidadeAdminORM.unidade_id)
        ).all()
        return tuple(self._unidade(row) for row in rows)

    def obter_unidade(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
    ) -> UnidadeAdministrativa | None:
        row = self._session.get(UnidadeAdminORM, (tenant_id, unidade_id))
        return self._unidade(row) if row is not None else None

    def obter_configuracao(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
    ) -> ConfiguracaoEstabelecimento | None:
        row = self._session.get(
            ConfiguracaoEstabelecimentoORM,
            (tenant_id, unidade_id),
        )
        return self._config(row) if row is not None else None

    def criar_unidade(
        self,
        unidade: UnidadeAdministrativa,
        *,
        agora: datetime | None = None,
    ) -> UnidadeAdministrativa:
        if self.obter_unidade(
            tenant_id=unidade.tenant_id,
            unidade_id=unidade.unidade_id,
        ) is not None:
            raise ValueError("unidade_ja_cadastrada")
        instante = agora or datetime.now(timezone.utc)
        row = UnidadeAdminORM(
            tenant_id=unidade.tenant_id,
            unidade_id=unidade.unidade_id,
            codigo=unidade.codigo,
            nome_fantasia=unidade.nome_fantasia,
            tipo=unidade.tipo,
            documento_fiscal=unidade.documento_fiscal,
            telefone=unidade.telefone,
            email=unidade.email,
            endereco=dict(unidade.endereco),
            horarios=dict(unidade.horarios),
            ativa=unidade.ativa,
            versao=1,
            criado_em=instante,
            atualizado_em=instante,
        )
        self._session.add(row)
        self._session.add(
            ConfiguracaoEstabelecimentoORM(
                tenant_id=unidade.tenant_id,
                unidade_id=unidade.unidade_id,
                formas_pagamento=[],
                taxa_servico_percentual=Decimal("0"),
                parametros_operacionais={},
                politica_financeira={},
                versao=1,
                atualizado_em=instante,
            )
        )
        self._session.flush()
        return self._unidade(row)

    def atualizar_empresa(
        self,
        empresa: EmpresaAdministrativa,
        *,
        versao_esperada: int,
        agora: datetime | None = None,
    ) -> EmpresaAdministrativa:
        instante = agora or datetime.now(timezone.utc)
        result = self._session.execute(
            update(EmpresaAdminORM)
            .where(
                EmpresaAdminORM.tenant_id == empresa.tenant_id,
                EmpresaAdminORM.versao == versao_esperada,
            )
            .values(
                nome_exibicao=empresa.nome_exibicao,
                moeda=empresa.moeda,
                timezone=empresa.timezone,
                ativa=empresa.ativa,
                versao=versao_esperada + 1,
                atualizado_em=instante,
            )
        )
        if getattr(result, "rowcount", 0) != 1:
            raise RuntimeError("empresa_admin_concorrente")
        self._session.flush()
        atual = self.obter_empresa(tenant_id=empresa.tenant_id)
        if atual is None:
            raise RuntimeError("empresa_admin_ausente")
        return atual

    def atualizar_unidade(
        self,
        unidade: UnidadeAdministrativa,
        *,
        versao_esperada: int,
        agora: datetime | None = None,
    ) -> UnidadeAdministrativa:
        instante = agora or datetime.now(timezone.utc)
        result = self._session.execute(
            update(UnidadeAdminORM)
            .where(
                UnidadeAdminORM.tenant_id == unidade.tenant_id,
                UnidadeAdminORM.unidade_id == unidade.unidade_id,
                UnidadeAdminORM.versao == versao_esperada,
            )
            .values(
                codigo=unidade.codigo,
                nome_fantasia=unidade.nome_fantasia,
                tipo=unidade.tipo,
                documento_fiscal=unidade.documento_fiscal,
                telefone=unidade.telefone,
                email=unidade.email,
                endereco=dict(unidade.endereco),
                horarios=dict(unidade.horarios),
                ativa=unidade.ativa,
                versao=versao_esperada + 1,
                atualizado_em=instante,
            )
        )
        if getattr(result, "rowcount", 0) != 1:
            raise RuntimeError("unidade_admin_concorrente")
        self._session.flush()
        atual = self.obter_unidade(
            tenant_id=unidade.tenant_id,
            unidade_id=unidade.unidade_id,
        )
        if atual is None:
            raise RuntimeError("unidade_admin_ausente")
        return atual

    def salvar_configuracao(
        self,
        configuracao: ConfiguracaoEstabelecimento,
        *,
        versao_esperada: int,
        agora: datetime | None = None,
    ) -> ConfiguracaoEstabelecimento:
        instante = agora or datetime.now(timezone.utc)
        result = self._session.execute(
            update(ConfiguracaoEstabelecimentoORM)
            .where(
                ConfiguracaoEstabelecimentoORM.tenant_id == configuracao.tenant_id,
                ConfiguracaoEstabelecimentoORM.unidade_id == configuracao.unidade_id,
                ConfiguracaoEstabelecimentoORM.versao == versao_esperada,
            )
            .values(
                formas_pagamento=list(configuracao.formas_pagamento),
                taxa_servico_percentual=configuracao.taxa_servico_percentual,
                parametros_operacionais=dict(configuracao.parametros_operacionais),
                politica_financeira=dict(configuracao.politica_financeira),
                versao=versao_esperada + 1,
                atualizado_em=instante,
            )
        )
        if getattr(result, "rowcount", 0) != 1:
            raise RuntimeError("configuracao_estabelecimento_concorrente")
        self._session.flush()
        atual = self.obter_configuracao(
            tenant_id=configuracao.tenant_id,
            unidade_id=configuracao.unidade_id,
        )
        if atual is None:
            raise RuntimeError("configuracao_estabelecimento_ausente")
        return atual
