"""Projeções canônicas e multi-tenant para consultas do Gerente IA V1."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.entrega.modelos_orm import EntregaORM
from core.estoque.modelos_orm import SaldoEstoqueORM
from core.gerente_ia.erros import ErroGerenteIA
from core.gerente_ia.modelos import RegistroGerencial, ValorPrimitivo
from core.kds.modelos_orm import ProducaoItemORM
from core.pagamentos.modelos_orm import (
    DecisaoCreditoTributarioORM,
    ObrigacaoCompraFiscalORM,
    VendaFinanceiraORM,
)
from core.pedidos.modelos_orm import PedidoORM
from core.salao.modelos_orm import MesaORM
from infra.fiscal.modelos_orm import (
    FiscalDocumentProjectionORM,
    FiscalInboundDocumentORM,
    FiscalIntakeCaptureORM,
    FiscalIssuerProfileORM,
    FiscalOutboxORM,
    FiscalProductBindingORM,
)
from infra.gerente_ia.modelos_orm import ConsentimentoCRMAtualORM, EventoCoreORM
from infra.integracoes.modelos_orm import ServicoExternoConfigORM
from infra.procurement.modelos_orm import PedidoCompraORM, RecebimentoCompraORM


def _registro(tipo: str, **campos: ValorPrimitivo) -> RegistroGerencial:
    return RegistroGerencial(tipo, tuple(campos.items()))


class ConsultasGerenciaisSQLAlchemy:
    """Lê somente projeções canônicas, sempre limitadas ao escopo recebido."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def _limite(filtros: dict[str, ValorPrimitivo]) -> int:
        bruto = filtros.get("limite", 50)
        if isinstance(bruto, bool) or not isinstance(bruto, (int, float)):
            raise ErroGerenteIA("limite_invalido")
        return max(1, min(int(bruto), 100))

    def consultar_pedidos(self, *, tenant_id: str, unidade_id: str, filtros: dict[str, ValorPrimitivo]):
        query = select(PedidoORM).where(
            PedidoORM.tenant_id == tenant_id, PedidoORM.unidade_id == unidade_id
        )
        status = filtros.get("status")
        if isinstance(status, str) and status:
            query = query.where(PedidoORM.status == status)
        rows = self._session.scalars(
            query.order_by(PedidoORM.criado_em.desc()).limit(self._limite(filtros))
        )
        return tuple(
            _registro(
                "pedido",
                pedido_id=row.id,
                status=row.status,
                canal=row.canal,
                total=float(Decimal(str(row.total))),
                versao=row.versao,
                fonte="pedidos_v1",
                atualizado_em=str(row.atualizado_em),
                correlation_id=row.correlation_id,
            )
            for row in rows
        )

    def consultar_atrasos(self, *, tenant_id: str, unidade_id: str, filtros: dict[str, ValorPrimitivo]):
        minimo = filtros.get("minutos_minimos", 0)
        agora = datetime.now(timezone.utc)
        rows = self._session.scalars(
            select(ProducaoItemORM).where(
                ProducaoItemORM.tenant_id == tenant_id,
                ProducaoItemORM.unidade_id == unidade_id,
                ProducaoItemORM.status.not_in(("pronto", "retirado", "cancelado")),
            )
        )
        registros = []
        for row in rows:
            atualizado = cast(datetime, row.atualizado_em)
            if atualizado.tzinfo is None:
                atualizado = atualizado.replace(tzinfo=timezone.utc)
            minutos = max(0, int((agora - atualizado).total_seconds() // 60))
            if minutos < int(minimo or 0):
                continue
            registros.append(
                _registro(
                    "atraso",
                    pedido_id=row.pedido_id,
                    producao_item_id=row.id,
                    status=row.status,
                    minutos=minutos,
                    prioridade=row.prioridade,
                    fonte="producao_itens_v1",
                    atualizado_em=str(row.atualizado_em),
                )
            )
        return tuple(registros[: self._limite(filtros)])

    def consultar_mesas(self, *, tenant_id: str, unidade_id: str, filtros: dict[str, ValorPrimitivo]):
        query = select(MesaORM).where(
                MesaORM.tenant_id == tenant_id,
                MesaORM.unidade_id == unidade_id,
                MesaORM.ativo.is_(True),
            )
        status = filtros.get("status")
        if isinstance(status, str) and status:
            query = query.where(MesaORM.status == status)
        rows = self._session.scalars(query.limit(self._limite(filtros)))
        return tuple(
            _registro("mesa", mesa_id=row.id, codigo=row.codigo, status=row.status, fonte="mesas_v1")
            for row in rows
        )

    def consultar_cozinha(self, *, tenant_id: str, unidade_id: str, filtros: dict[str, ValorPrimitivo]):
        query = (
            select(ProducaoItemORM.status, func.count())
            .where(
                ProducaoItemORM.tenant_id == tenant_id,
                ProducaoItemORM.unidade_id == unidade_id,
            )
            .group_by(ProducaoItemORM.status)
        )
        setor_id = filtros.get("setor_id")
        if isinstance(setor_id, str) and setor_id:
            query = query.where(ProducaoItemORM.setor_id == setor_id)
        rows = self._session.execute(query)
        return tuple(
            _registro("cozinha", status=str(status), itens=int(total), fonte="producao_itens_v1")
            for status, total in rows
        )

    def consultar_entregas(self, *, tenant_id: str, unidade_id: str, filtros: dict[str, ValorPrimitivo]):
        query = select(EntregaORM).where(
                EntregaORM.tenant_id == tenant_id,
                EntregaORM.unidade_id == unidade_id,
            )
        status = filtros.get("status")
        if isinstance(status, str) and status:
            query = query.where(EntregaORM.status == status)
        rows = self._session.scalars(query.limit(self._limite(filtros)))
        return tuple(
            _registro(
                "entrega",
                entrega_id=row.id,
                pedido_id=row.pedido_id,
                status=row.status,
                entregador_id=row.entregador_id,
                versao=row.versao,
                fonte="entregas_v1",
                atualizado_em=str(row.atualizado_em),
            )
            for row in rows
        )

    def consultar_estoque(self, *, tenant_id: str, unidade_id: str, filtros: dict[str, ValorPrimitivo]):
        query = select(SaldoEstoqueORM).where(
                SaldoEstoqueORM.tenant_id == tenant_id,
                SaldoEstoqueORM.unidade_id == unidade_id,
            )
        rows = self._session.scalars(query.limit(self._limite(filtros)))
        registros = tuple(
            _registro(
                "estoque",
                insumo_id=row.insumo_id,
                saldo_fisico=float(Decimal(str(row.saldo_fisico))),
                saldo_reservado=float(Decimal(str(row.saldo_reservado))),
                disponivel=float(
                    Decimal(str(row.saldo_fisico)) - Decimal(str(row.saldo_reservado))
                ),
                versao=row.versao,
                fonte="estoque_saldos_v1",
            )
            for row in rows
        )
        if filtros.get("criticos_apenas") is True:
            return tuple(item for item in registros if float(item.para_dict()["disponivel"] or 0) <= 0)
        return registros

    def sugerir_compra(self, *, tenant_id: str, unidade_id: str, filtros: dict[str, ValorPrimitivo]):
        return tuple(
            _registro(
                "sugestao_compra",
                insumo_id=registro.para_dict()["insumo_id"],
                motivo="saldo_disponivel_nao_positivo",
                fonte="estoque_saldos_v1",
                impacto_esperado="evitar_indisponibilidade_de_producao",
            )
            for registro in self.consultar_estoque(
                tenant_id=tenant_id, unidade_id=unidade_id, filtros=filtros
            )
            if float(registro.para_dict()["disponivel"] or 0) <= 0
        )

    def consultar_fiscal(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        filtros: dict[str, ValorPrimitivo],
    ) -> tuple[RegistroGerencial, ...]:
        """Consulta cognitiva read-only sobre autoridades fiscais determinísticas.

        Nunca lê XML/arquivo bruto nem Secret Store. Environment é somente filtro
        de leitura e não promove ambiente nem autoriza operação.
        """

        environment = str(filtros.get("environment") or "homologation")
        tema = str(filtros.get("tema") or "resumo")
        limite = self._limite(filtros)

        doc_scope = (
            FiscalDocumentProjectionORM.tenant_id == tenant_id,
            FiscalDocumentProjectionORM.unit_id == unidade_id,
            FiscalDocumentProjectionORM.environment == environment,
        )
        inbound_scope = (
            FiscalInboundDocumentORM.tenant_id == tenant_id,
            FiscalInboundDocumentORM.unit_id == unidade_id,
            FiscalInboundDocumentORM.environment == environment,
        )
        intake_scope = (
            FiscalIntakeCaptureORM.tenant_id == tenant_id,
            FiscalIntakeCaptureORM.unit_id == unidade_id,
            FiscalIntakeCaptureORM.environment == environment,
        )
        outbox_scope = (
            FiscalOutboxORM.tenant_id == tenant_id,
            FiscalOutboxORM.unit_id == unidade_id,
            FiscalOutboxORM.environment == environment,
        )
        purchase_scope = (
            PedidoCompraORM.tenant_id == tenant_id,
            PedidoCompraORM.unit_id == unidade_id,
            PedidoCompraORM.environment == environment,
        )
        receipt_scope = (
            RecebimentoCompraORM.tenant_id == tenant_id,
            RecebimentoCompraORM.unit_id == unidade_id,
            RecebimentoCompraORM.environment == environment,
        )
        finance_scope = (
            ObrigacaoCompraFiscalORM.tenant_id == tenant_id,
            ObrigacaoCompraFiscalORM.unidade_id == unidade_id,
            ObrigacaoCompraFiscalORM.environment == environment,
        )
        credit_scope = (
            DecisaoCreditoTributarioORM.tenant_id == tenant_id,
            DecisaoCreditoTributarioORM.unidade_id == unidade_id,
            DecisaoCreditoTributarioORM.environment == environment,
        )

        def count(model: type[Any], *conditions: Any) -> int:
            statement = select(func.count()).select_from(model).where(*conditions)
            return int(self._session.execute(statement).scalar_one())

        outbound_total = count(FiscalDocumentProjectionORM, *doc_scope)
        outbound_rejected = count(
            FiscalDocumentProjectionORM,
            *doc_scope,
            FiscalDocumentProjectionORM.state == "rejected",
        )
        inbound_total = count(FiscalInboundDocumentORM, *inbound_scope)
        intake_total = count(FiscalIntakeCaptureORM, *intake_scope)
        intake_errors = count(
            FiscalIntakeCaptureORM,
            *intake_scope,
            FiscalIntakeCaptureORM.last_error_code.is_not(None),
        )
        outbox_open = count(
            FiscalOutboxORM,
            *outbox_scope,
            FiscalOutboxORM.status != "completed",
        )
        purchase_total = count(PedidoCompraORM, *purchase_scope)
        receipt_total = count(RecebimentoCompraORM, *receipt_scope)
        obligation_total = count(ObrigacaoCompraFiscalORM, *finance_scope)
        credit_total = count(DecisaoCreditoTributarioORM, *credit_scope)
        issuer_profiles = count(
            FiscalIssuerProfileORM,
            FiscalIssuerProfileORM.tenant_id == tenant_id,
            FiscalIssuerProfileORM.unit_id == unidade_id,
            FiscalIssuerProfileORM.environment == environment,
            FiscalIssuerProfileORM.valid_until.is_(None),
        )
        product_bindings = count(
            FiscalProductBindingORM,
            FiscalProductBindingORM.tenant_id == tenant_id,
            FiscalProductBindingORM.unit_id == unidade_id,
            FiscalProductBindingORM.environment == environment,
            FiscalProductBindingORM.valid_until.is_(None),
        )

        saldo_aberto = self._session.scalar(
            select(func.coalesce(func.sum(ObrigacaoCompraFiscalORM.saldo), 0)).where(
                *finance_scope
            )
        )
        integration = self._session.scalar(
            select(ServicoExternoConfigORM)
            .where(
                ServicoExternoConfigORM.tenant_id == tenant_id,
                ServicoExternoConfigORM.unidade_id == unidade_id,
                ServicoExternoConfigORM.servico == "fiscal.documentos",
            )
            .order_by(ServicoExternoConfigORM.atualizado_em.desc())
            .limit(1)
        )

        registros: list[RegistroGerencial] = [
            _registro(
                "resumo_fiscal",
                environment=environment,
                documentos_saida=outbound_total,
                documentos_rejeitados=outbound_rejected,
                documentos_entrada=inbound_total,
                capturas_intake=intake_total,
                capturas_com_erro=intake_errors,
                outbox_aberto=outbox_open,
                pedidos_compra=purchase_total,
                recebimentos=receipt_total,
                obrigacoes_compra=obligation_total,
                saldo_obrigacoes=float(Decimal(str(saldo_aberto or 0))),
                decisoes_credito=credit_total,
                perfis_emissor_ativos=issuer_profiles,
                vinculos_produto_ativos=product_bindings,
                fonte="fiscal_projection,inbound,intake,outbox,procurement,pagamentos",
                autoridade="servicos_deterministicos_v1",
                natureza="fato_deterministico",
            )
        ]

        if tema == "documentos":
            document_rows = self._session.scalars(
                select(FiscalDocumentProjectionORM)
                .where(*doc_scope)
                .order_by(FiscalDocumentProjectionORM.updated_at.desc())
                .limit(limite)
            )
            registros.extend(
                _registro(
                    "documento_fiscal",
                    document_id=row.document_id,
                    document_kind=row.document_kind,
                    state=row.state,
                    rejection_code=row.rejection_code,
                    updated_at=str(row.updated_at),
                    environment=environment,
                    fonte="fiscal_document_projection_v1",
                    autoridade="fiscal_v1",
                    natureza="fato_deterministico",
                )
                for row in document_rows
            )
        elif tema == "entradas":
            inbound_rows = self._session.scalars(
                select(FiscalInboundDocumentORM)
                .where(*inbound_scope)
                .order_by(FiscalInboundDocumentORM.updated_at.desc())
                .limit(limite)
            )
            registros.extend(
                _registro(
                    "entrada_fiscal",
                    inbound_id=row.inbound_id,
                    status=row.status,
                    source=row.source,
                    issuer_name=row.issuer_name,
                    updated_at=str(row.updated_at),
                    environment=environment,
                    fonte="fiscal_inbound_documents_v1",
                    autoridade="xml_dfe_oficial",
                    natureza="fato_deterministico",
                )
                for row in inbound_rows
            )
        elif tema == "intake":
            intake_rows = self._session.scalars(
                select(FiscalIntakeCaptureORM)
                .where(*intake_scope)
                .order_by(FiscalIntakeCaptureORM.updated_at.desc())
                .limit(limite)
            )
            registros.extend(
                _registro(
                    "captura_fiscal",
                    capture_id=row.capture_id,
                    source=row.source,
                    authority=row.authority,
                    status=row.status,
                    last_error_code=row.last_error_code,
                    updated_at=str(row.updated_at),
                    environment=environment,
                    fonte="fiscal_intake_captures_v1",
                    autoridade="captura_preliminar",
                    natureza="fato_deterministico",
                )
                for row in intake_rows
            )
        elif tema == "compras":
            order_rows = self._session.scalars(
                select(PedidoCompraORM)
                .where(*purchase_scope)
                .order_by(PedidoCompraORM.atualizado_em.desc())
                .limit(limite)
            )
            receipt_rows = self._session.scalars(
                select(RecebimentoCompraORM)
                .where(*receipt_scope)
                .order_by(RecebimentoCompraORM.confirmado_em.desc())
                .limit(limite)
            )
            registros.extend(
                _registro(
                    "pedido_compra_fiscal",
                    pedido_id=row.pedido_id,
                    fornecedor_id=row.fornecedor_id,
                    status=row.status,
                    versao=row.versao,
                    environment=environment,
                    fonte="procurement_purchase_orders_v1",
                    autoridade="procurement_v1",
                    natureza="fato_deterministico",
                )
                for row in order_rows
            )
            registros.extend(
                _registro(
                    "recebimento_compra_fiscal",
                    recebimento_id=row.recebimento_id,
                    pedido_id=row.pedido_id,
                    inbound_id=row.inbound_id,
                    status=row.status,
                    versao=row.versao,
                    environment=environment,
                    fonte="procurement_receipts_v1",
                    autoridade="procurement_v1",
                    natureza="fato_deterministico",
                )
                for row in receipt_rows
            )
        elif tema == "financeiro":
            obligation_rows = self._session.scalars(
                select(ObrigacaoCompraFiscalORM)
                .where(*finance_scope)
                .order_by(ObrigacaoCompraFiscalORM.criado_em.desc())
                .limit(limite)
            )
            registros.extend(
                _registro(
                    "obrigacao_compra_fiscal",
                    obrigacao_id=row.obrigacao_id,
                    pedido_id=row.pedido_id,
                    status=row.status,
                    reconciliacao=row.reconciliacao,
                    saldo=float(Decimal(str(row.saldo))),
                    moeda=row.moeda,
                    versao=row.versao,
                    environment=environment,
                    fonte="obrigacoes_compra_fiscal_v1",
                    autoridade="financeiro_v1",
                    natureza="fato_deterministico",
                )
                for row in obligation_rows
            )
        elif tema == "configuracao":
            registros.append(
                _registro(
                    "configuracao_fiscal",
                    environment=environment,
                    configurada=integration is not None,
                    provider=(integration.provedor if integration else None),
                    enabled=(integration.habilitada if integration else False),
                    homologated=(integration.homologada if integration else False),
                    credential_roles=(
                        ",".join(sorted(dict(integration.finalidades_credenciais)))
                        if integration
                        else ""
                    ),
                    perfis_emissor_ativos=issuer_profiles,
                    vinculos_produto_ativos=product_bindings,
                    fonte="fm_servicos_externos_config_v1,fiscal_issuer_profiles_v1,fiscal_product_bindings_v1",
                    autoridade="control_plane_fiscal_v1",
                    natureza="fato_deterministico",
                )
            )

        if tema in {"resumo", "pendencias"}:
            if issuer_profiles == 0:
                registros.append(
                    _registro(
                        "recomendacao_fiscal",
                        codigo="configurar_perfil_emissor",
                        evidencias=0,
                        environment=environment,
                        fonte="fiscal_issuer_profiles_v1",
                        natureza="recomendacao",
                        execucao="nao_executada",
                    )
                )
            if integration is None or not integration.habilitada:
                registros.append(
                    _registro(
                        "recomendacao_fiscal",
                        codigo="regularizar_integracao_fiscal",
                        evidencias=0 if integration is None else 1,
                        environment=environment,
                        fonte="fm_servicos_externos_config_v1",
                        natureza="recomendacao",
                        execucao="nao_executada",
                    )
                )
            if outbound_rejected:
                registros.append(
                    _registro(
                        "recomendacao_fiscal",
                        codigo="revisar_documentos_rejeitados",
                        evidencias=outbound_rejected,
                        environment=environment,
                        fonte="fiscal_document_projection_v1",
                        natureza="recomendacao",
                        execucao="nao_executada",
                    )
                )
            if intake_errors:
                registros.append(
                    _registro(
                        "recomendacao_fiscal",
                        codigo="revisar_falhas_intake",
                        evidencias=intake_errors,
                        environment=environment,
                        fonte="fiscal_intake_captures_v1",
                        natureza="recomendacao",
                        execucao="nao_executada",
                    )
                )
            if outbox_open:
                registros.append(
                    _registro(
                        "recomendacao_fiscal",
                        codigo="acompanhar_outbox_fiscal",
                        evidencias=outbox_open,
                        environment=environment,
                        fonte="fiscal_outbox_v1",
                        natureza="recomendacao",
                        execucao="nao_executada",
                    )
                )

        return tuple(registros)

    def gerar_relatorio(self, *, tenant_id: str, unidade_id: str, filtros: dict[str, ValorPrimitivo]):
        tipo = str(filtros.get("tipo", "operacional"))
        escopo_pedido = (PedidoORM.tenant_id == tenant_id, PedidoORM.unidade_id == unidade_id)
        pedidos = int(self._session.scalar(select(func.count()).select_from(PedidoORM).where(*escopo_pedido)) or 0)
        receita = self._session.scalar(
            select(func.coalesce(func.sum(VendaFinanceiraORM.valor), 0)).where(
                VendaFinanceiraORM.tenant_id == tenant_id,
                VendaFinanceiraORM.unidade_id == unidade_id,
            )
        )
        entregas_abertas = int(
            self._session.scalar(
                select(func.count()).select_from(EntregaORM).where(
                    EntregaORM.tenant_id == tenant_id,
                    EntregaORM.unidade_id == unidade_id,
                    EntregaORM.status.not_in(("entregue", "cancelada")),
                )
            )
            or 0
        )
        integracoes_prontas = int(
            self._session.scalar(
                select(func.count()).select_from(ServicoExternoConfigORM).where(
                    ServicoExternoConfigORM.tenant_id == tenant_id,
                    ServicoExternoConfigORM.unidade_id == unidade_id,
                    ServicoExternoConfigORM.habilitada.is_(True),
                    ServicoExternoConfigORM.homologada.is_(True),
                )
            )
            or 0
        )
        integracoes_total = int(
            self._session.scalar(
                select(func.count()).select_from(ServicoExternoConfigORM).where(
                    ServicoExternoConfigORM.tenant_id == tenant_id,
                    ServicoExternoConfigORM.unidade_id == unidade_id,
                )
            ) or 0
        )
        consentimentos = int(
            self._session.scalar(
                select(func.count()).select_from(ConsentimentoCRMAtualORM).where(
                    ConsentimentoCRMAtualORM.tenant_id == tenant_id,
                    ConsentimentoCRMAtualORM.unidade_id == unidade_id,
                    ConsentimentoCRMAtualORM.status == "concedido",
                )
            ) or 0
        )
        eventos = int(
            self._session.scalar(
                select(func.count()).select_from(EventoCoreORM).where(
                    EventoCoreORM.tenant_id == tenant_id,
                    EventoCoreORM.unidade_id == unidade_id,
                )
            ) or 0
        )
        registros: list[RegistroGerencial] = [
            _registro(
                "visao_operacional_central",
                tipo_relatorio=tipo,
                pedidos=pedidos,
                receita_confirmada=float(Decimal(str(receita))),
                entregas_abertas=entregas_abertas,
                itens_cozinha=sum(
                    int(item.para_dict()["itens"] or 0)
                    for item in self.consultar_cozinha(
                        tenant_id=tenant_id, unidade_id=unidade_id, filtros={}
                    )
                ),
                integracoes_prontas=integracoes_prontas,
                integracoes_total=integracoes_total,
                consentimentos_marketing_ativos=consentimentos,
                eventos_internos_correlacionaveis=eventos,
                fontes="pedidos_v1,vendas_financeiras_v1,entregas_v1,producao_itens_v1,estoque_saldos_v1,crm_consentimentos_atuais_v1,fm_servicos_externos_config_v1,gerente_ia_eventos_v1",
            ),
        ]
        atrasos = self.consultar_atrasos(tenant_id=tenant_id, unidade_id=unidade_id, filtros={"limite": 100, "minutos_minimos": 15})
        criticos = self.consultar_estoque(tenant_id=tenant_id, unidade_id=unidade_id, filtros={"limite": 100, "criticos_apenas": True})
        if atrasos:
            registros.append(_registro("recomendacao", codigo="priorizar_atrasos_cozinha", evidencias=len(atrasos), fonte="producao_itens_v1", impacto_esperado="reduzir_sla_operacional"))
        if criticos:
            registros.append(_registro("recomendacao", codigo="repor_estoque_critico", evidencias=len(criticos), fonte="estoque_saldos_v1", impacto_esperado="evitar_ruptura"))
        if integracoes_total > integracoes_prontas:
            registros.append(_registro("recomendacao", codigo="regularizar_integracoes", evidencias=integracoes_total - integracoes_prontas, fonte="fm_servicos_externos_config_v1", impacto_esperado="restaurar_canais_externos"))
        if entregas_abertas:
            registros.append(_registro("recomendacao", codigo="acompanhar_entregas_abertas", evidencias=entregas_abertas, fonte="entregas_v1", impacto_esperado="reduzir_atrasos_delivery"))
        return tuple(registros)

    def acompanhar_conversao(self, *, tenant_id: str, unidade_id: str, filtros: dict[str, ValorPrimitivo]):
        canal = filtros.get("canal")
        query = select(ConsentimentoCRMAtualORM.status, func.count()).where(
            ConsentimentoCRMAtualORM.tenant_id == tenant_id,
            ConsentimentoCRMAtualORM.unidade_id == unidade_id,
        )
        if isinstance(canal, str) and canal:
            query = query.where(ConsentimentoCRMAtualORM.canal == canal)
        rows = self._session.execute(query.group_by(ConsentimentoCRMAtualORM.status))
        contagens = {str(status): int(total) for status, total in rows}
        return (
            _registro(
                "conversao_crm",
                consentimentos_ativos=contagens.get("concedido", 0),
                opt_outs=contagens.get("revogado", 0),
                canal=str(canal) if canal else "todos",
                fonte="crm_consentimentos_atuais_v1",
            ),
        )
