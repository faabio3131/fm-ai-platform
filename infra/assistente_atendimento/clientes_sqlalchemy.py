"""Composição SQLAlchemy do cliente do Assistente de Atendimento."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from core.assistente_atendimento.cliente_adapters import PortaClientesAtendimento
from core.assistente_atendimento.contexto import (
    ClienteAtendimento,
    TipoClienteAtendimento,
)
from core.assistente_atendimento.erros import ErroAssistenteAtendimento
from core.crm.modelos import CanalMarketing, ClienteCRM, ContatoCRM, OrigemClienteCRM
from core.seguranca.contexto import ContextoExecucao
from infra.crm.contatos_sqlalchemy import EncryptedSQLAlchemyContactStore
from infra.gerente_ia.persistencia_sqlalchemy import RepositorioClientesCRMSQLAlchemy


class ClientesAtendimentoSQLAlchemy(PortaClientesAtendimento):
    """Resolve e cria ClienteCRM sem consultar Cliente legado por inferência."""

    def __init__(
        self,
        session: Session,
        *,
        master_key: str | None = None,
    ) -> None:
        self._session = session
        self._contatos = EncryptedSQLAlchemyContactStore(
            session,
            master_key=master_key,
        )
        self._clientes = RepositorioClientesCRMSQLAlchemy(session)

    @staticmethod
    def _canal(canal: str) -> CanalMarketing:
        normalizado = " ".join(canal.casefold().strip().split())
        if normalizado in {"whatsapp", "whatsapp_business"}:
            return CanalMarketing.WHATSAPP
        raise ErroAssistenteAtendimento("canal_cliente_nao_suportado", canal)

    def identificar_por_canal(
        self,
        *,
        contexto: ContextoExecucao,
        canal: str,
        identificador_externo: str,
    ) -> ClienteAtendimento:
        canal_crm = self._canal(canal)
        referencia = self._contatos.buscar(
            contexto=contexto,
            canal=canal_crm,
            valor=identificador_externo,
        )
        if referencia is None:
            return ClienteAtendimento(
                tipo=TipoClienteAtendimento.NOVO,
                cliente_ref=None,
            )

        cliente = self._clientes.obter_por_referencia_contato(
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
            referencia=referencia,
        )
        if cliente is None:
            raise ErroAssistenteAtendimento(
                "contato_sem_cliente_canonico"
            )

        return ClienteAtendimento(
            tipo=TipoClienteAtendimento.CONHECIDO,
            cliente_ref=cliente.cliente_id,
        )

    def registrar_novo(
        self,
        *,
        contexto: ContextoExecucao,
        canal: str,
        identificador_externo: str,
    ) -> ClienteAtendimento:
        existente = self.identificar_por_canal(
            contexto=contexto,
            canal=canal,
            identificador_externo=identificador_externo,
        )
        if existente.tipo is TipoClienteAtendimento.CONHECIDO:
            return existente

        canal_crm = self._canal(canal)
        referencia = self._contatos.armazenar(
            contexto=contexto,
            canal=canal_crm,
            valor=identificador_externo,
        )
        cliente_id = f"crm-{uuid4().hex}"
        cliente = ClienteCRM(
            cliente_id=cliente_id,
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
            origem=OrigemClienteCRM.MANUAL,
            contatos=(
                ContatoCRM(
                    canal=canal_crm,
                    referencia=referencia,
                ),
            ),
            criado_em=datetime.now(timezone.utc),
        )
        salvo, _ja_existia = self._clientes.registrar(cliente)
        return ClienteAtendimento(
            tipo=TipoClienteAtendimento.CONHECIDO,
            cliente_ref=salvo.cliente_id,
        )
