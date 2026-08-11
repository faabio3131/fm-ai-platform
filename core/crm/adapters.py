"""Portas do CRM V1; produção futura implementa persistência/transporte reais."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Protocol

from core.eventos.modelos import EnvelopeMensagem

from .modelos import (
    BeneficioCRM,
    CanalMarketing,
    ClienteCRM,
    ClienteMarketplaceRestrito,
    ConsentimentoMarketing,
    EventoFunilCRM,
    FinalidadeMarketing,
    StatusConsentimento,
    TipoBeneficioCRM,
)


class PortaHashIdentidadeCRM(Protocol):
    def hash_marketplace(self, *, integracao_id: str, id_externo: str) -> str: ...


class PortaClientesCRM(Protocol):
    def registrar(self, cliente: ClienteCRM) -> tuple[ClienteCRM, bool]: ...

    def obter(
        self, *, tenant_id: str, unidade_id: str, cliente_id: str
    ) -> ClienteCRM | None: ...

    def listar(self, *, tenant_id: str, unidade_id: str) -> tuple[ClienteCRM, ...]: ...


class PortaClientesMarketplaceCRM(Protocol):
    def registrar(
        self, cliente: ClienteMarketplaceRestrito
    ) -> tuple[ClienteMarketplaceRestrito, bool]: ...

    def obter(
        self, *, tenant_id: str, unidade_id: str, marketplace_cliente_id: str
    ) -> ClienteMarketplaceRestrito | None: ...

    def obter_por_hash(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        integracao_id: str,
        id_externo_hash: str,
    ) -> ClienteMarketplaceRestrito | None: ...

    def marcar_convertido_cas(
        self,
        cliente: ClienteMarketplaceRestrito,
        *,
        cliente_id: str,
        expected_version: int,
    ) -> ClienteMarketplaceRestrito: ...

    def expurgar_expirados(self, *, agora: datetime) -> int: ...


class PortaConsentimentosCRM(Protocol):
    """Registro append-only + outbox no mesmo limite transacional."""

    def registrar_com_evento(
        self,
        consentimento: ConsentimentoMarketing,
        mensagem: EnvelopeMensagem,
    ) -> tuple[ConsentimentoMarketing, bool]: ...

    def atual(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        cliente_id: str,
        canal: CanalMarketing,
        finalidade: FinalidadeMarketing,
    ) -> ConsentimentoMarketing | None: ...

    def historico(
        self, *, tenant_id: str, unidade_id: str, cliente_id: str
    ) -> tuple[ConsentimentoMarketing, ...]: ...

    def listar_atuais(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        canal: CanalMarketing,
        finalidade: FinalidadeMarketing,
        status: StatusConsentimento,
    ) -> tuple[ConsentimentoMarketing, ...]: ...


class PortaFunilCRM(Protocol):
    def registrar(self, evento: EventoFunilCRM) -> tuple[EventoFunilCRM, bool]: ...

    def listar(
        self, *, tenant_id: str, unidade_id: str
    ) -> tuple[EventoFunilCRM, ...]: ...


class PortaBeneficiosCRM(Protocol):
    def emitir(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        cliente_id: str,
        tipo: TipoBeneficioCRM,
        valor: Decimal,
        idempotency_key: str,
    ) -> tuple[BeneficioCRM, bool]: ...


class PortaEnvioMarketing(Protocol):
    def enviar(
        self,
        *,
        referencia_contato: str,
        campanha_ref: str,
        idempotency_key: str,
    ) -> None: ...
