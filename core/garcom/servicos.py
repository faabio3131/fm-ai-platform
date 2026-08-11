"""Composição da interface do garçom sobre Salão e KDS autoritativos."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError

from core.kds import RepositorioKDSSQLAlchemy
from core.salao import (
    Comanda,
    RepositorioSalaoSQLAlchemy,
    ServicoSalao,
    StatusMesa,
)
from core.seguranca import AutorizarAcao, ContextoExecucao, Papel, Permissao

from .erros import ErroGarcom
from .modelos import (
    AlertaProntoGarcom,
    PainelGarcom,
    ResumoComandaGarcom,
    ResumoMesaGarcom,
)
from .observabilidade import ColetorMetricasGarcom


def _agora_utc() -> datetime:
    return datetime.now(timezone.utc)


def _elevado(contexto: ContextoExecucao) -> bool:
    return contexto.identidade_sistema or bool(
        contexto.papeis.intersection({Papel.ADMINISTRADOR, Papel.GERENTE})
    )


def _papel_exibicao(contexto: ContextoExecucao) -> str:
    if contexto.identidade_sistema:
        return "sistema"
    if Papel.ADMINISTRADOR in contexto.papeis:
        return Papel.ADMINISTRADOR.value
    if Papel.GERENTE in contexto.papeis:
        return Papel.GERENTE.value
    if Papel.GARCOM in contexto.papeis:
        return Papel.GARCOM.value
    return min((p.value for p in contexto.papeis), default="sem_papel")


def _autorizar(
    contexto: ContextoExecucao,
    permissao: Permissao,
    recurso: str,
) -> None:
    if contexto.identidade_sistema:
        return
    decisao = AutorizarAcao().executar(
        contexto=contexto,
        permissao=permissao,
        recurso=recurso,
        tenant_recurso=contexto.tenant_id,
        unidade_recurso=contexto.unidade_id,
    )
    if not decisao.autorizado:
        raise ErroGarcom(decisao.codigo)


class ServicoGarcom:
    """Fachada segura para a jornada móvel do garçom.

    Salão e KDS continuam autoritativos. Esta classe só compõe projeções e
    acrescenta a alçada por responsável da comanda para o papel garçom.
    """

    def __init__(
        self,
        repositorio_salao: RepositorioSalaoSQLAlchemy,
        repositorio_kds: RepositorioKDSSQLAlchemy,
        *,
        agora: Callable[[], datetime] = _agora_utc,
        metricas: ColetorMetricasGarcom | None = None,
    ) -> None:
        if repositorio_salao.session is not repositorio_kds.session:
            raise ValueError("repositorios_devem_compartilhar_sessao")
        self.repositorio_salao = repositorio_salao
        self.repositorio_kds = repositorio_kds
        self.agora = agora
        self.metricas = metricas or ColetorMetricasGarcom()
        self.salao = ServicoSalao(repositorio_salao, agora=agora)

    def _obter_comanda_na_alcada(
        self, contexto: ContextoExecucao, comanda_id: str
    ) -> Comanda:
        comanda = self.repositorio_salao.obter_comanda(
            contexto.tenant_id, contexto.unidade_id, comanda_id
        )
        if comanda is None:
            raise ErroGarcom("comanda_indisponivel")
        if (
            not _elevado(contexto)
            and Papel.GARCOM in contexto.papeis
            and comanda.responsavel_id != contexto.usuario_id
        ):
            self.metricas.incrementar("garcom_alcada_negada")
            raise ErroGarcom("comanda_fora_alcada")
        return comanda

    def listar_painel(self, contexto: ContextoExecucao) -> PainelGarcom:
        _autorizar(contexto, Permissao.PEDIDO_VISUALIZAR, "interface_garcom")
        elevado = _elevado(contexto)
        mesas = self.repositorio_salao.listar_mesas(
            contexto.tenant_id, contexto.unidade_id
        )
        comandas_ativas = self.repositorio_salao.listar_comandas_ativas(
            contexto.tenant_id, contexto.unidade_id
        )
        comandas_visiveis = tuple(
            comanda
            for comanda in comandas_ativas
            if elevado or comanda.responsavel_id == contexto.usuario_id
        )
        mesas_da_alcada = {
            comanda.mesa_id for comanda in comandas_visiveis if comanda.mesa_id is not None
        }
        mesas_visiveis = tuple(
            mesa
            for mesa in mesas
            if elevado or mesa.status == StatusMesa.LIVRE or mesa.mesa_id in mesas_da_alcada
        )

        resumos_mesa = tuple(
            ResumoMesaGarcom(
                mesa_id=mesa.mesa_id,
                codigo=mesa.codigo,
                nome=mesa.nome,
                capacidade=mesa.capacidade,
                status=mesa.status.value,
                versao=mesa.versao,
                disponivel_para_abertura=(
                    mesa.status == StatusMesa.LIVRE
                    and Permissao.MESA_ABRIR in contexto.permissoes
                ),
            )
            for mesa in mesas_visiveis
        )
        resumos_comanda = tuple(
            ResumoComandaGarcom(
                comanda_id=comanda.comanda_id,
                mesa_id=comanda.mesa_id,
                numero=comanda.numero,
                status=comanda.status.value,
                responsavel_id=comanda.responsavel_id,
                total=comanda.total,
                saldo=comanda.saldo,
                versao=comanda.versao,
                propria=comanda.responsavel_id == contexto.usuario_id,
            )
            for comanda in comandas_visiveis
        )

        pedido_para_comanda: dict[str, Comanda] = {}
        for comanda in comandas_visiveis:
            for pedido in self.repositorio_salao.listar_pedidos(
                contexto.tenant_id, contexto.unidade_id, comanda.comanda_id
            ):
                pedido_para_comanda[pedido.pedido_id] = comanda

        mesas_por_id = {mesa.mesa_id: mesa for mesa in mesas_visiveis}
        alertas: list[AlertaProntoGarcom] = []
        kds_degradado = False
        try:
            itens_prontos = self.repositorio_kds.listar_fila(
                contexto.tenant_id,
                contexto.unidade_id,
                statuses=("pronta",),
            )
            for producao, setor in itens_prontos:
                comanda = pedido_para_comanda.get(producao.pedido_id)
                if comanda is None:
                    continue
                mesa = mesas_por_id.get(comanda.mesa_id) if comanda.mesa_id else None
                alertas.append(
                    AlertaProntoGarcom(
                        producao_id=producao.producao_id,
                        pedido_id=producao.pedido_id,
                        setor_id=setor.setor_id,
                        setor_nome=setor.nome,
                        comanda_id=comanda.comanda_id,
                        comanda_numero=comanda.numero,
                        mesa_id=comanda.mesa_id,
                        mesa_codigo=mesa.codigo if mesa else None,
                        pronta_em=producao.pronta_em or producao.atualizado_em,
                        versao=producao.versao,
                    )
                )
        except SQLAlchemyError:
            kds_degradado = True
            self.metricas.incrementar("garcom_kds_degradado")

        alertas.sort(key=lambda item: (item.pronta_em, item.producao_id))
        instante = self.agora().astimezone(timezone.utc)
        self.metricas.incrementar("garcom_painel_leitura")
        self.metricas.incrementar("garcom_alertas_prontos", len(alertas))
        return PainelGarcom(
            mesas=resumos_mesa,
            comandas=resumos_comanda,
            alertas_prontos=tuple(alertas),
            atualizado_em=instante,
            papel=_papel_exibicao(contexto),
            kds_degradado=kds_degradado,
        )

    def abrir_comanda(
        self,
        contexto: ContextoExecucao,
        *,
        mesa_id: str,
        expected_mesa_version: int,
        numero: str | None = None,
        comanda_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> Comanda:
        _autorizar(contexto, Permissao.MESA_ABRIR, "mesa")
        mesa = self.repositorio_salao.obter_mesa(
            contexto.tenant_id, contexto.unidade_id, mesa_id
        )
        if mesa is None or mesa.status != StatusMesa.LIVRE or not mesa.ativo:
            raise ErroGarcom("mesa_indisponivel")
        identificador = comanda_id or str(uuid4())
        numero_efetivo = numero or f"M{mesa.codigo}-{uuid4().hex[:6]}"
        resultado = self.salao.abrir_comanda(
            contexto,
            comanda_id=identificador,
            numero=numero_efetivo,
            mesa_id=mesa_id,
            expected_mesa_version=expected_mesa_version,
            idempotency_key=(
                idempotency_key
                or f"garcom:abrir:{mesa_id}:{expected_mesa_version}:{identificador}"
            ),
        )
        self.metricas.incrementar("garcom_comanda_aberta")
        return resultado

    def adicionar_participante(
        self,
        contexto: ContextoExecucao,
        *,
        comanda_id: str,
        apelido: str,
        expected_version: int,
        participante_id: str | None = None,
        idempotency_key: str | None = None,
    ):
        self._obter_comanda_na_alcada(contexto, comanda_id)
        identificador = participante_id or str(uuid4())
        resultado = self.salao.adicionar_participante(
            contexto,
            comanda_id=comanda_id,
            participante_id=identificador,
            apelido=apelido.strip(),
            expected_version=expected_version,
            idempotency_key=(
                idempotency_key
                or f"garcom:participante:{comanda_id}:{expected_version}:{identificador}"
            ),
        )
        self.metricas.incrementar("garcom_participante_adicionado")
        return resultado

    def vincular_pedido(
        self,
        contexto: ContextoExecucao,
        *,
        comanda_id: str,
        pedido_id: str,
        expected_version: int,
        participante_id: str | None = None,
        idempotency_key: str | None = None,
    ):
        self._obter_comanda_na_alcada(contexto, comanda_id)
        resultado = self.salao.vincular_pedido(
            contexto,
            comanda_id=comanda_id,
            pedido_id=pedido_id,
            participante_id=participante_id,
            expected_version=expected_version,
            idempotency_key=(
                idempotency_key
                or f"garcom:pedido:{comanda_id}:{pedido_id}:{expected_version}"
            ),
        )
        self.metricas.incrementar("garcom_pedido_vinculado")
        return resultado

    def solicitar_conta(
        self,
        contexto: ContextoExecucao,
        *,
        comanda_id: str,
        expected_version: int,
        idempotency_key: str | None = None,
    ) -> Comanda:
        self._obter_comanda_na_alcada(contexto, comanda_id)
        resultado = self.salao.solicitar_conta(
            contexto,
            comanda_id=comanda_id,
            expected_version=expected_version,
            idempotency_key=(
                idempotency_key or f"garcom:conta:{comanda_id}:{expected_version}"
            ),
        )
        self.metricas.incrementar("garcom_conta_solicitada")
        return resultado

    def retomar_consumo(
        self,
        contexto: ContextoExecucao,
        *,
        comanda_id: str,
        expected_version: int,
        idempotency_key: str | None = None,
    ) -> Comanda:
        self._obter_comanda_na_alcada(contexto, comanda_id)
        resultado = self.salao.retomar_consumo(
            contexto,
            comanda_id=comanda_id,
            expected_version=expected_version,
            idempotency_key=(
                idempotency_key or f"garcom:retomar:{comanda_id}:{expected_version}"
            ),
        )
        self.metricas.incrementar("garcom_consumo_retomado")
        return resultado
