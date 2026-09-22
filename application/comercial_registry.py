"""Application boundary do Commercial Registry KCA-01."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.comercial.erros import (
    ConflitoIdempotenciaComercial,
    DadoComercialInvalido,
    RegistroComercialDuplicado,
    RegistroComercialNaoEncontrado,
)
from core.comercial.modelos import (
    ClasseContaComercial,
    ClienteComercial,
    ContaProdutoComercial,
    StatusClienteComercial,
    StatusContaProduto,
    normalizar_email,
    normalizar_product_code,
    normalizar_telefone,
    validar_transicao_conta_produto,
)
from core.seguranca.contexto import ContextoExecucao
from infra.comercial.modelos_orm import (
    CommercialAuditORM,
    CommercialOutboxORM,
    FMCustomerORM,
    FMProductAccountORM,
)
from infra.comercial.repositorio_sqlalchemy import RepositorioComercialSQLAlchemy

SessionFactory = Callable[[], Session]


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _texto_opcional(valor: str | None, *, max_length: int) -> str | None:
    if valor is None:
        return None
    normalizado = valor.strip()
    if not normalizado:
        return None
    if len(normalizado) > max_length:
        raise DadoComercialInvalido("campo_excede_limite")
    return normalizado


def _hash_requisicao(payload: dict[str, object]) -> str:
    serializado = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(serializado).hexdigest()


def _idempotency_key(valor: str) -> str:
    normalizado = valor.strip()
    if not normalizado or len(normalizado) > 192:
        raise DadoComercialInvalido("idempotency_key_invalida")
    return normalizado


def _customer_code(customer_id: str) -> str:
    return f"FMC-{customer_id.replace('-', '')[:12].upper()}"


class AplicacaoCommercialRegistryV1:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    @staticmethod
    def _validar_idempotencia(
        *,
        registro,
        request_sha256: str,
        aggregate_type: str,
    ) -> str:
        if registro.request_sha256 != request_sha256:
            raise ConflitoIdempotenciaComercial("idempotency_payload_conflict")
        if registro.aggregate_type != aggregate_type:
            raise ConflitoIdempotenciaComercial("idempotency_scope_conflict")
        return str(registro.aggregate_id)

    @staticmethod
    def _auditoria(
        *,
        contexto: ContextoExecucao,
        action: str,
        aggregate_type: str,
        aggregate_id: str,
        reason: str,
        metadata_safe: dict[str, object],
        instante: datetime,
    ) -> CommercialAuditORM:
        return CommercialAuditORM(
            audit_id=str(uuid4()),
            actor_user_id=contexto.usuario_id,
            action=action,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            result="success",
            reason=reason,
            correlation_id=contexto.correlation_id,
            causation_id=contexto.causation_id,
            metadata_safe=metadata_safe,
            timestamp=instante,
        )

    @staticmethod
    def _evento(
        *,
        contexto: ContextoExecucao,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        idempotency_key: str,
        instante: datetime,
        fm_customer_id: str | None,
        product_account_id: str | None = None,
        product_code: str | None = None,
        product_tenant_id: str | None = None,
        payload: dict[str, object],
    ) -> CommercialOutboxORM:
        return CommercialOutboxORM(
            event_id=str(uuid4()),
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            fm_customer_id=fm_customer_id,
            product_account_id=product_account_id,
            product_code=product_code,
            product_tenant_id=product_tenant_id,
            correlation_id=contexto.correlation_id,
            causation_id=contexto.causation_id,
            idempotency_key=idempotency_key,
            occurred_at=instante,
            payload=payload,
            version=1,
            status="pending",
        )

    def criar_cliente(
        self,
        *,
        contexto: ContextoExecucao,
        idempotency_key: str,
        display_name: str,
        legal_name: str | None,
        account_class: ClasseContaComercial,
        primary_contact_email: str,
        primary_contact_phone: str | None,
    ) -> ClienteComercial:
        nome = display_name.strip()
        if not nome or len(nome) > 255:
            raise DadoComercialInvalido("display_name_invalido")
        razao = _texto_opcional(legal_name, max_length=255)
        email = normalizar_email(primary_contact_email)
        telefone = normalizar_telefone(primary_contact_phone)
        key = _idempotency_key(idempotency_key)
        payload = {
            "display_name": nome,
            "legal_name": razao,
            "account_class": account_class.value,
            "primary_contact_email": email,
            "primary_contact_phone": telefone,
        }
        request_sha256 = _hash_requisicao(payload)
        scope = "customer.create"

        try:
            with self._session_factory() as session, session.begin():
                repo = RepositorioComercialSQLAlchemy(session)
                existente = repo.obter_idempotencia(scope=scope, idempotency_key=key)
                if existente is not None:
                    customer_id = self._validar_idempotencia(
                        registro=existente,
                        request_sha256=request_sha256,
                        aggregate_type="customer",
                    )
                    cliente = repo.obter_cliente(customer_id)
                    if cliente is None:
                        raise ConflitoIdempotenciaComercial(
                            "idempotency_result_missing"
                        )
                    return cliente

                instante = _agora()
                customer_id = str(uuid4())
                cliente = repo.adicionar_cliente(
                    FMCustomerORM(
                        fm_customer_id=customer_id,
                        customer_code=_customer_code(customer_id),
                        display_name=nome,
                        legal_name=razao,
                        status=StatusClienteComercial.ACTIVE.value,
                        account_class=account_class.value,
                        primary_contact_email=email,
                        primary_contact_phone=telefone,
                        created_by=contexto.usuario_id,
                        updated_by=contexto.usuario_id,
                        version=1,
                        created_at=instante,
                        updated_at=instante,
                    )
                )
                repo.adicionar_idempotencia(
                    scope=scope,
                    idempotency_key=key,
                    request_sha256=request_sha256,
                    aggregate_type="customer",
                    aggregate_id=customer_id,
                    created_at=instante,
                )
                repo.adicionar_auditoria(
                    self._auditoria(
                        contexto=contexto,
                        action="commercial.customer.create",
                        aggregate_type="customer",
                        aggregate_id=customer_id,
                        reason="customer_registry_kca01",
                        metadata_safe={
                            "account_class": account_class.value,
                            "status": StatusClienteComercial.ACTIVE.value,
                        },
                        instante=instante,
                    )
                )
                repo.adicionar_outbox(
                    self._evento(
                        contexto=contexto,
                        event_type="customer.created",
                        aggregate_type="customer",
                        aggregate_id=customer_id,
                        idempotency_key=f"{scope}:{key}",
                        instante=instante,
                        fm_customer_id=customer_id,
                        payload={
                            "fm_customer_id": customer_id,
                            "account_class": account_class.value,
                            "status": StatusClienteComercial.ACTIVE.value,
                        },
                    )
                )
                return cliente
        except IntegrityError as exc:
            with self._session_factory() as session:
                repo = RepositorioComercialSQLAlchemy(session)
                existente = repo.obter_idempotencia(scope=scope, idempotency_key=key)
                if existente is not None:
                    customer_id = self._validar_idempotencia(
                        registro=existente,
                        request_sha256=request_sha256,
                        aggregate_type="customer",
                    )
                    cliente = repo.obter_cliente(customer_id)
                    if cliente is not None:
                        return cliente
            raise RegistroComercialDuplicado("customer_duplicate") from exc

    def obter_cliente(self, *, fm_customer_id: str) -> ClienteComercial:
        with self._session_factory() as session:
            cliente = RepositorioComercialSQLAlchemy(session).obter_cliente(
                fm_customer_id.strip()
            )
        if cliente is None:
            raise RegistroComercialNaoEncontrado("customer_not_found")
        return cliente

    def atualizar_cliente(
        self,
        *,
        contexto: ContextoExecucao,
        fm_customer_id: str,
        expected_version: int,
        display_name: str,
        legal_name: str | None,
        status: StatusClienteComercial,
        account_class: ClasseContaComercial,
        primary_contact_email: str,
        primary_contact_phone: str | None,
    ) -> ClienteComercial:
        if expected_version < 1:
            raise DadoComercialInvalido("expected_version_invalida")
        nome = display_name.strip()
        if not nome or len(nome) > 255:
            raise DadoComercialInvalido("display_name_invalido")
        email = normalizar_email(primary_contact_email)
        instante = _agora()
        customer_id = fm_customer_id.strip()

        try:
            with self._session_factory() as session, session.begin():
                repo = RepositorioComercialSQLAlchemy(session)
                atual = repo.obter_cliente(customer_id)
                if atual is None:
                    raise RegistroComercialNaoEncontrado("customer_not_found")
                if (
                    atual.status == StatusClienteComercial.CLOSED
                    and status != atual.status
                ):
                    raise DadoComercialInvalido("customer_closed_is_terminal")

                atualizado = repo.atualizar_cliente(
                    fm_customer_id=customer_id,
                    expected_version=expected_version,
                    values={
                        "display_name": nome,
                        "legal_name": _texto_opcional(legal_name, max_length=255),
                        "status": status.value,
                        "account_class": account_class.value,
                        "primary_contact_email": email,
                        "primary_contact_phone": normalizar_telefone(
                            primary_contact_phone
                        ),
                        "updated_by": contexto.usuario_id,
                        "updated_at": instante,
                    },
                )
                repo.adicionar_auditoria(
                    self._auditoria(
                        contexto=contexto,
                        action="commercial.customer.update",
                        aggregate_type="customer",
                        aggregate_id=customer_id,
                        reason="customer_registry_kca01",
                        metadata_safe={
                            "previous_status": atual.status.value,
                            "new_status": atualizado.status.value,
                            "previous_class": atual.account_class.value,
                            "new_class": atualizado.account_class.value,
                            "version": atualizado.version,
                        },
                        instante=instante,
                    )
                )
                repo.adicionar_outbox(
                    self._evento(
                        contexto=contexto,
                        event_type="customer.updated",
                        aggregate_type="customer",
                        aggregate_id=customer_id,
                        idempotency_key=(
                            f"customer.update:{customer_id}:v{atualizado.version}"
                        ),
                        instante=instante,
                        fm_customer_id=customer_id,
                        payload={
                            "fm_customer_id": customer_id,
                            "status": atualizado.status.value,
                            "account_class": atualizado.account_class.value,
                            "version": atualizado.version,
                        },
                    )
                )
                return atualizado
        except IntegrityError as exc:
            raise RegistroComercialDuplicado("customer_update_conflict") from exc

    def criar_conta_produto(
        self,
        *,
        contexto: ContextoExecucao,
        idempotency_key: str,
        fm_customer_id: str,
        product_code: str,
        product_tenant_id: str | None = None,
    ) -> ContaProdutoComercial:
        customer_id = fm_customer_id.strip()
        code = normalizar_product_code(product_code)
        tenant = _texto_opcional(product_tenant_id, max_length=64)
        key = _idempotency_key(idempotency_key)
        request_sha256 = _hash_requisicao(
            {
                "fm_customer_id": customer_id,
                "product_code": code,
                "product_tenant_id": tenant,
            }
        )
        scope = f"product_account.create:{customer_id}:{code}"

        try:
            with self._session_factory() as session, session.begin():
                repo = RepositorioComercialSQLAlchemy(session)
                existente = repo.obter_idempotencia(scope=scope, idempotency_key=key)
                if existente is not None:
                    account_id = self._validar_idempotencia(
                        registro=existente,
                        request_sha256=request_sha256,
                        aggregate_type="product_account",
                    )
                    conta = repo.obter_conta_produto(account_id)
                    if conta is None:
                        raise ConflitoIdempotenciaComercial(
                            "idempotency_result_missing"
                        )
                    return conta

                cliente = repo.obter_cliente(customer_id)
                if cliente is None:
                    raise RegistroComercialNaoEncontrado("customer_not_found")
                if cliente.status == StatusClienteComercial.CLOSED:
                    raise DadoComercialInvalido("customer_closed")

                instante = _agora()
                account_id = str(uuid4())
                conta = repo.adicionar_conta_produto(
                    FMProductAccountORM(
                        product_account_id=account_id,
                        fm_customer_id=customer_id,
                        product_code=code,
                        product_tenant_id=tenant,
                        status=StatusContaProduto.REQUESTED.value,
                        created_by=contexto.usuario_id,
                        updated_by=contexto.usuario_id,
                        version=1,
                        created_at=instante,
                        updated_at=instante,
                        activated_at=None,
                        suspended_at=None,
                        closed_at=None,
                    )
                )
                repo.adicionar_idempotencia(
                    scope=scope,
                    idempotency_key=key,
                    request_sha256=request_sha256,
                    aggregate_type="product_account",
                    aggregate_id=account_id,
                    created_at=instante,
                )
                repo.adicionar_auditoria(
                    self._auditoria(
                        contexto=contexto,
                        action="commercial.product_account.create",
                        aggregate_type="product_account",
                        aggregate_id=account_id,
                        reason="product_account_registry_kca01",
                        metadata_safe={
                            "product_code": code,
                            "status": StatusContaProduto.REQUESTED.value,
                            "tenant_bound": bool(tenant),
                        },
                        instante=instante,
                    )
                )
                repo.adicionar_outbox(
                    self._evento(
                        contexto=contexto,
                        event_type="product_account.created",
                        aggregate_type="product_account",
                        aggregate_id=account_id,
                        idempotency_key=f"{scope}:{key}",
                        instante=instante,
                        fm_customer_id=customer_id,
                        product_account_id=account_id,
                        product_code=code,
                        product_tenant_id=tenant,
                        payload={
                            "fm_customer_id": customer_id,
                            "product_account_id": account_id,
                            "product_code": code,
                            "status": StatusContaProduto.REQUESTED.value,
                        },
                    )
                )
                return conta
        except IntegrityError as exc:
            with self._session_factory() as session:
                repo = RepositorioComercialSQLAlchemy(session)
                existente = repo.obter_idempotencia(scope=scope, idempotency_key=key)
                if existente is not None:
                    account_id = self._validar_idempotencia(
                        registro=existente,
                        request_sha256=request_sha256,
                        aggregate_type="product_account",
                    )
                    conta = repo.obter_conta_produto(account_id)
                    if conta is not None:
                        return conta
            raise RegistroComercialDuplicado("product_account_duplicate") from exc

    def obter_conta_produto(
        self, *, product_account_id: str
    ) -> ContaProdutoComercial:
        with self._session_factory() as session:
            conta = RepositorioComercialSQLAlchemy(session).obter_conta_produto(
                product_account_id.strip()
            )
        if conta is None:
            raise RegistroComercialNaoEncontrado("product_account_not_found")
        return conta

    def transicionar_conta_produto(
        self,
        *,
        contexto: ContextoExecucao,
        product_account_id: str,
        expected_version: int,
        status: StatusContaProduto,
        product_tenant_id: str | None = None,
    ) -> ContaProdutoComercial:
        if expected_version < 1:
            raise DadoComercialInvalido("expected_version_invalida")
        account_id = product_account_id.strip()
        instante = _agora()

        try:
            with self._session_factory() as session, session.begin():
                repo = RepositorioComercialSQLAlchemy(session)
                atual = repo.obter_conta_produto(account_id)
                if atual is None:
                    raise RegistroComercialNaoEncontrado(
                        "product_account_not_found"
                    )
                tenant = validar_transicao_conta_produto(
                    atual=atual.status,
                    destino=status,
                    tenant_atual=atual.product_tenant_id,
                    tenant_solicitado=product_tenant_id,
                )
                values: dict[str, object] = {
                    "status": status.value,
                    "product_tenant_id": tenant,
                    "updated_by": contexto.usuario_id,
                    "updated_at": instante,
                }
                if status == StatusContaProduto.ACTIVE:
                    values["activated_at"] = instante
                    values["suspended_at"] = None
                elif status == StatusContaProduto.SUSPENDED:
                    values["suspended_at"] = instante
                elif status == StatusContaProduto.CLOSED:
                    values["closed_at"] = instante

                atualizada = repo.atualizar_conta_produto(
                    product_account_id=account_id,
                    expected_version=expected_version,
                    values=values,
                )
                event_type = {
                    StatusContaProduto.ACTIVE: "product_account.activated",
                    StatusContaProduto.SUSPENDED: "product_account.suspended",
                    StatusContaProduto.CLOSED: "product_account.closed",
                    StatusContaProduto.PROVISIONING: "product_account.provisioning",
                }[status]
                repo.adicionar_auditoria(
                    self._auditoria(
                        contexto=contexto,
                        action=f"commercial.{event_type}",
                        aggregate_type="product_account",
                        aggregate_id=account_id,
                        reason="product_account_registry_kca01",
                        metadata_safe={
                            "product_code": atualizada.product_code,
                            "previous_status": atual.status.value,
                            "new_status": atualizada.status.value,
                            "tenant_bound": bool(atualizada.product_tenant_id),
                            "version": atualizada.version,
                        },
                        instante=instante,
                    )
                )
                repo.adicionar_outbox(
                    self._evento(
                        contexto=contexto,
                        event_type=event_type,
                        aggregate_type="product_account",
                        aggregate_id=account_id,
                        idempotency_key=(
                            f"product_account.transition:{account_id}:"
                            f"v{atualizada.version}"
                        ),
                        instante=instante,
                        fm_customer_id=atualizada.fm_customer_id,
                        product_account_id=account_id,
                        product_code=atualizada.product_code,
                        product_tenant_id=atualizada.product_tenant_id,
                        payload={
                            "fm_customer_id": atualizada.fm_customer_id,
                            "product_account_id": account_id,
                            "product_code": atualizada.product_code,
                            "status": atualizada.status.value,
                            "version": atualizada.version,
                        },
                    )
                )
                return atualizada
        except IntegrityError as exc:
            raise RegistroComercialDuplicado(
                "product_tenant_binding_duplicate"
            ) from exc
