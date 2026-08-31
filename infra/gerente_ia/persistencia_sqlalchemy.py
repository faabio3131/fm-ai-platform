"""Adapters persistentes de produção do Core/Gerente IA V1."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, cast
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from core.assistente_atendimento.modelos import ConfiguracaoIdentidadeAssistente
from core.crm.erros import ErroCRM
from core.crm.modelos import (
    CanalMarketing,
    ClienteCRM,
    ContatoCRM,
    OrigemClienteCRM,
)
from core.eventos.modelos import EnvelopeMensagem
from core.gerente_ia.erros import ErroGerenteIA
from core.gerente_ia.modelos import (
    PreviewAcao,
    RascunhoCampanha,
    RegistroGerencial,
    ResultadoAcao,
    StatusPreview,
    ToolGerenteIA,
)
from core.kds.modelos_orm import ProducaoItemORM
from core.marketplaces.modelos import PlataformaMarketplace
from core.pedidos.modelos_orm import ItemPedidoORM

from .modelos_orm import (
    ClienteCRMORM,
    ConsentimentoCRMAtualORM,
    ContatoCRMORM,
    DisponibilidadeProdutoORM,
    EventoCoreORM,
    IdentidadeAssistenteORM,
    PreviewGerenteIAORM,
    RascunhoCampanhaORM,
    ResultadoAcaoGerenteIAORM,
)


def _utc(valor: datetime) -> datetime:
    if valor.tzinfo is None:
        return valor.replace(tzinfo=timezone.utc)
    return valor.astimezone(timezone.utc)


def _registro(tipo: str, **campos: str | float | bool | None) -> RegistroGerencial:
    return RegistroGerencial(tipo, tuple(campos.items()))


class RepositorioIdentidadeAssistenteSQLAlchemy:
    def __init__(self, session: Session) -> None:
        self._session = session

    def obter(self, *, tenant_id: str, unidade_id: str) -> ConfiguracaoIdentidadeAssistente | None:
        row = self._session.get(IdentidadeAssistenteORM, (tenant_id, unidade_id))
        if row is None:
            return None
        return ConfiguracaoIdentidadeAssistente(
            tenant_id=row.tenant_id,
            unidade_id=row.unidade_id,
            nome_publico=row.nome_publico,
            atributos=tuple(dict(row.atributos).items()),
            versao=row.versao,
            atualizado_em=_utc(row.atualizado_em),
        )

    def salvar(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        nome_publico: str,
        atributos: dict[str, Any],
        atualizado_por: str,
        correlation_id: str,
        versao_esperada: int | None,
    ) -> ConfiguracaoIdentidadeAssistente:
        validada = ConfiguracaoIdentidadeAssistente(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            nome_publico=nome_publico,
            atributos=tuple(atributos.items()),
        )
        agora = datetime.now(timezone.utc)
        row = self._session.get(IdentidadeAssistenteORM, (tenant_id, unidade_id))
        if row is None:
            if versao_esperada not in (None, 0):
                raise ErroGerenteIA("configuracao_assistente_desatualizada")
            row = IdentidadeAssistenteORM(
                tenant_id=tenant_id,
                unidade_id=unidade_id,
                nome_publico=validada.nome_publico,
                atributos=dict(validada.atributos),
                versao=1,
                atualizado_por=atualizado_por,
                correlation_id=correlation_id,
                criado_em=agora,
                atualizado_em=agora,
            )
            self._session.add(row)
        else:
            if versao_esperada is not None and row.versao != versao_esperada:
                raise ErroGerenteIA("configuracao_assistente_desatualizada")
            row.nome_publico = validada.nome_publico
            row.atributos = dict(validada.atributos)
            row.versao += 1
            row.atualizado_por = atualizado_por
            row.correlation_id = correlation_id
            row.atualizado_em = agora
        self._session.flush()
        return cast(ConfiguracaoIdentidadeAssistente, self.obter(tenant_id=tenant_id, unidade_id=unidade_id))


class RepositorioClientesCRMSQLAlchemy:
    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def _chave(
        *,
        tenant_id: str,
        unidade_id: str,
        cliente_id: str,
    ) -> tuple[str, str, str]:
        return tenant_id, unidade_id, cliente_id

    def _modelo(self, row: ClienteCRMORM) -> ClienteCRM:
        contatos_rows = self._session.scalars(
            select(ContatoCRMORM)
            .where(
                ContatoCRMORM.tenant_id == row.tenant_id,
                ContatoCRMORM.unidade_id == row.unidade_id,
                ContatoCRMORM.cliente_id == row.cliente_id,
            )
            .order_by(ContatoCRMORM.canal)
        ).all()

        contatos = tuple(
            ContatoCRM(
                canal=CanalMarketing(contato.canal),
                referencia=contato.referencia,
            )
            for contato in contatos_rows
        )

        marketplace_origem = (
            PlataformaMarketplace(row.marketplace_origem)
            if row.marketplace_origem is not None
            else None
        )

        return ClienteCRM(
            cliente_id=row.cliente_id,
            tenant_id=row.tenant_id,
            unidade_id=row.unidade_id,
            origem=OrigemClienteCRM(row.origem),
            contatos=contatos,
            criado_em=_utc(row.criado_em),
            marketplace_origem=marketplace_origem,
            versao=row.versao,
        )

    @staticmethod
    def _semantica(cliente: ClienteCRM) -> tuple:
        contatos = tuple(
            sorted(
                (contato.canal.value, contato.referencia)
                for contato in cliente.contatos
            )
        )
        marketplace = (
            cliente.marketplace_origem.value
            if cliente.marketplace_origem is not None
            else None
        )
        return (
            cliente.tenant_id,
            cliente.unidade_id,
            cliente.cliente_id,
            cliente.origem.value,
            contatos,
            marketplace,
            cliente.versao,
        )

    def registrar(self, cliente: ClienteCRM) -> tuple[ClienteCRM, bool]:
        chave = self._chave(
            tenant_id=cliente.tenant_id,
            unidade_id=cliente.unidade_id,
            cliente_id=cliente.cliente_id,
        )
        existente_row = self._session.get(ClienteCRMORM, chave)
        if existente_row is not None:
            existente = self._modelo(existente_row)
            if self._semantica(existente) != self._semantica(cliente):
                raise ErroCRM("cliente_id_em_conflito")
            return existente, True

        self._session.add(
            ClienteCRMORM(
                tenant_id=cliente.tenant_id,
                unidade_id=cliente.unidade_id,
                cliente_id=cliente.cliente_id,
                origem=cliente.origem.value,
                marketplace_origem=(
                    cliente.marketplace_origem.value
                    if cliente.marketplace_origem is not None
                    else None
                ),
                criado_em=cliente.criado_em,
                versao=cliente.versao,
            )
        )
        for contato in cliente.contatos:
            self._session.add(
                ContatoCRMORM(
                    tenant_id=cliente.tenant_id,
                    unidade_id=cliente.unidade_id,
                    cliente_id=cliente.cliente_id,
                    canal=contato.canal.value,
                    referencia=contato.referencia,
                )
            )
        self._session.flush()

        salvo = self.obter(
            tenant_id=cliente.tenant_id,
            unidade_id=cliente.unidade_id,
            cliente_id=cliente.cliente_id,
        )
        if salvo is None:
            raise ErroCRM("recurso_indisponivel")
        return salvo, False

    def obter(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        cliente_id: str,
    ) -> ClienteCRM | None:
        row = self._session.get(
            ClienteCRMORM,
            self._chave(
                tenant_id=tenant_id,
                unidade_id=unidade_id,
                cliente_id=cliente_id,
            ),
        )
        return self._modelo(row) if row is not None else None

    def obter_por_referencia_contato(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        referencia: str,
    ) -> ClienteCRM | None:
        contato = self._session.scalar(
            select(ContatoCRMORM).where(
                ContatoCRMORM.tenant_id == tenant_id,
                ContatoCRMORM.unidade_id == unidade_id,
                ContatoCRMORM.referencia == referencia,
            )
        )
        if contato is None:
            return None
        return self.obter(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            cliente_id=contato.cliente_id,
        )

    def listar(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
    ) -> tuple[ClienteCRM, ...]:
        rows = self._session.scalars(
            select(ClienteCRMORM)
            .where(
                ClienteCRMORM.tenant_id == tenant_id,
                ClienteCRMORM.unidade_id == unidade_id,
            )
            .order_by(ClienteCRMORM.criado_em, ClienteCRMORM.cliente_id)
        ).all()
        return tuple(self._modelo(row) for row in rows)


class RepositorioPreviewsSQLAlchemy:
    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def _modelo(row: PreviewGerenteIAORM) -> PreviewAcao:
        return PreviewAcao(
            preview_id=row.preview_id,
            tenant_id=row.tenant_id,
            unidade_id=row.unidade_id,
            tool=ToolGerenteIA(row.tool),
            recurso_id=row.recurso_id,
            argumentos=tuple(dict(row.argumentos).items()),
            impacto=RegistroGerencial(row.impacto_tipo, tuple(dict(row.impacto_campos).items())),
            motivo=row.motivo,
            criado_por=row.criado_por,
            criado_em=_utc(row.criado_em),
            expira_em=_utc(row.expira_em),
            fingerprint=row.fingerprint,
            status=StatusPreview(row.status),
        )

    def adicionar(self, preview: PreviewAcao) -> None:
        if self._session.get(PreviewGerenteIAORM, preview.preview_id) is not None:
            raise ErroGerenteIA("preview_duplicado")
        self._session.add(
            PreviewGerenteIAORM(
                preview_id=preview.preview_id,
                tenant_id=preview.tenant_id,
                unidade_id=preview.unidade_id,
                tool=preview.tool.value,
                recurso_id=preview.recurso_id,
                argumentos=dict(preview.argumentos),
                impacto_tipo=preview.impacto.tipo,
                impacto_campos=preview.impacto.para_dict(),
                motivo=preview.motivo,
                criado_por=preview.criado_por,
                criado_em=preview.criado_em,
                expira_em=preview.expira_em,
                fingerprint=preview.fingerprint,
                status=preview.status.value,
                versao=1,
            )
        )
        self._session.flush()

    def obter(self, *, tenant_id: str, unidade_id: str, preview_id: str) -> PreviewAcao | None:
        row = self._session.scalar(
            select(PreviewGerenteIAORM).where(
                PreviewGerenteIAORM.preview_id == preview_id,
                PreviewGerenteIAORM.tenant_id == tenant_id,
                PreviewGerenteIAORM.unidade_id == unidade_id,
            )
        )
        return self._modelo(row) if row is not None else None

    def reservar_execucao(self, *, tenant_id: str, unidade_id: str, preview_id: str, fingerprint: str) -> PreviewAcao:
        resultado = cast(
            CursorResult[Any],
            self._session.execute(
                update(PreviewGerenteIAORM)
                .where(
                    PreviewGerenteIAORM.preview_id == preview_id,
                    PreviewGerenteIAORM.tenant_id == tenant_id,
                    PreviewGerenteIAORM.unidade_id == unidade_id,
                    PreviewGerenteIAORM.fingerprint == fingerprint,
                    PreviewGerenteIAORM.status == StatusPreview.PENDENTE.value,
                )
                .values(status=StatusPreview.EXECUTANDO.value, versao=PreviewGerenteIAORM.versao + 1)
            ),
        )
        if resultado.rowcount != 1:
            raise ErroGerenteIA("preview_ja_consumido")
        self._session.flush()
        reservado = self.obter(tenant_id=tenant_id, unidade_id=unidade_id, preview_id=preview_id)
        if reservado is None:
            raise ErroGerenteIA("recurso_indisponivel")
        return reservado

    def liberar_execucao(self, *, tenant_id: str, unidade_id: str, preview_id: str, fingerprint: str) -> None:
        self._session.execute(
            update(PreviewGerenteIAORM)
            .where(
                PreviewGerenteIAORM.preview_id == preview_id,
                PreviewGerenteIAORM.tenant_id == tenant_id,
                PreviewGerenteIAORM.unidade_id == unidade_id,
                PreviewGerenteIAORM.fingerprint == fingerprint,
                PreviewGerenteIAORM.status == StatusPreview.EXECUTANDO.value,
            )
            .values(status=StatusPreview.PENDENTE.value, versao=PreviewGerenteIAORM.versao + 1)
        )
        self._session.flush()

    def concluir(self, resultado: ResultadoAcao) -> None:
        row = self._session.get(PreviewGerenteIAORM, resultado.preview_id)
        if row is None or row.status != StatusPreview.EXECUTANDO.value:
            raise ErroGerenteIA("preview_ja_consumido")
        row.status = StatusPreview.EXECUTADO.value
        row.versao += 1
        self._session.flush()

    def obter_resultado_por_idempotencia(self, *, tenant_id: str, unidade_id: str, idempotency_key: str) -> ResultadoAcao | None:
        row = self._session.scalar(
            select(ResultadoAcaoGerenteIAORM).where(
                ResultadoAcaoGerenteIAORM.tenant_id == tenant_id,
                ResultadoAcaoGerenteIAORM.unidade_id == unidade_id,
                ResultadoAcaoGerenteIAORM.idempotency_key == idempotency_key,
            )
        )
        if row is None:
            return None
        return ResultadoAcao(
            preview_id=row.preview_id,
            tool=ToolGerenteIA(row.tool),
            recurso_id=row.recurso_id,
            resultado=row.resultado,
            executado_por=row.executado_por,
            executado_em=_utc(row.executado_em),
            idempotency_key=row.idempotency_key,
        )

    def registrar_idempotencia(self, *, tenant_id: str, unidade_id: str, resultado: ResultadoAcao) -> None:
        existente = self.obter_resultado_por_idempotencia(
            tenant_id=tenant_id, unidade_id=unidade_id, idempotency_key=resultado.idempotency_key
        )
        if existente is not None:
            if existente.preview_id != resultado.preview_id:
                raise ErroGerenteIA("conflito_idempotencia")
            return
        self._session.add(
            ResultadoAcaoGerenteIAORM(
                resultado_id=f"result_{uuid4().hex}",
                tenant_id=tenant_id,
                unidade_id=unidade_id,
                preview_id=resultado.preview_id,
                tool=resultado.tool.value,
                recurso_id=resultado.recurso_id,
                resultado=resultado.resultado,
                executado_por=resultado.executado_por,
                executado_em=resultado.executado_em,
                idempotency_key=resultado.idempotency_key,
            )
        )
        self._session.flush()


class AcoesGerenciaisSQLAlchemy:
    def __init__(self, session: Session) -> None:
        self._session = session

    def _itens_pedido(self, tenant_id: str, unidade_id: str, pedido_id: str) -> list[ProducaoItemORM]:
        return list(
            self._session.scalars(
                select(ProducaoItemORM).where(
                    ProducaoItemORM.tenant_id == tenant_id,
                    ProducaoItemORM.unidade_id == unidade_id,
                    ProducaoItemORM.pedido_id == pedido_id,
                    ProducaoItemORM.status.not_in(("retirado", "cancelado")),
                )
            ).all()
        )

    def previsualizar_priorizacao(self, *, tenant_id: str, unidade_id: str, pedido_id: str, prioridade: int) -> RegistroGerencial:
        itens = self._itens_pedido(tenant_id, unidade_id, pedido_id)
        if not itens:
            raise ErroGerenteIA("recurso_indisponivel")
        return _registro(
            "preview_priorizacao",
            pedido_id=pedido_id,
            prioridade_atual=max(item.prioridade for item in itens),
            prioridade_nova=prioridade,
            itens_afetados=len(itens),
            versao=sum(item.versao for item in itens),
        )

    def priorizar_pedido(self, *, tenant_id: str, unidade_id: str, pedido_id: str, prioridade: int, motivo: str, idempotency_key: str, usuario_id: str, correlation_id: str) -> str:
        del motivo, idempotency_key, usuario_id, correlation_id
        itens = self._itens_pedido(tenant_id, unidade_id, pedido_id)
        if not itens:
            raise ErroGerenteIA("recurso_indisponivel")
        agora = datetime.now(timezone.utc)
        for item in itens:
            item.prioridade = prioridade
            item.versao += 1
            item.atualizado_em = agora
        self._session.flush()
        return f"pedido_priorizado:{pedido_id}:{prioridade}:{len(itens)}"

    def _produto_existe(self, tenant_id: str, unidade_id: str, produto_id: str) -> bool:
        return bool(
            self._session.scalar(
                select(func.count()).select_from(ItemPedidoORM).where(
                    ItemPedidoORM.tenant_id == tenant_id,
                    ItemPedidoORM.unidade_id == unidade_id,
                    ItemPedidoORM.produto_id == produto_id,
                )
            )
        )

    def previsualizar_pausa_produto(self, *, tenant_id: str, unidade_id: str, produto_id: str, duracao_minutos: int | None) -> RegistroGerencial:
        row = self._session.get(DisponibilidadeProdutoORM, (tenant_id, unidade_id, produto_id))
        if row is None and not self._produto_existe(tenant_id, unidade_id, produto_id):
            raise ErroGerenteIA("recurso_indisponivel")
        return _registro(
            "preview_pausa_produto",
            produto_id=produto_id,
            ativo=not bool(row and row.pausado),
            duracao_minutos=duracao_minutos,
            versao=row.versao if row else 0,
        )

    def pausar_produto(self, *, tenant_id: str, unidade_id: str, produto_id: str, motivo: str, duracao_minutos: int | None, idempotency_key: str, usuario_id: str, correlation_id: str) -> str:
        del idempotency_key
        if not self._produto_existe(tenant_id, unidade_id, produto_id):
            raise ErroGerenteIA("recurso_indisponivel")
        agora = datetime.now(timezone.utc)
        row = self._session.get(DisponibilidadeProdutoORM, (tenant_id, unidade_id, produto_id))
        if row is None:
            row = DisponibilidadeProdutoORM(
                tenant_id=tenant_id,
                unidade_id=unidade_id,
                produto_id=produto_id,
                pausado=True,
                pausado_ate=agora + timedelta(minutes=duracao_minutos) if duracao_minutos else None,
                motivo=motivo,
                versao=1,
                atualizado_por=usuario_id,
                correlation_id=correlation_id,
                atualizado_em=agora,
            )
            self._session.add(row)
        else:
            row.pausado = True
            row.pausado_ate = agora + timedelta(minutes=duracao_minutos) if duracao_minutos else None
            row.motivo = motivo
            row.versao += 1
            row.atualizado_por = usuario_id
            row.correlation_id = correlation_id
            row.atualizado_em = agora
        self._session.flush()
        return f"produto_pausado:{produto_id}:{row.versao}"


class CampanhasGerenciaisSQLAlchemy:
    def __init__(self, session: Session) -> None:
        self._session = session

    def preparar_rascunho(self, *, tenant_id: str, unidade_id: str, canal: str, finalidade: str, objetivo: str, texto_base: str, usuario_id: str, correlation_id: str, idempotency_key: str) -> RascunhoCampanha:
        existente = self._session.scalar(
            select(RascunhoCampanhaORM).where(
                RascunhoCampanhaORM.tenant_id == tenant_id,
                RascunhoCampanhaORM.unidade_id == unidade_id,
                RascunhoCampanhaORM.idempotency_key == idempotency_key,
            )
        )
        if existente is None:
            audiencia = int(
                self._session.scalar(
                    select(func.count()).select_from(ConsentimentoCRMAtualORM).where(
                        ConsentimentoCRMAtualORM.tenant_id == tenant_id,
                        ConsentimentoCRMAtualORM.unidade_id == unidade_id,
                        ConsentimentoCRMAtualORM.canal == canal,
                        ConsentimentoCRMAtualORM.finalidade == finalidade,
                        ConsentimentoCRMAtualORM.status == "concedido",
                    )
                ) or 0
            )
            agora = datetime.now(timezone.utc)
            existente = RascunhoCampanhaORM(
                rascunho_id=f"camp_{uuid4().hex}",
                tenant_id=tenant_id,
                unidade_id=unidade_id,
                canal=canal,
                finalidade=finalidade,
                objetivo=objetivo,
                texto_base=texto_base,
                audiencia_elegivel=audiencia,
                criado_em=agora,
                criado_por=usuario_id,
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
                status="rascunho",
            )
            self._session.add(existente)
            self._session.flush()
        return RascunhoCampanha(
            rascunho_id=existente.rascunho_id,
            tenant_id=existente.tenant_id,
            unidade_id=existente.unidade_id,
            canal=existente.canal,
            finalidade=existente.finalidade,
            objetivo=existente.objetivo,
            texto_base=existente.texto_base,
            audiencia_elegivel=existente.audiencia_elegivel,
            criado_em=_utc(existente.criado_em),
            criado_por=existente.criado_por,
            status=existente.status,
        )


_SENSITIVE_KEYS = frozenset({"senha", "password", "token", "secret", "segredo", "api_key", "authorization", "telefone", "email", "cpf", "endereco"})


def _payload_seguro(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            str(chave): "[REDACTED]" if str(chave).casefold() in _SENSITIVE_KEYS else _payload_seguro(valor)
            for chave, valor in payload.items()
        }
    if isinstance(payload, (tuple, list)):
        return [_payload_seguro(item) for item in payload]
    if isinstance(payload, (str, int, float, bool)) or payload is None:
        return payload
    return str(payload)


class ConsumidorEventosCoreSQLAlchemy:
    """Consumer idempotente de envelopes reais internos para a projeção do Core."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def consumir(self, mensagem: EnvelopeMensagem) -> bool:
        tenant_id, unidade_id = str(mensagem.tenant_id), str(mensagem.unidade_id)
        existente = self._session.scalar(
            select(EventoCoreORM).where(
                EventoCoreORM.tenant_id == tenant_id,
                EventoCoreORM.unidade_id == unidade_id,
                EventoCoreORM.idempotency_key == str(mensagem.idempotency_key),
            )
        )
        if existente is not None:
            return False
        payload = _payload_seguro(mensagem.para_dict()["payload"])
        self._session.add(
            EventoCoreORM(
                event_id=str(mensagem.event_id),
                tenant_id=tenant_id,
                unidade_id=unidade_id,
                event_type=mensagem.event_type,
                aggregate_id=mensagem.aggregate_id,
                aggregate_type=mensagem.aggregate_type,
                correlation_id=str(mensagem.correlation_id),
                causation_id=str(mensagem.causation_id) if mensagem.causation_id else None,
                idempotency_key=str(mensagem.idempotency_key),
                ocorrido_em=mensagem.occurred_at,
                payload_seguro=payload,
                versao=mensagem.version,
                processado_em=datetime.now(timezone.utc),
            )
        )
        if mensagem.event_type in {"cliente.consentiu_marketing", "cliente.cancelou_marketing"}:
            self._projetar_consentimento(tenant_id, unidade_id, mensagem, cast(dict[str, Any], payload))
        self._session.flush()
        return True

    def _projetar_consentimento(self, tenant_id: str, unidade_id: str, mensagem: EnvelopeMensagem, payload: dict[str, Any]) -> None:
        chave = (
            tenant_id,
            unidade_id,
            str(payload.get("cliente_id", mensagem.aggregate_id)),
            str(payload.get("canal", "")),
            str(payload.get("finalidade", "")),
        )
        if not chave[3] or not chave[4]:
            raise ErroGerenteIA("evento_crm_invalido")
        row = self._session.get(ConsentimentoCRMAtualORM, chave)
        status = str(payload.get("status", "revogado"))
        atualizado_em = mensagem.occurred_at
        correlation_id = str(mensagem.correlation_id)
        if row is None:
            self._session.add(
                ConsentimentoCRMAtualORM(
                    tenant_id=chave[0], unidade_id=chave[1], cliente_id=chave[2],
                    canal=chave[3], finalidade=chave[4], status=status,
                    atualizado_em=atualizado_em, correlation_id=correlation_id,
                )
            )
        elif _utc(row.atualizado_em) <= mensagem.occurred_at:
            row.status = status
            row.atualizado_em = atualizado_em
            row.correlation_id = correlation_id
