"""Runtime in-memory da PR19; sem banco, mensageria ou marketing reais."""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from threading import RLock

from core.eventos.modelos import EnvelopeMensagem
from core.eventos.repositorios import RepositorioOutboxEmMemoria
from core.seguranca.auditoria import RepositorioAuditoriaEmMemoria

from .erros import ErroCRM
from .modelos import (
    BeneficioCRM,
    CanalMarketing,
    ClienteCRM,
    ClienteMarketplaceRestrito,
    ConsentimentoMarketing,
    EtapaFunilCRM,
    EventoFunilCRM,
    FinalidadeMarketing,
    StatusConsentimento,
    TipoBeneficioCRM,
    moeda,
)
from .servicos import ServicoCRM, _id


class HashIdentidadeHMACTeste:
    """HMAC determinístico; a chave de teste nunca representa segredo de produção."""

    def __init__(self, chave: bytes = b"fm-ai-crm-test-only") -> None:
        self._chave = chave

    def hash_marketplace(self, *, integracao_id: str, id_externo: str) -> str:
        if not integracao_id.strip() or not id_externo.strip():
            raise ErroCRM("identidade_marketplace_invalida")
        mensagem = f"{integracao_id}:{id_externo}".encode()
        return hmac.new(self._chave, mensagem, hashlib.sha256).hexdigest()


class MemoriaClientesCRM:
    def __init__(self) -> None:
        self._lock = RLock()
        self._dados: dict[tuple[str, str, str], ClienteCRM] = {}

    @staticmethod
    def _chave(cliente: ClienteCRM) -> tuple[str, str, str]:
        return cliente.tenant_id, cliente.unidade_id, cliente.cliente_id

    def registrar(self, cliente: ClienteCRM) -> tuple[ClienteCRM, bool]:
        chave = self._chave(cliente)
        with self._lock:
            existente = self._dados.get(chave)
            if existente is not None:
                semantica_existente = replace(existente, criado_em=cliente.criado_em)
                if semantica_existente != cliente:
                    raise ErroCRM("cliente_id_em_conflito")
                return existente, True
            self._dados[chave] = cliente
            return cliente, False

    def obter(
        self, *, tenant_id: str, unidade_id: str, cliente_id: str
    ) -> ClienteCRM | None:
        with self._lock:
            return self._dados.get((tenant_id, unidade_id, cliente_id))

    def listar(self, *, tenant_id: str, unidade_id: str) -> tuple[ClienteCRM, ...]:
        with self._lock:
            return tuple(
                cliente
                for (tenant, unidade, _), cliente in self._dados.items()
                if tenant == tenant_id and unidade == unidade_id
            )


class MemoriaClientesMarketplaceCRM:
    def __init__(self) -> None:
        self._lock = RLock()
        self._dados: dict[tuple[str, str, str], ClienteMarketplaceRestrito] = {}
        self._por_hash: dict[tuple[str, str, str, str], tuple[str, str, str]] = {}

    @staticmethod
    def _chave(cliente: ClienteMarketplaceRestrito) -> tuple[str, str, str]:
        return (
            cliente.tenant_id,
            cliente.unidade_id,
            cliente.marketplace_cliente_id,
        )

    def registrar(
        self, cliente: ClienteMarketplaceRestrito
    ) -> tuple[ClienteMarketplaceRestrito, bool]:
        chave = self._chave(cliente)
        chave_hash = (
            cliente.tenant_id,
            cliente.unidade_id,
            cliente.integracao_id,
            cliente.id_externo_hash,
        )
        with self._lock:
            chave_existente = self._por_hash.get(chave_hash)
            if chave_existente is not None:
                return self._dados[chave_existente], True
            if chave in self._dados:
                raise ErroCRM("cliente_marketplace_id_em_conflito")
            self._dados[chave] = cliente
            self._por_hash[chave_hash] = chave
            return cliente, False

    def obter(
        self, *, tenant_id: str, unidade_id: str, marketplace_cliente_id: str
    ) -> ClienteMarketplaceRestrito | None:
        with self._lock:
            return self._dados.get((tenant_id, unidade_id, marketplace_cliente_id))

    def obter_por_hash(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        integracao_id: str,
        id_externo_hash: str,
    ) -> ClienteMarketplaceRestrito | None:
        with self._lock:
            chave = self._por_hash.get(
                (tenant_id, unidade_id, integracao_id, id_externo_hash)
            )
            return self._dados.get(chave) if chave is not None else None

    def marcar_convertido_cas(
        self,
        cliente: ClienteMarketplaceRestrito,
        *,
        cliente_id: str,
        expected_version: int,
    ) -> ClienteMarketplaceRestrito:
        chave = self._chave(cliente)
        with self._lock:
            atual = self._dados.get(chave)
            if atual is None:
                raise ErroCRM("recurso_indisponivel")
            if atual.versao != expected_version:
                raise ErroCRM("conflito_concorrencia")
            if atual.convertido_cliente_id not in {None, cliente_id}:
                raise ErroCRM("cliente_marketplace_ja_convertido")
            if atual.convertido_cliente_id == cliente_id:
                return atual
            novo = replace(
                atual,
                convertido_cliente_id=cliente_id,
                versao=atual.versao + 1,
            )
            self._dados[chave] = novo
            return novo

    def expurgar_expirados(self, *, agora: datetime) -> int:
        with self._lock:
            remover = [chave for chave, cliente in self._dados.items() if cliente.expira_em <= agora]
            for chave in remover:
                cliente = self._dados.pop(chave)
                self._por_hash.pop(
                    (
                        cliente.tenant_id,
                        cliente.unidade_id,
                        cliente.integracao_id,
                        cliente.id_externo_hash,
                    ),
                    None,
                )
            return len(remover)


class MemoriaConsentimentosCRM:
    def __init__(self, outbox: RepositorioOutboxEmMemoria) -> None:
        self._lock = RLock()
        self._outbox = outbox
        self._historico: list[ConsentimentoMarketing] = []
        self._idempotencia: dict[str, ConsentimentoMarketing] = {}
        self._atual: dict[
            tuple[str, str, str, CanalMarketing, FinalidadeMarketing],
            ConsentimentoMarketing,
        ] = {}

    @staticmethod
    def _chave(
        consentimento: ConsentimentoMarketing,
    ) -> tuple[str, str, str, CanalMarketing, FinalidadeMarketing]:
        return (
            consentimento.tenant_id,
            consentimento.unidade_id,
            consentimento.cliente_id,
            consentimento.canal,
            consentimento.finalidade,
        )

    @staticmethod
    def _mesma_semantica(
        a: ConsentimentoMarketing, b: ConsentimentoMarketing
    ) -> bool:
        return (
            a.tenant_id,
            a.unidade_id,
            a.cliente_id,
            a.canal,
            a.finalidade,
            a.status,
            a.base_legal,
            a.texto_versao,
            a.origem,
            a.prova_hash,
        ) == (
            b.tenant_id,
            b.unidade_id,
            b.cliente_id,
            b.canal,
            b.finalidade,
            b.status,
            b.base_legal,
            b.texto_versao,
            b.origem,
            b.prova_hash,
        )

    def registrar_com_evento(
        self,
        consentimento: ConsentimentoMarketing,
        mensagem: EnvelopeMensagem,
    ) -> tuple[ConsentimentoMarketing, bool]:
        with self._lock:
            existente = self._idempotencia.get(consentimento.idempotency_key)
            if existente is not None:
                if not self._mesma_semantica(existente, consentimento):
                    raise ErroCRM("conflito_idempotencia_consentimento")
                return existente, True
            self._outbox.adicionar(mensagem)
            self._historico.append(consentimento)
            self._idempotencia[consentimento.idempotency_key] = consentimento
            chave = self._chave(consentimento)
            atual = self._atual.get(chave)
            if (
                atual is None
                or consentimento.ocorrido_em > atual.ocorrido_em
                or (
                    consentimento.ocorrido_em == atual.ocorrido_em
                    and consentimento.status is StatusConsentimento.REVOGADO
                )
            ):
                self._atual[chave] = consentimento
            return consentimento, False

    def atual(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        cliente_id: str,
        canal: CanalMarketing,
        finalidade: FinalidadeMarketing,
    ) -> ConsentimentoMarketing | None:
        with self._lock:
            return self._atual.get(
                (tenant_id, unidade_id, cliente_id, canal, finalidade)
            )

    def historico(
        self, *, tenant_id: str, unidade_id: str, cliente_id: str
    ) -> tuple[ConsentimentoMarketing, ...]:
        with self._lock:
            return tuple(
                evento
                for evento in self._historico
                if evento.tenant_id == tenant_id
                and evento.unidade_id == unidade_id
                and evento.cliente_id == cliente_id
            )

    def listar_atuais(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        canal: CanalMarketing,
        finalidade: FinalidadeMarketing,
        status: StatusConsentimento,
    ) -> tuple[ConsentimentoMarketing, ...]:
        with self._lock:
            return tuple(
                evento
                for (tenant, unidade, _, canal_atual, finalidade_atual), evento in self._atual.items()
                if tenant == tenant_id
                and unidade == unidade_id
                and canal_atual is canal
                and finalidade_atual is finalidade
                and evento.status is status
            )


class MemoriaFunilCRM:
    def __init__(self) -> None:
        self._lock = RLock()
        self._eventos: list[EventoFunilCRM] = []
        self._idempotencia: dict[str, EventoFunilCRM] = {}

    def registrar(self, evento: EventoFunilCRM) -> tuple[EventoFunilCRM, bool]:
        with self._lock:
            existente = self._idempotencia.get(evento.idempotency_key)
            if existente is not None:
                if existente.etapa is not evento.etapa or existente.sujeito_ref != evento.sujeito_ref:
                    raise ErroCRM("conflito_idempotencia_funil")
                return existente, True
            self._idempotencia[evento.idempotency_key] = evento
            self._eventos.append(evento)
            return evento, False

    def listar(
        self, *, tenant_id: str, unidade_id: str
    ) -> tuple[EventoFunilCRM, ...]:
        with self._lock:
            return tuple(
                evento
                for evento in self._eventos
                if evento.tenant_id == tenant_id and evento.unidade_id == unidade_id
            )


class MemoriaBeneficiosCRM:
    def __init__(self) -> None:
        self._lock = RLock()
        self._idempotencia: dict[str, BeneficioCRM] = {}

    def emitir(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        cliente_id: str,
        tipo: TipoBeneficioCRM,
        valor: Decimal,
        idempotency_key: str,
    ) -> tuple[BeneficioCRM, bool]:
        with self._lock:
            existente = self._idempotencia.get(idempotency_key)
            if existente is not None:
                if (
                    existente.tenant_id != tenant_id
                    or existente.unidade_id != unidade_id
                    or existente.cliente_id != cliente_id
                    or existente.tipo is not tipo
                    or existente.valor != moeda(valor)
                ):
                    raise ErroCRM("conflito_idempotencia_beneficio")
                return existente, True
            beneficio = BeneficioCRM(
                beneficio_id=_id("benef", idempotency_key),
                tenant_id=tenant_id,
                unidade_id=unidade_id,
                cliente_id=cliente_id,
                tipo=tipo,
                valor=valor,
                referencia=(
                    f"CUPOM-{_id('c', idempotency_key)[2:10].upper()}"
                    if tipo is TipoBeneficioCRM.CUPOM
                    else f"cashback://{_id('cb', idempotency_key)}"
                ),
                emitido_em=datetime.now().astimezone(),
                idempotency_key=idempotency_key,
            )
            self._idempotencia[idempotency_key] = beneficio
            return beneficio, False


class EnvioMarketingFake:
    def __init__(self) -> None:
        self.envios: list[tuple[str, str, str]] = []
        self._idempotencia: set[str] = set()

    def enviar(
        self,
        *,
        referencia_contato: str,
        campanha_ref: str,
        idempotency_key: str,
    ) -> None:
        if idempotency_key in self._idempotencia:
            return
        self._idempotencia.add(idempotency_key)
        self.envios.append((referencia_contato, campanha_ref, idempotency_key))


class RuntimeCRMTeste:
    def __init__(self) -> None:
        self.outbox = RepositorioOutboxEmMemoria()
        self.auditoria = RepositorioAuditoriaEmMemoria()
        self.clientes = MemoriaClientesCRM()
        self.marketplace_clientes = MemoriaClientesMarketplaceCRM()
        self.consentimentos = MemoriaConsentimentosCRM(self.outbox)
        self.funil = MemoriaFunilCRM()
        self.beneficios = MemoriaBeneficiosCRM()
        self.hash_identidade = HashIdentidadeHMACTeste()
        self.envio = EnvioMarketingFake()
        self.servico = ServicoCRM(
            clientes=self.clientes,
            marketplace_clientes=self.marketplace_clientes,
            consentimentos=self.consentimentos,
            funil=self.funil,
            beneficios=self.beneficios,
            hash_identidade=self.hash_identidade,
            auditoria=self.auditoria,
        )
