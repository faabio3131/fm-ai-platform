"""Web application boundary for fiscal capabilities that predate the Next.js surface.

This module composes the already-certified inbound, intake, procurement and
financial/tax authorities. It does not redefine fiscal rules or trust browser
scope.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from decimal import Decimal
from xml.etree import ElementTree

from sqlalchemy.orm import Session

from application.fiscal_inbound import FiscalInboundApplication
from application.fiscal_intake import SmartFiscalIntakeApplication
from core.estoque.adaptador_sqlalchemy import RepositorioLedgerSQLAlchemy
from core.pagamentos.fiscal_bridge import (
    RegraCreditoTributario,
    ServicoBridgeFinanceiroFiscal,
    TipoAjusteObrigacaoCompra,
)
from core.pagamentos.fiscal_bridge_sqlalchemy import (
    RepositorioBridgeFinanceiroFiscalSQLAlchemy,
)
from core.procurement.modelos import ItemPedidoCompra, ItemRecebido
from core.procurement.servicos import ServicoProcurement
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Permissao
from infra.administracao.repositorio_sqlalchemy import RepositorioAdministracaoSQLAlchemy
from infra.eventos.adaptador_sqlalchemy import RepositorioOutboxSQLAlchemy
from infra.fiscal.inbound_sqlalchemy import FiscalInboundStoreSQLAlchemy
from infra.fiscal.intake_ai import GeminiFiscalIntakeExtractor
from infra.fiscal.intake_sqlalchemy import FiscalIntakeStoreSQLAlchemy
from infra.procurement.repositorio_sqlalchemy import RepositorioProcurementSQLAlchemy
from infra.seguranca.auditoria_sqlalchemy import RepositorioAuditoriaSQLAlchemy
from kordena_fiscal.archive import RetentionPolicyMetadata
from kordena_fiscal.domain import Cnpj, ExecutionScope, FiscalEnvironment
from kordena_fiscal.inbound import FiscalManifestationType
from kordena_fiscal.intake import FiscalIntakeSource

SessionFactory = Callable[[], Session]


def _permission(contexto: ContextoExecucao, permissao: Permissao) -> None:
    if permissao not in contexto.permissoes:
        raise PermissionError(f"seguranca.permissao_exigida:{permissao.value}")


def _scope(
    contexto: ContextoExecucao,
    environment: FiscalEnvironment,
    *,
    suffix: str,
) -> ExecutionScope:
    return ExecutionScope(
        tenant_id=contexto.tenant_id,
        unit_id=contexto.unidade_id,
        environment=environment,
        correlation_id=f"{contexto.correlation_id}:{suffix}",
    )


def _document_total(xml_content: bytes) -> Decimal:
    upper = xml_content.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise ValueError("fiscal.xml_declaracao_nao_permitida")
    root = ElementTree.fromstring(xml_content)

    def local(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    total = next((node for node in root.iter() if local(node.tag) == "ICMSTot"), None)
    if total is not None:
        node = next((child for child in total if local(child.tag) == "vNF"), None)
        if node is not None and (node.text or "").strip():
            value = Decimal((node.text or "").strip()).quantize(Decimal("0.01"))
            if value > 0:
                return value
    values = []
    for det in (node for node in root.iter() if local(node.tag) == "det"):
        product = next((child for child in det if local(child.tag) == "prod"), None)
        if product is None:
            continue
        raw = next(
            (
                (child.text or "").strip()
                for child in product
                if local(child.tag) == "vProd" and (child.text or "").strip()
            ),
            None,
        )
        if raw:
            values.append(Decimal(raw))
    value = sum(values, Decimal(0)).quantize(Decimal("0.01"))
    if value <= 0:
        raise ValueError("fiscal.total_documental_indisponivel")
    return value


class AplicacaoFiscalWebOperationsV1:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def _recipient_document(self, contexto: ContextoExecucao) -> Cnpj:
        with self._session_factory() as session:
            unidade = RepositorioAdministracaoSQLAlchemy(session).obter_unidade(
                tenant_id=contexto.tenant_id,
                unidade_id=contexto.unidade_id,
            )
        if unidade is None or not (unidade.documento_fiscal or "").strip():
            raise ValueError("fiscal.documento_unidade_nao_configurado")
        digits = "".join(ch for ch in str(unidade.documento_fiscal) if ch.isdigit())
        try:
            return Cnpj(digits)
        except Exception as exc:
            raise ValueError("fiscal.documento_unidade_invalido") from exc

    def ingest_official_xml(
        self,
        *,
        contexto: ContextoExecucao,
        environment: FiscalEnvironment,
        xml_content: bytes,
    ):
        _permission(contexto, Permissao.FISCAL_COMPRAS_RECEBER)
        scope = _scope(contexto, environment, suffix="xml")
        store = FiscalInboundStoreSQLAlchemy(self._session_factory)
        return FiscalInboundApplication(store=store).ingest_xml_upload(
            scope=scope,
            recipient_document=self._recipient_document(contexto),
            xml_content=xml_content,
            received_at=contexto.solicitado_em,
        )

    def manifest(
        self,
        *,
        contexto: ContextoExecucao,
        environment: FiscalEnvironment,
        access_key: str,
        event_type: FiscalManifestationType,
        idempotency_key: str,
        protocol_reference: str | None,
    ) -> bool:
        _permission(contexto, Permissao.FISCAL_MANIFESTAR)
        store = FiscalInboundStoreSQLAlchemy(self._session_factory)
        return FiscalInboundApplication(store=store).manifest(
            scope=_scope(contexto, environment, suffix="manifest"),
            access_key=__import__(
                "kordena_fiscal.xml", fromlist=["NfeAccessKey"]
            ).NfeAccessKey(access_key),
            event_type=event_type,
            idempotency_key=idempotency_key,
            actor_id=contexto.usuario_id,
            occurred_at=contexto.solicitado_em,
            protocol_reference=protocol_reference,
        )

    def ingest_preliminary(
        self,
        *,
        contexto: ContextoExecucao,
        environment: FiscalEnvironment,
        source: FiscalIntakeSource,
        media_type: str,
        content: bytes,
        idempotency_key: str,
        extractor: GeminiFiscalIntakeExtractor,
    ):
        _permission(contexto, Permissao.FISCAL_COMPRAS_RECEBER)
        scope = _scope(contexto, environment, suffix="intake")
        inbound_store = FiscalInboundStoreSQLAlchemy(self._session_factory)
        app = SmartFiscalIntakeApplication(
            store=FiscalIntakeStoreSQLAlchemy(self._session_factory),
            inbound_application=FiscalInboundApplication(store=inbound_store),
            inbound_store=inbound_store,
        )
        return app.ingest_preliminary(
            scope=scope,
            source=source,
            media_type=media_type,
            content=content,
            idempotency_key=idempotency_key,
            captured_at=contexto.solicitado_em,
            retention=RetentionPolicyMetadata(
                policy_id="kordena-fiscal-intake-v1",
                policy_version=1,
            ),
            extractor=extractor,
        )

    def reconcile_intake(
        self,
        *,
        contexto: ContextoExecucao,
        environment: FiscalEnvironment,
        capture_id: str,
        official_access_key: str,
    ):
        _permission(contexto, Permissao.FISCAL_COMPRAS_RECEBER)
        scope = _scope(contexto, environment, suffix="intake-reconcile")
        inbound_store = FiscalInboundStoreSQLAlchemy(self._session_factory)
        app = SmartFiscalIntakeApplication(
            store=FiscalIntakeStoreSQLAlchemy(self._session_factory),
            inbound_application=FiscalInboundApplication(store=inbound_store),
            inbound_store=inbound_store,
        )
        return app.reconcile(
            scope=scope,
            capture_id=capture_id,
            official_access_key=official_access_key,
            reconciled_at=contexto.solicitado_em,
        )

    def cadastrar_fornecedor(
        self,
        *,
        contexto: ContextoExecucao,
        environment: FiscalEnvironment,
        fornecedor_id: str,
        documento: str,
        nome: str,
    ):
        scope = _scope(contexto, environment, suffix="supplier")
        with self._session_factory() as session, session.begin():
            service = ServicoProcurement(
                repositorio=RepositorioProcurementSQLAlchemy(session),
                estoque=RepositorioLedgerSQLAlchemy(session),
            )
            return service.cadastrar_fornecedor(
                contexto=contexto,
                scope=scope,
                fornecedor_id=fornecedor_id,
                documento=documento,
                nome=nome,
            )

    def vincular_produto(
        self,
        *,
        contexto: ContextoExecucao,
        environment: FiscalEnvironment,
        fornecedor_id: str,
        codigo_fornecedor: str,
        insumo_id: str,
    ):
        scope = _scope(contexto, environment, suffix="supplier-binding")
        with self._session_factory() as session, session.begin():
            service = ServicoProcurement(
                repositorio=RepositorioProcurementSQLAlchemy(session),
                estoque=RepositorioLedgerSQLAlchemy(session),
            )
            return service.vincular_produto(
                contexto=contexto,
                scope=scope,
                fornecedor_id=fornecedor_id,
                codigo_fornecedor=codigo_fornecedor,
                insumo_id=insumo_id,
            )

    def criar_pedido(
        self,
        *,
        contexto: ContextoExecucao,
        environment: FiscalEnvironment,
        pedido_id: str,
        fornecedor_id: str,
        itens: tuple[ItemPedidoCompra, ...],
        frete: Decimal,
        desconto: Decimal,
        total: Decimal,
    ):
        scope = _scope(contexto, environment, suffix="purchase-order")
        with self._session_factory() as session, session.begin():
            service = ServicoProcurement(
                repositorio=RepositorioProcurementSQLAlchemy(session),
                estoque=RepositorioLedgerSQLAlchemy(session),
            )
            return service.criar_pedido(
                contexto=contexto,
                scope=scope,
                pedido_id=pedido_id,
                fornecedor_id=fornecedor_id,
                itens=itens,
                frete=frete,
                desconto=desconto,
                total=total,
            )

    def aprovar_pedido(
        self,
        *,
        contexto: ContextoExecucao,
        environment: FiscalEnvironment,
        pedido_id: str,
        versao_esperada: int,
    ):
        scope = _scope(contexto, environment, suffix="purchase-order-approve")
        with self._session_factory() as session, session.begin():
            service = ServicoProcurement(
                repositorio=RepositorioProcurementSQLAlchemy(session),
                estoque=RepositorioLedgerSQLAlchemy(session),
            )
            return service.aprovar_pedido(
                contexto=contexto,
                scope=scope,
                pedido_id=pedido_id,
                versao_esperada=versao_esperada,
            )

    def receber(
        self,
        *,
        contexto: ContextoExecucao,
        environment: FiscalEnvironment,
        pedido_id: str,
        access_key: str,
        itens: tuple[ItemRecebido, ...],
        idempotency_key: str,
    ):
        scope = _scope(contexto, environment, suffix="receipt")
        documento = FiscalInboundStoreSQLAlchemy(self._session_factory).get(
            scope=scope,
            access_key=access_key,
        )
        with self._session_factory() as session, session.begin():
            service = ServicoProcurement(
                repositorio=RepositorioProcurementSQLAlchemy(session),
                estoque=RepositorioLedgerSQLAlchemy(session),
            )
            result = service.receber(
                contexto=contexto,
                scope=scope,
                pedido_id=pedido_id,
                documento=documento,
                itens_recebidos=itens,
                idempotency_key=idempotency_key,
            )
            outbox = RepositorioOutboxSQLAlchemy(session)
            audit = RepositorioAuditoriaSQLAlchemy(session)
            for event in result.eventos:
                outbox.adicionar(event)
            for item in result.auditorias:
                audit.adicionar(item)
            return result

    def devolver(
        self,
        *,
        contexto: ContextoExecucao,
        environment: FiscalEnvironment,
        recebimento_id: str,
        idempotency_key: str,
        motivo: str,
    ):
        scope = _scope(contexto, environment, suffix="receipt-return")
        with self._session_factory() as session, session.begin():
            service = ServicoProcurement(
                repositorio=RepositorioProcurementSQLAlchemy(session),
                estoque=RepositorioLedgerSQLAlchemy(session),
            )
            return service.devolver_ao_fornecedor(
                contexto=contexto,
                scope=scope,
                recebimento_id=recebimento_id,
                idempotency_key=idempotency_key,
                motivo=motivo,
            )

    def criar_obrigacao(
        self,
        *,
        contexto: ContextoExecucao,
        recebimento_id: str,
        idempotency_key: str,
    ):
        environment = FiscalEnvironment.PRODUCTION
        scope = _scope(contexto, environment, suffix="financial-obligation")
        inbound_store = FiscalInboundStoreSQLAlchemy(self._session_factory)
        with self._session_factory() as session, session.begin():
            procurement = RepositorioProcurementSQLAlchemy(session)
            recebimento = procurement.obter_recebimento(scope, recebimento_id)
            if recebimento is None:
                raise ValueError("fiscal.recebimento_nao_encontrado")
            pedido = procurement.obter_pedido(scope, recebimento.pedido_id)
            if pedido is None:
                raise ValueError("fiscal.pedido_compra_nao_encontrado")
            documento = inbound_store.get(
                scope=scope,
                access_key=recebimento.chave_acesso,
            )
            service = ServicoBridgeFinanceiroFiscal(
                RepositorioBridgeFinanceiroFiscalSQLAlchemy(session)
            )
            result = service.criar_obrigacao(
                contexto=contexto,
                scope=scope,
                pedido=pedido,
                recebimento=recebimento,
                total_documental=_document_total(documento.xml_content),
                idempotency_key=idempotency_key,
            )
            outbox = RepositorioOutboxSQLAlchemy(session)
            audit = RepositorioAuditoriaSQLAlchemy(session)
            for event in result.eventos:
                outbox.adicionar(event)
            for item in result.auditorias:
                audit.adicionar(item)
            return result

    def ajustar_obrigacao(
        self,
        *,
        contexto: ContextoExecucao,
        recebimento_id: str,
        tipo: TipoAjusteObrigacaoCompra,
        origem_id: str,
        motivo: str,
        idempotency_key: str,
        valor: Decimal | None,
    ):
        scope = _scope(
            contexto,
            FiscalEnvironment.PRODUCTION,
            suffix="financial-adjustment",
        )
        with self._session_factory() as session, session.begin():
            return ServicoBridgeFinanceiroFiscal(
                RepositorioBridgeFinanceiroFiscalSQLAlchemy(session)
            ).ajustar_obrigacao(
                contexto=contexto,
                scope=scope,
                recebimento_id=recebimento_id,
                tipo=tipo,
                origem_id=origem_id,
                motivo=motivo,
                idempotency_key=idempotency_key,
                valor=valor,
            )

    def decidir_credito(
        self,
        *,
        contexto: ContextoExecucao,
        recebimento_id: str,
        tributo: str,
        base_calculo: Decimal,
        valor_destacado: Decimal,
        cfop: str,
        cst: str,
        idempotency_key: str,
        regra_id: str | None,
        regra_versao: int | None,
        aliquota_credito: Decimal | None,
        cfops_elegiveis: frozenset[str],
        csts_elegiveis: frozenset[str],
        vigente_desde: date | None,
        vigente_ate: date | None,
    ):
        scope = _scope(
            contexto,
            FiscalEnvironment.PRODUCTION,
            suffix="tax-credit",
        )
        regra = None
        supplied = (
            regra_id,
            regra_versao,
            aliquota_credito,
            vigente_desde,
        )
        if any(item is not None for item in supplied):
            if any(item is None for item in supplied):
                raise ValueError("fiscal.regra_tributaria_incompleta")
            regra = RegraCreditoTributario(
                regra_id=str(regra_id),
                versao=int(regra_versao),
                tributo=tributo,
                cfops_elegiveis=cfops_elegiveis,
                csts_elegiveis=csts_elegiveis,
                aliquota_credito=Decimal(str(aliquota_credito)),
                vigente_desde=vigente_desde,
                vigente_ate=vigente_ate,
            )
        with self._session_factory() as session, session.begin():
            return ServicoBridgeFinanceiroFiscal(
                RepositorioBridgeFinanceiroFiscalSQLAlchemy(session)
            ).decidir_credito(
                contexto=contexto,
                scope=scope,
                recebimento_id=recebimento_id,
                tributo=tributo,
                base_calculo=base_calculo,
                valor_destacado=valor_destacado,
                cfop=cfop,
                cst=cst,
                regra=regra,
                idempotency_key=idempotency_key,
            )
