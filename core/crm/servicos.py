"""Serviços de CRM: marketing negado por padrão e conversão consentida."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from core.dominio.ids import (
    CorrelationId,
    EventoId,
    IdempotencyKey,
    TenantId,
    UnidadeId,
)
from core.eventos.modelos import EnvelopeMensagem
from core.marketplaces.modelos import PlataformaMarketplace
from core.seguranca.auditoria import EventoAuditoria, RepositorioAuditoria

from .adapters import (
    PortaBeneficiosCRM,
    PortaClientesCRM,
    PortaClientesMarketplaceCRM,
    PortaConsentimentosCRM,
    PortaEnvioMarketing,
    PortaFunilCRM,
    PortaHashIdentidadeCRM,
)
from .erros import ErroCRM
from .modelos import (
    BaseLegalMarketing,
    CanalMarketing,
    ClienteCRM,
    ClienteMarketplaceRestrito,
    ConsentimentoMarketing,
    ContatoCRM,
    EtapaFunilCRM,
    EventoFunilCRM,
    FinalidadeMarketing,
    OrigemClienteCRM,
    ResultadoConversaoCRM,
    ResultadoDespachoMarketing,
    ResumoFunilCRM,
    StatusConsentimento,
    TipoBeneficioCRM,
    moeda,
)


def _id(prefixo: str, chave: str) -> str:
    digest = hashlib.sha256(chave.encode("utf-8")).hexdigest()[:24]
    return f"{prefixo}_{digest}"


def _hash_prova(prova: str) -> str:
    conteudo = prova.strip()
    if not conteudo:
        raise ErroCRM("prova_consentimento_obrigatoria")
    return hashlib.sha256(conteudo.encode("utf-8")).hexdigest()


def _agora(valor: datetime | None) -> datetime:
    instante = valor or datetime.now(timezone.utc)
    if instante.tzinfo is None or instante.utcoffset() is None:
        raise ErroCRM("timestamp_sem_timezone")
    return instante.astimezone(timezone.utc)


class ServicoCRM:
    def __init__(
        self,
        *,
        clientes: PortaClientesCRM,
        marketplace_clientes: PortaClientesMarketplaceCRM,
        consentimentos: PortaConsentimentosCRM,
        funil: PortaFunilCRM,
        beneficios: PortaBeneficiosCRM,
        hash_identidade: PortaHashIdentidadeCRM,
        auditoria: RepositorioAuditoria | None = None,
    ) -> None:
        self.clientes = clientes
        self.marketplace_clientes = marketplace_clientes
        self.consentimentos = consentimentos
        self.funil = funil
        self.beneficios = beneficios
        self.hash_identidade = hash_identidade
        self.auditoria = auditoria

    def _cliente(
        self, *, tenant_id: str, unidade_id: str, cliente_id: str
    ) -> ClienteCRM:
        cliente = self.clientes.obter(
            tenant_id=tenant_id, unidade_id=unidade_id, cliente_id=cliente_id
        )
        if cliente is None:
            raise ErroCRM("recurso_indisponivel")
        return cliente

    def _registrar_funil(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        sujeito_ref: str,
        etapa: EtapaFunilCRM,
        idempotency_key: str,
        ocorrido_em: datetime,
        plataforma: PlataformaMarketplace | None = None,
        cliente_id: str | None = None,
    ) -> None:
        evento = EventoFunilCRM(
            evento_id=_id("funil", idempotency_key),
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            sujeito_ref=sujeito_ref,
            etapa=etapa,
            ocorrido_em=ocorrido_em,
            idempotency_key=idempotency_key,
            plataforma=plataforma,
            cliente_id=cliente_id,
        )
        self.funil.registrar(evento)

    def _auditar(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        usuario_id: str,
        acao: str,
        recurso_tipo: str,
        recurso_id: str,
        correlation_id: str,
        timestamp: datetime,
        metadata: dict[str, str] | None = None,
    ) -> None:
        if self.auditoria is None:
            return
        self.auditoria.adicionar(
            EventoAuditoria(
                audit_id=_id("audit", f"{acao}:{recurso_id}:{correlation_id}"),
                tenant_id=tenant_id,
                unidade_id=unidade_id,
                usuario_id=usuario_id,
                papel_efetivo=None,
                acao=acao,
                recurso_tipo=recurso_tipo,
                recurso_id=recurso_id,
                resultado="sucesso",
                motivo="acao_crm_solicitada",
                correlation_id=correlation_id,
                timestamp=timestamp,
                origem="crm_v1",
                politica="marketing_consentido_v1",
                metadata=tuple(sorted((metadata or {}).items())),
            )
        )

    def registrar_cliente(
        self,
        *,
        cliente_id: str,
        tenant_id: str,
        unidade_id: str,
        origem: OrigemClienteCRM,
        contatos: tuple[ContatoCRM, ...],
        marketplace_origem: PlataformaMarketplace | None = None,
        agora: datetime | None = None,
    ) -> tuple[ClienteCRM, bool]:
        cliente = ClienteCRM(
            cliente_id=cliente_id,
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            origem=origem,
            contatos=contatos,
            criado_em=_agora(agora),
            marketplace_origem=marketplace_origem,
        )
        return self.clientes.registrar(cliente)

    def registrar_cliente_marketplace_restrito(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        integracao_id: str,
        plataforma: PlataformaMarketplace,
        id_externo: str,
        apelido: str | None,
        idempotency_key: str,
        ttl_dias: int = 90,
        agora: datetime | None = None,
    ) -> ClienteMarketplaceRestrito:
        if not id_externo.strip() or not idempotency_key.strip():
            raise ErroCRM("identidade_marketplace_invalida")
        if ttl_dias < 1 or ttl_dias > 365:
            raise ErroCRM("ttl_marketplace_invalido")
        instante = _agora(agora)
        identidade_hash = self.hash_identidade.hash_marketplace(
            integracao_id=integracao_id, id_externo=id_externo
        )
        existente = self.marketplace_clientes.obter_por_hash(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            integracao_id=integracao_id,
            id_externo_hash=identidade_hash,
        )
        if existente is not None:
            return existente
        sujeito_id = _id(
            "mktcli", f"{tenant_id}:{unidade_id}:{integracao_id}:{identidade_hash}"
        )
        cliente = ClienteMarketplaceRestrito(
            marketplace_cliente_id=sujeito_id,
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            integracao_id=integracao_id,
            plataforma=plataforma,
            id_externo_hash=identidade_hash,
            criado_em=instante,
            expira_em=instante + timedelta(days=ttl_dias),
            apelido=apelido,
        )
        salvo, criado = self.marketplace_clientes.registrar(cliente)
        if criado:
            self._registrar_funil(
                tenant_id=tenant_id,
                unidade_id=unidade_id,
                sujeito_ref=salvo.marketplace_cliente_id,
                etapa=EtapaFunilCRM.MARKETPLACE_RESTRITO,
                idempotency_key=f"crm:funil:restrito:{idempotency_key}",
                ocorrido_em=instante,
                plataforma=plataforma,
            )
        return salvo

    def _envelope_consentimento(
        self, consentimento: ConsentimentoMarketing
    ) -> EnvelopeMensagem:
        tipo = (
            "cliente.consentiu_marketing"
            if consentimento.status is StatusConsentimento.CONCEDIDO
            else "cliente.cancelou_marketing"
        )
        return EnvelopeMensagem(
            event_id=EventoId.de(_id("evt", consentimento.idempotency_key)),
            event_type=tipo,
            aggregate_id=consentimento.cliente_id,
            aggregate_type="cliente",
            tenant_id=TenantId.de(consentimento.tenant_id),
            unidade_id=UnidadeId.de(consentimento.unidade_id),
            correlation_id=CorrelationId.de(consentimento.correlation_id),
            causation_id=None,
            idempotency_key=IdempotencyKey.de(
                f"crm:consentimento:{consentimento.idempotency_key}"
            ),
            occurred_at=consentimento.ocorrido_em,
            payload={
                "cliente_id": consentimento.cliente_id,
                "canal": consentimento.canal.value,
                "finalidade": consentimento.finalidade.value,
                "texto_versao": consentimento.texto_versao,
                "status": consentimento.status.value,
            },
        )

    def conceder_consentimento(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        cliente_id: str,
        canal: CanalMarketing,
        finalidade: FinalidadeMarketing,
        texto_versao: str,
        origem: str,
        prova: str,
        idempotency_key: str,
        correlation_id: str,
        agora: datetime | None = None,
    ) -> ConsentimentoMarketing:
        if not idempotency_key.strip() or not correlation_id.strip():
            raise ErroCRM("idempotencia_e_correlacao_obrigatorias")
        cliente = self._cliente(
            tenant_id=tenant_id, unidade_id=unidade_id, cliente_id=cliente_id
        )
        if cliente.contato_para(canal) is None:
            raise ErroCRM("cliente_sem_canal_solicitado")
        instante = _agora(agora)
        consentimento = ConsentimentoMarketing(
            consentimento_id=_id("cons", idempotency_key),
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            cliente_id=cliente_id,
            canal=canal,
            finalidade=finalidade,
            status=StatusConsentimento.CONCEDIDO,
            base_legal=BaseLegalMarketing.CONSENTIMENTO,
            texto_versao=texto_versao,
            origem=origem,
            prova_hash=_hash_prova(prova),
            ocorrido_em=instante,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
            concedido_em=instante,
        )
        salvo, idempotente = self.consentimentos.registrar_com_evento(
            consentimento, self._envelope_consentimento(consentimento)
        )
        if not idempotente:
            self._registrar_funil(
                tenant_id=tenant_id,
                unidade_id=unidade_id,
                sujeito_ref=cliente_id,
                etapa=EtapaFunilCRM.CONSENTIMENTO_CONCEDIDO,
                idempotency_key=f"crm:funil:consentiu:{idempotency_key}",
                ocorrido_em=instante,
                plataforma=cliente.marketplace_origem,
                cliente_id=cliente_id,
            )
            self._auditar(
                tenant_id=tenant_id,
                unidade_id=unidade_id,
                usuario_id=f"cliente:{cliente_id}",
                acao="consentimento.conceder",
                recurso_tipo="ConsentimentoMarketing",
                recurso_id=salvo.consentimento_id,
                correlation_id=correlation_id,
                timestamp=instante,
                metadata={"canal": canal.value, "finalidade": finalidade.value},
            )
        return salvo

    def revogar_consentimento(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        cliente_id: str,
        canal: CanalMarketing,
        finalidade: FinalidadeMarketing,
        origem: str,
        prova: str,
        idempotency_key: str,
        correlation_id: str,
        agora: datetime | None = None,
    ) -> ConsentimentoMarketing:
        cliente = self._cliente(
            tenant_id=tenant_id, unidade_id=unidade_id, cliente_id=cliente_id
        )
        if not idempotency_key.strip() or not correlation_id.strip():
            raise ErroCRM("idempotencia_e_correlacao_obrigatorias")
        instante = _agora(agora)
        atual = self.consentimentos.atual(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            cliente_id=cliente_id,
            canal=canal,
            finalidade=finalidade,
        )
        texto_versao = atual.texto_versao if atual else "optout-v1"
        revogacao = ConsentimentoMarketing(
            consentimento_id=_id("cons", idempotency_key),
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            cliente_id=cliente_id,
            canal=canal,
            finalidade=finalidade,
            status=StatusConsentimento.REVOGADO,
            base_legal=BaseLegalMarketing.CONSENTIMENTO,
            texto_versao=texto_versao,
            origem=origem,
            prova_hash=_hash_prova(prova),
            ocorrido_em=instante,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
            revogado_em=instante,
        )
        salvo, idempotente = self.consentimentos.registrar_com_evento(
            revogacao, self._envelope_consentimento(revogacao)
        )
        if not idempotente:
            self._registrar_funil(
                tenant_id=tenant_id,
                unidade_id=unidade_id,
                sujeito_ref=cliente_id,
                etapa=EtapaFunilCRM.OPT_OUT,
                idempotency_key=f"crm:funil:optout:{idempotency_key}",
                ocorrido_em=instante,
                plataforma=cliente.marketplace_origem,
                cliente_id=cliente_id,
            )
            self._auditar(
                tenant_id=tenant_id,
                unidade_id=unidade_id,
                usuario_id=f"cliente:{cliente_id}",
                acao="consentimento.revogar",
                recurso_tipo="ConsentimentoMarketing",
                recurso_id=salvo.consentimento_id,
                correlation_id=correlation_id,
                timestamp=instante,
                metadata={"canal": canal.value, "finalidade": finalidade.value},
            )
        return salvo

    def pode_enviar_marketing(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        cliente_id: str,
        canal: CanalMarketing,
        finalidade: FinalidadeMarketing,
    ) -> bool:
        cliente = self.clientes.obter(
            tenant_id=tenant_id, unidade_id=unidade_id, cliente_id=cliente_id
        )
        if cliente is None or cliente.contato_para(canal) is None:
            return False
        atual = self.consentimentos.atual(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            cliente_id=cliente_id,
            canal=canal,
            finalidade=finalidade,
        )
        return bool(atual and atual.status is StatusConsentimento.CONCEDIDO)

    def listar_elegiveis(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        canal: CanalMarketing,
        finalidade: FinalidadeMarketing,
    ) -> tuple[str, ...]:
        atuais = self.consentimentos.listar_atuais(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            canal=canal,
            finalidade=finalidade,
            status=StatusConsentimento.CONCEDIDO,
        )
        candidatos = sorted({item.cliente_id for item in atuais})
        return tuple(
            cliente_id
            for cliente_id in candidatos
            if self.pode_enviar_marketing(
                tenant_id=tenant_id,
                unidade_id=unidade_id,
                cliente_id=cliente_id,
                canal=canal,
                finalidade=finalidade,
            )
        )

    def despachar_marketing(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        cliente_id: str,
        canal: CanalMarketing,
        finalidade: FinalidadeMarketing,
        campanha_ref: str,
        idempotency_key: str,
        envio: PortaEnvioMarketing,
    ) -> ResultadoDespachoMarketing:
        if not campanha_ref.strip() or not idempotency_key.strip():
            raise ErroCRM("campanha_e_idempotencia_obrigatorias")
        if not self.pode_enviar_marketing(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            cliente_id=cliente_id,
            canal=canal,
            finalidade=finalidade,
        ):
            return ResultadoDespachoMarketing(False, "marketing_sem_consentimento")
        cliente = self._cliente(
            tenant_id=tenant_id, unidade_id=unidade_id, cliente_id=cliente_id
        )
        contato = cliente.contato_para(canal)
        if contato is None:
            return ResultadoDespachoMarketing(False, "canal_indisponivel")
        envio.enviar(
            referencia_contato=contato.referencia,
            campanha_ref=campanha_ref,
            idempotency_key=idempotency_key,
        )
        return ResultadoDespachoMarketing(True, "enviado")

    def converter_cliente_marketplace(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        marketplace_cliente_id: str,
        cliente_id: str,
        contato: ContatoCRM,
        finalidade: FinalidadeMarketing,
        texto_versao: str,
        origem_consentimento: str,
        prova: str,
        idempotency_key: str,
        correlation_id: str,
        agora: datetime | None = None,
    ) -> ResultadoConversaoCRM:
        instante = _agora(agora)
        restrito = self.marketplace_clientes.obter(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            marketplace_cliente_id=marketplace_cliente_id,
        )
        if restrito is None:
            raise ErroCRM("recurso_indisponivel")
        if restrito.expira_em <= instante:
            raise ErroCRM("cliente_marketplace_expirado")
        if restrito.convertido_cliente_id not in {None, cliente_id}:
            raise ErroCRM("cliente_marketplace_ja_convertido")

        cliente, cliente_existia = self.registrar_cliente(
            cliente_id=cliente_id,
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            origem=OrigemClienteCRM.MARKETPLACE_CONVERTIDO,
            contatos=(contato,),
            marketplace_origem=restrito.plataforma,
            agora=instante,
        )
        convertido = restrito
        if restrito.convertido_cliente_id is None:
            convertido = self.marketplace_clientes.marcar_convertido_cas(
                restrito,
                cliente_id=cliente_id,
                expected_version=restrito.versao,
            )
        consentimento = self.conceder_consentimento(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            cliente_id=cliente_id,
            canal=contato.canal,
            finalidade=finalidade,
            texto_versao=texto_versao,
            origem=origem_consentimento,
            prova=prova,
            idempotency_key=f"{idempotency_key}:consentimento",
            correlation_id=correlation_id,
            agora=instante,
        )
        self._registrar_funil(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            sujeito_ref=convertido.marketplace_cliente_id,
            etapa=EtapaFunilCRM.CONVERTIDO,
            idempotency_key=f"crm:funil:conversao:{idempotency_key}",
            ocorrido_em=instante,
            plataforma=convertido.plataforma,
            cliente_id=cliente_id,
        )
        self._auditar(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            usuario_id=f"cliente:{cliente_id}",
            acao="cliente_marketplace.converter",
            recurso_tipo="ClienteMarketplace",
            recurso_id=convertido.marketplace_cliente_id,
            correlation_id=correlation_id,
            timestamp=instante,
            metadata={"plataforma": convertido.plataforma.value},
        )
        return ResultadoConversaoCRM(
            cliente=cliente,
            consentimento=consentimento,
            idempotente=cliente_existia and restrito.convertido_cliente_id == cliente_id,
        )

    def emitir_beneficio_conversao(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        cliente_id: str,
        canal: CanalMarketing,
        finalidade: FinalidadeMarketing,
        tipo: TipoBeneficioCRM,
        valor: Decimal,
        idempotency_key: str,
        correlation_id: str,
        agora: datetime | None = None,
    ):
        cliente = self._cliente(
            tenant_id=tenant_id, unidade_id=unidade_id, cliente_id=cliente_id
        )
        if cliente.origem is not OrigemClienteCRM.MARKETPLACE_CONVERTIDO:
            raise ErroCRM("beneficio_conversao_apenas_marketplace_convertido")
        if not self.pode_enviar_marketing(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            cliente_id=cliente_id,
            canal=canal,
            finalidade=finalidade,
        ):
            raise ErroCRM("beneficio_conversao_sem_consentimento")
        valor = moeda(valor)
        if valor <= 0:
            raise ErroCRM("beneficio_valor_invalido")
        beneficio, idempotente = self.beneficios.emitir(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            cliente_id=cliente_id,
            tipo=tipo,
            valor=valor,
            idempotency_key=idempotency_key,
        )
        if not idempotente:
            instante = _agora(agora)
            self._registrar_funil(
                tenant_id=tenant_id,
                unidade_id=unidade_id,
                sujeito_ref=cliente_id,
                etapa=EtapaFunilCRM.BENEFICIO_EMITIDO,
                idempotency_key=f"crm:funil:beneficio:{idempotency_key}",
                ocorrido_em=instante,
                plataforma=cliente.marketplace_origem,
                cliente_id=cliente_id,
            )
            self._auditar(
                tenant_id=tenant_id,
                unidade_id=unidade_id,
                usuario_id=f"cliente:{cliente_id}",
                acao="crm.beneficio_conversao",
                recurso_tipo="BeneficioCRM",
                recurso_id=beneficio.beneficio_id,
                correlation_id=correlation_id,
                timestamp=instante,
                metadata={"tipo": tipo.value},
            )
        return beneficio

    def expurgar_marketplace_expirados(self, *, agora: datetime | None = None) -> int:
        return self.marketplace_clientes.expurgar_expirados(agora=_agora(agora))

    def resumo_funil(
        self, *, tenant_id: str, unidade_id: str
    ) -> ResumoFunilCRM:
        eventos = self.funil.listar(tenant_id=tenant_id, unidade_id=unidade_id)
        contagens = {etapa: 0 for etapa in EtapaFunilCRM}
        for evento in eventos:
            contagens[evento.etapa] += 1
        return ResumoFunilCRM(
            marketplace_restritos=contagens[EtapaFunilCRM.MARKETPLACE_RESTRITO],
            consentimentos_concedidos=contagens[
                EtapaFunilCRM.CONSENTIMENTO_CONCEDIDO
            ],
            convertidos=contagens[EtapaFunilCRM.CONVERTIDO],
            beneficios_emitidos=contagens[EtapaFunilCRM.BENEFICIO_EMITIDO],
            opt_outs=contagens[EtapaFunilCRM.OPT_OUT],
        )
