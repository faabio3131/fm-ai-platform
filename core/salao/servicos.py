"""Casos de uso da operacao de salao V1."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import func, select, update

from core.pedidos.modelos_orm import PedidoORM
from core.seguranca import AutorizarAcao, ContextoExecucao, Papel, Permissao

from .adaptador_sqlalchemy import RepositorioSalaoSQLAlchemy
from .erros import ErroSalao
from .modelos import (
    Comanda,
    EventoSalao,
    Mesa,
    MetodoFechamento,
    PagamentoConfirmadoComanda,
    ParcelaFechamento,
    ParticipanteComanda,
    PedidoNaComanda,
    SnapshotSalao,
    StatusComanda,
    StatusMesa,
)
from .modelos_orm import ComandaORM, EventoSalaoORM, ParticipanteComandaORM

_ATIVOS = {
    StatusComanda.ABERTA,
    StatusComanda.EM_CONSUMO,
    StatusComanda.CONTA_SOLICITADA,
    StatusComanda.FECHAMENTO_EM_ANDAMENTO,
    StatusComanda.PARCIALMENTE_PAGA,
}


def _centavos(valor: Decimal) -> Decimal:
    if not isinstance(valor, Decimal):
        raise ErroSalao("valor_deve_ser_decimal")
    return valor.quantize(Decimal("0.01"))


def _autorizar(
    contexto: ContextoExecucao,
    permissao: Permissao,
    recurso: str,
    tenant_id: str,
    unidade_id: str,
) -> None:
    if contexto.identidade_sistema:
        return
    decisao = AutorizarAcao().executar(
        contexto=contexto,
        permissao=permissao,
        recurso=recurso,
        tenant_recurso=tenant_id,
        unidade_recurso=unidade_id,
    )
    if not decisao.autorizado:
        raise ErroSalao(decisao.codigo)


def _exigir_escopo(contexto: ContextoExecucao, tenant_id: str, unidade_id: str) -> None:
    if contexto.tenant_id != tenant_id or contexto.unidade_id != unidade_id:
        raise ErroSalao("recurso_indisponivel")


def _evento_existente(
    repositorio: RepositorioSalaoSQLAlchemy,
    contexto: ContextoExecucao,
    *,
    chave: str,
    tipo: str,
    agregado_id: str,
) -> bool:
    orm = repositorio.session.scalar(
        select(EventoSalaoORM).where(
            EventoSalaoORM.tenant_id == contexto.tenant_id,
            EventoSalaoORM.unidade_id == contexto.unidade_id,
            EventoSalaoORM.idempotency_key == chave,
        )
    )
    if orm is None:
        return False
    if orm.tipo != tipo or orm.agregado_id != agregado_id:
        raise ErroSalao("conflito_idempotencia")
    return True


def _registrar_evento(
    repositorio: RepositorioSalaoSQLAlchemy,
    contexto: ContextoExecucao,
    *,
    agregado_tipo: str,
    agregado_id: str,
    tipo: str,
    versao: int,
    chave: str,
    ocorrido_em: datetime,
    payload: tuple[tuple[str, str], ...] = (),
) -> None:
    repositorio.adicionar_evento(
        EventoSalao(
            evento_id=str(uuid4()),
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
            agregado_tipo=agregado_tipo,
            agregado_id=agregado_id,
            tipo=tipo,
            versao=versao,
            ator_id=contexto.usuario_id,
            correlation_id=contexto.correlation_id,
            idempotency_key=chave,
            ocorrido_em=ocorrido_em,
            payload=payload,
        )
    )


def _obter_comanda_ativa(
    repositorio: RepositorioSalaoSQLAlchemy,
    contexto: ContextoExecucao,
    comanda_id: str,
) -> Comanda:
    comanda = repositorio.obter_comanda(
        contexto.tenant_id, contexto.unidade_id, comanda_id
    )
    if comanda is None or comanda.status not in _ATIVOS:
        raise ErroSalao("comanda_indisponivel")
    return comanda


def _outras_comandas_na_mesa(
    repositorio: RepositorioSalaoSQLAlchemy,
    contexto: ContextoExecucao,
    mesa_id: str,
    *,
    exceto: str,
) -> int:
    return int(
        repositorio.session.scalar(
            select(func.count())
            .select_from(ComandaORM)
            .where(
                ComandaORM.tenant_id == contexto.tenant_id,
                ComandaORM.unidade_id == contexto.unidade_id,
                ComandaORM.mesa_id == mesa_id,
                ComandaORM.id != exceto,
                ComandaORM.status.in_([estado.value for estado in _ATIVOS]),
            )
        )
        or 0
    )


class ServicoSalao:
    def __init__(
        self,
        repositorio: RepositorioSalaoSQLAlchemy,
        *,
        agora: Callable[[], datetime],
    ) -> None:
        self.repositorio = repositorio
        self.agora = agora

    def listar_mapa(self, contexto: ContextoExecucao) -> SnapshotSalao:
        _autorizar(
            contexto,
            Permissao.PEDIDO_VISUALIZAR,
            "salao",
            contexto.tenant_id,
            contexto.unidade_id,
        )
        return SnapshotSalao(
            self.repositorio.listar_mesas(contexto.tenant_id, contexto.unidade_id),
            self.repositorio.listar_comandas_ativas(
                contexto.tenant_id, contexto.unidade_id
            ),
        )

    def cadastrar_mesa(
        self,
        contexto: ContextoExecucao,
        *,
        mesa_id: str,
        codigo: str,
        capacidade: int,
        idempotency_key: str,
        nome: str | None = None,
        posicao_x: Decimal | None = None,
        posicao_y: Decimal | None = None,
    ) -> Mesa:
        _autorizar(
            contexto,
            Permissao.CONFIGURACAO_ALTERAR,
            "mesa",
            contexto.tenant_id,
            contexto.unidade_id,
        )
        if _evento_existente(
            self.repositorio,
            contexto,
            chave=idempotency_key,
            tipo="mesa.criada",
            agregado_id=mesa_id,
        ):
            mesa = self.repositorio.obter_mesa(
                contexto.tenant_id, contexto.unidade_id, mesa_id
            )
            if mesa is None:
                raise ErroSalao("recurso_indisponivel")
            return mesa
        instante = self.agora()
        mesa = Mesa(
            mesa_id=mesa_id,
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
            codigo=codigo,
            nome=nome,
            capacidade=capacidade,
            status=StatusMesa.LIVRE,
            posicao_x=posicao_x,
            posicao_y=posicao_y,
            ativo=True,
            versao=1,
            criado_em=instante,
            atualizado_em=instante,
        )
        self.repositorio.criar_mesa(mesa)
        _registrar_evento(
            self.repositorio,
            contexto,
            agregado_tipo="mesa",
            agregado_id=mesa_id,
            tipo="mesa.criada",
            versao=1,
            chave=idempotency_key,
            ocorrido_em=instante,
        )
        return mesa

    def abrir_comanda(
        self,
        contexto: ContextoExecucao,
        *,
        comanda_id: str,
        numero: str,
        mesa_id: str,
        expected_mesa_version: int,
        idempotency_key: str,
    ) -> Comanda:
        _autorizar(
            contexto,
            Permissao.MESA_ABRIR,
            "mesa",
            contexto.tenant_id,
            contexto.unidade_id,
        )
        if _evento_existente(
            self.repositorio,
            contexto,
            chave=idempotency_key,
            tipo="comanda.aberta",
            agregado_id=comanda_id,
        ):
            existente = self.repositorio.obter_comanda(
                contexto.tenant_id, contexto.unidade_id, comanda_id
            )
            if existente is None:
                raise ErroSalao("recurso_indisponivel")
            return existente
        mesa = self.repositorio.obter_mesa(
            contexto.tenant_id, contexto.unidade_id, mesa_id
        )
        if mesa is None or not mesa.ativo or mesa.status != StatusMesa.LIVRE:
            raise ErroSalao("mesa_indisponivel")
        if mesa.versao != expected_mesa_version:
            raise ErroSalao("mesa_concorrente")
        instante = self.agora()
        comanda = Comanda(
            comanda_id=comanda_id,
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
            mesa_id=mesa.mesa_id,
            numero=numero,
            status=StatusComanda.ABERTA,
            responsavel_id=contexto.usuario_id,
            aberta_em=instante,
            total=Decimal("0.00"),
            saldo=Decimal("0.00"),
            versao=1,
        )
        self.repositorio.criar_comanda(comanda)
        self.repositorio.salvar_mesa(
            replace(
                mesa,
                status=StatusMesa.OCUPADA,
                versao=mesa.versao + 1,
                atualizado_em=instante,
            ),
            expected_mesa_version,
        )
        _registrar_evento(
            self.repositorio,
            contexto,
            agregado_tipo="comanda",
            agregado_id=comanda_id,
            tipo="comanda.aberta",
            versao=1,
            chave=idempotency_key,
            ocorrido_em=instante,
            payload=(("mesa_id", mesa_id),),
        )
        return comanda

    def adicionar_participante(
        self,
        contexto: ContextoExecucao,
        *,
        comanda_id: str,
        participante_id: str,
        expected_version: int,
        idempotency_key: str,
        cliente_id: str | None = None,
        apelido: str | None = None,
    ) -> ParticipanteComanda:
        comanda = _obter_comanda_ativa(self.repositorio, contexto, comanda_id)
        _autorizar(
            contexto,
            Permissao.COMANDA_ALTERAR,
            "comanda",
            comanda.tenant_id,
            comanda.unidade_id,
        )
        if _evento_existente(
            self.repositorio,
            contexto,
            chave=idempotency_key,
            tipo="comanda.participante_adicionado",
            agregado_id=comanda_id,
        ):
            itens = self.repositorio.listar_participantes(
                contexto.tenant_id, contexto.unidade_id, comanda_id
            )
            encontrado = next((p for p in itens if p.participante_id == participante_id), None)
            if encontrado is None:
                raise ErroSalao("recurso_indisponivel")
            return encontrado
        if comanda.versao != expected_version:
            raise ErroSalao("comanda_concorrente")
        participantes = self.repositorio.listar_participantes(
            contexto.tenant_id, contexto.unidade_id, comanda_id
        )
        participante = ParticipanteComanda(
            participante_id=participante_id,
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
            comanda_id=comanda_id,
            cliente_id=cliente_id,
            apelido=apelido,
            ordem=len(participantes) + 1,
        )
        self.repositorio.adicionar_participante(participante)
        atualizado = replace(comanda, versao=comanda.versao + 1)
        self.repositorio.salvar_comanda(atualizado, expected_version)
        _registrar_evento(
            self.repositorio,
            contexto,
            agregado_tipo="comanda",
            agregado_id=comanda_id,
            tipo="comanda.participante_adicionado",
            versao=atualizado.versao,
            chave=idempotency_key,
            ocorrido_em=self.agora(),
            payload=(("participante_id", participante_id),),
        )
        return participante

    def vincular_pedido(
        self,
        contexto: ContextoExecucao,
        *,
        comanda_id: str,
        pedido_id: str,
        expected_version: int,
        idempotency_key: str,
        participante_id: str | None = None,
    ) -> Comanda:
        comanda = _obter_comanda_ativa(self.repositorio, contexto, comanda_id)
        _autorizar(
            contexto,
            Permissao.COMANDA_ALTERAR,
            "comanda",
            comanda.tenant_id,
            comanda.unidade_id,
        )
        if _evento_existente(
            self.repositorio,
            contexto,
            chave=idempotency_key,
            tipo="comanda.pedido_vinculado",
            agregado_id=comanda_id,
        ):
            atual = self.repositorio.obter_comanda(
                contexto.tenant_id, contexto.unidade_id, comanda_id
            )
            if atual is None:
                raise ErroSalao("recurso_indisponivel")
            return atual
        if comanda.status not in {StatusComanda.ABERTA, StatusComanda.EM_CONSUMO}:
            raise ErroSalao("comanda_bloqueada_para_consumo")
        if comanda.versao != expected_version:
            raise ErroSalao("comanda_concorrente")
        pedido = self.repositorio.session.get(
            PedidoORM, (pedido_id, contexto.tenant_id, contexto.unidade_id)
        )
        if pedido is None or pedido.status == "cancelado":
            raise ErroSalao("pedido_indisponivel")
        valor = _centavos(Decimal(str(pedido.total)))
        if participante_id is not None:
            participantes = self.repositorio.listar_participantes(
                contexto.tenant_id, contexto.unidade_id, comanda_id
            )
            if participante_id not in {p.participante_id for p in participantes}:
                raise ErroSalao("participante_indisponivel")
        instante = self.agora()
        self.repositorio.vincular_pedido(
            PedidoNaComanda(
                vinculo_id=str(uuid4()),
                tenant_id=contexto.tenant_id,
                unidade_id=contexto.unidade_id,
                comanda_id=comanda_id,
                pedido_id=pedido_id,
                participante_id=participante_id,
                valor=valor,
                criado_em=instante,
            )
        )
        atualizado = replace(
            comanda,
            status=StatusComanda.EM_CONSUMO,
            total=_centavos(comanda.total + valor),
            saldo=_centavos(comanda.saldo + valor),
            versao=comanda.versao + 1,
        )
        self.repositorio.salvar_comanda(atualizado, expected_version)
        _registrar_evento(
            self.repositorio,
            contexto,
            agregado_tipo="comanda",
            agregado_id=comanda_id,
            tipo="comanda.pedido_vinculado",
            versao=atualizado.versao,
            chave=idempotency_key,
            ocorrido_em=instante,
            payload=(("pedido_id", pedido_id), ("valor", str(valor))),
        )
        return atualizado

    def transferir_comanda(
        self,
        contexto: ContextoExecucao,
        *,
        comanda_id: str,
        mesa_destino_id: str,
        expected_comanda_version: int,
        expected_destino_version: int,
        expected_origem_version: int,
        idempotency_key: str,
    ) -> Comanda:
        comanda = _obter_comanda_ativa(self.repositorio, contexto, comanda_id)
        _autorizar(
            contexto,
            Permissao.MESA_TRANSFERIR,
            "comanda",
            comanda.tenant_id,
            comanda.unidade_id,
        )
        if _evento_existente(
            self.repositorio,
            contexto,
            chave=idempotency_key,
            tipo="comanda.transferida",
            agregado_id=comanda_id,
        ):
            atual = self.repositorio.obter_comanda(
                contexto.tenant_id, contexto.unidade_id, comanda_id
            )
            if atual is None:
                raise ErroSalao("recurso_indisponivel")
            return atual
        if comanda.versao != expected_comanda_version or comanda.mesa_id is None:
            raise ErroSalao("comanda_concorrente")
        if comanda.mesa_id == mesa_destino_id:
            raise ErroSalao("mesa_destino_igual_origem")
        origem = self.repositorio.obter_mesa(
            contexto.tenant_id, contexto.unidade_id, comanda.mesa_id
        )
        destino = self.repositorio.obter_mesa(
            contexto.tenant_id, contexto.unidade_id, mesa_destino_id
        )
        if origem is None or destino is None or not destino.ativo:
            raise ErroSalao("mesa_indisponivel")
        if origem.versao != expected_origem_version or destino.versao != expected_destino_version:
            raise ErroSalao("mesa_concorrente")
        if destino.status != StatusMesa.LIVRE:
            raise ErroSalao("mesa_destino_ocupada")
        instante = self.agora()
        if _outras_comandas_na_mesa(
            self.repositorio, contexto, origem.mesa_id, exceto=comanda_id
        ) == 0:
            self.repositorio.salvar_mesa(
                replace(
                    origem,
                    status=StatusMesa.LIVRE,
                    versao=origem.versao + 1,
                    atualizado_em=instante,
                ),
                expected_origem_version,
            )
        self.repositorio.salvar_mesa(
            replace(
                destino,
                status=StatusMesa.OCUPADA,
                versao=destino.versao + 1,
                atualizado_em=instante,
            ),
            expected_destino_version,
        )
        atualizado = replace(
            comanda, mesa_id=destino.mesa_id, versao=comanda.versao + 1
        )
        self.repositorio.salvar_comanda(atualizado, expected_comanda_version)
        _registrar_evento(
            self.repositorio,
            contexto,
            agregado_tipo="comanda",
            agregado_id=comanda_id,
            tipo="comanda.transferida",
            versao=atualizado.versao,
            chave=idempotency_key,
            ocorrido_em=instante,
            payload=(("origem", origem.mesa_id), ("destino", destino.mesa_id)),
        )
        return atualizado

    def juntar_comandas(
        self,
        contexto: ContextoExecucao,
        *,
        origem_id: str,
        destino_id: str,
        expected_origem_version: int,
        expected_destino_version: int,
        idempotency_key: str,
    ) -> Comanda:
        if origem_id == destino_id:
            raise ErroSalao("comandas_iguais")
        origem = _obter_comanda_ativa(self.repositorio, contexto, origem_id)
        destino = _obter_comanda_ativa(self.repositorio, contexto, destino_id)
        _autorizar(
            contexto,
            Permissao.COMANDA_ALTERAR,
            "comanda",
            destino.tenant_id,
            destino.unidade_id,
        )
        if _evento_existente(
            self.repositorio,
            contexto,
            chave=idempotency_key,
            tipo="comanda.juntada",
            agregado_id=destino_id,
        ):
            atual = self.repositorio.obter_comanda(
                contexto.tenant_id, contexto.unidade_id, destino_id
            )
            if atual is None:
                raise ErroSalao("recurso_indisponivel")
            return atual
        if origem.versao != expected_origem_version or destino.versao != expected_destino_version:
            raise ErroSalao("comanda_concorrente")
        if origem.status not in {StatusComanda.ABERTA, StatusComanda.EM_CONSUMO} or destino.status not in {
            StatusComanda.ABERTA,
            StatusComanda.EM_CONSUMO,
        }:
            raise ErroSalao("comanda_bloqueada_para_reorganizacao")
        if self.repositorio.total_pago_confirmado(
            contexto.tenant_id, contexto.unidade_id, origem_id
        ) > 0 or self.repositorio.total_pago_confirmado(
            contexto.tenant_id, contexto.unidade_id, destino_id
        ) > 0:
            raise ErroSalao("comanda_com_pagamento_nao_pode_juntar")
        self.repositorio.mover_pedidos(
            contexto.tenant_id, contexto.unidade_id, origem_id, destino_id
        )
        participantes_destino = self.repositorio.listar_participantes(
            contexto.tenant_id, contexto.unidade_id, destino_id
        )
        deslocamento = len(participantes_destino)
        self.repositorio.session.execute(
            update(ParticipanteComandaORM)
            .where(
                ParticipanteComandaORM.tenant_id == contexto.tenant_id,
                ParticipanteComandaORM.unidade_id == contexto.unidade_id,
                ParticipanteComandaORM.comanda_id == origem_id,
            )
            .values(
                comanda_id=destino_id,
                ordem=ParticipanteComandaORM.ordem + deslocamento,
            )
        )
        instante = self.agora()
        novo_destino = replace(
            destino,
            status=(
                StatusComanda.EM_CONSUMO
                if origem.total > 0 or destino.total > 0
                else StatusComanda.ABERTA
            ),
            total=_centavos(destino.total + origem.total),
            saldo=_centavos(destino.saldo + origem.saldo),
            versao=destino.versao + 1,
        )
        novo_origem = replace(
            origem,
            status=StatusComanda.CANCELADA,
            saldo=Decimal("0.00"),
            mesa_id=None,
            versao=origem.versao + 1,
        )
        self.repositorio.salvar_comanda(novo_destino, expected_destino_version)
        self.repositorio.salvar_comanda(novo_origem, expected_origem_version)
        if origem.mesa_id and origem.mesa_id != destino.mesa_id:
            mesa_origem = self.repositorio.obter_mesa(
                contexto.tenant_id, contexto.unidade_id, origem.mesa_id
            )
            if mesa_origem and _outras_comandas_na_mesa(
                self.repositorio, contexto, origem.mesa_id, exceto=origem_id
            ) == 0:
                self.repositorio.salvar_mesa(
                    replace(
                        mesa_origem,
                        status=StatusMesa.LIVRE,
                        versao=mesa_origem.versao + 1,
                        atualizado_em=instante,
                    ),
                    mesa_origem.versao,
                )
        _registrar_evento(
            self.repositorio,
            contexto,
            agregado_tipo="comanda",
            agregado_id=destino_id,
            tipo="comanda.juntada",
            versao=novo_destino.versao,
            chave=idempotency_key,
            ocorrido_em=instante,
            payload=(("origem_id", origem_id),),
        )
        _registrar_evento(
            self.repositorio,
            contexto,
            agregado_tipo="comanda",
            agregado_id=origem_id,
            tipo="comanda.juntada_origem",
            versao=novo_origem.versao,
            chave=f"{idempotency_key}:origem",
            ocorrido_em=instante,
            payload=(("destino_id", destino_id),),
        )
        return novo_destino

    def separar_comanda(
        self,
        contexto: ContextoExecucao,
        *,
        origem_id: str,
        nova_comanda_id: str,
        novo_numero: str,
        pedido_ids: tuple[str, ...],
        expected_origem_version: int,
        idempotency_key: str,
        participante_ids: tuple[str, ...] = (),
    ) -> Comanda:
        origem = _obter_comanda_ativa(self.repositorio, contexto, origem_id)
        _autorizar(
            contexto,
            Permissao.COMANDA_ALTERAR,
            "comanda",
            origem.tenant_id,
            origem.unidade_id,
        )
        if _evento_existente(
            self.repositorio,
            contexto,
            chave=idempotency_key,
            tipo="comanda.separada",
            agregado_id=origem_id,
        ):
            existente = self.repositorio.obter_comanda(
                contexto.tenant_id, contexto.unidade_id, nova_comanda_id
            )
            if existente is None:
                raise ErroSalao("recurso_indisponivel")
            return existente
        if origem.versao != expected_origem_version:
            raise ErroSalao("comanda_concorrente")
        if origem.status not in {StatusComanda.ABERTA, StatusComanda.EM_CONSUMO}:
            raise ErroSalao("comanda_bloqueada_para_reorganizacao")
        if self.repositorio.total_pago_confirmado(
            contexto.tenant_id, contexto.unidade_id, origem_id
        ) > 0:
            raise ErroSalao("comanda_com_pagamento_nao_pode_separar")
        pedidos = self.repositorio.listar_pedidos(
            contexto.tenant_id, contexto.unidade_id, origem_id
        )
        selecionados = tuple(item for item in pedidos if item.pedido_id in set(pedido_ids))
        if not selecionados or len(selecionados) == len(pedidos):
            raise ErroSalao("separacao_deve_manter_pedidos_na_origem")
        if {item.pedido_id for item in selecionados} != set(pedido_ids):
            raise ErroSalao("pedido_indisponivel")
        movido = _centavos(sum((item.valor for item in selecionados), Decimal("0.00")))
        instante = self.agora()
        nova = Comanda(
            comanda_id=nova_comanda_id,
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
            mesa_id=origem.mesa_id,
            numero=novo_numero,
            status=StatusComanda.EM_CONSUMO,
            responsavel_id=contexto.usuario_id,
            aberta_em=instante,
            total=movido,
            saldo=movido,
            versao=1,
        )
        self.repositorio.criar_comanda(nova)
        quantidade = self.repositorio.mover_pedidos(
            contexto.tenant_id,
            contexto.unidade_id,
            origem_id,
            nova_comanda_id,
            pedido_ids,
        )
        if quantidade != len(pedido_ids):
            raise ErroSalao("pedido_indisponivel")
        if participante_ids:
            self.repositorio.session.execute(
                update(ParticipanteComandaORM)
                .where(
                    ParticipanteComandaORM.tenant_id == contexto.tenant_id,
                    ParticipanteComandaORM.unidade_id == contexto.unidade_id,
                    ParticipanteComandaORM.comanda_id == origem_id,
                    ParticipanteComandaORM.id.in_(participante_ids),
                )
                .values(comanda_id=nova_comanda_id)
            )
        nova_origem = replace(
            origem,
            total=_centavos(origem.total - movido),
            saldo=_centavos(origem.saldo - movido),
            versao=origem.versao + 1,
        )
        self.repositorio.salvar_comanda(nova_origem, expected_origem_version)
        _registrar_evento(
            self.repositorio,
            contexto,
            agregado_tipo="comanda",
            agregado_id=origem_id,
            tipo="comanda.separada",
            versao=nova_origem.versao,
            chave=idempotency_key,
            ocorrido_em=instante,
            payload=(("nova_comanda_id", nova_comanda_id), ("valor", str(movido))),
        )
        return nova

    def solicitar_conta(
        self,
        contexto: ContextoExecucao,
        *,
        comanda_id: str,
        expected_version: int,
        idempotency_key: str,
    ) -> Comanda:
        comanda = _obter_comanda_ativa(self.repositorio, contexto, comanda_id)
        _autorizar(
            contexto,
            Permissao.COMANDA_ALTERAR,
            "comanda",
            comanda.tenant_id,
            comanda.unidade_id,
        )
        if _evento_existente(
            self.repositorio,
            contexto,
            chave=idempotency_key,
            tipo="comanda.conta_solicitada",
            agregado_id=comanda_id,
        ):
            atual = self.repositorio.obter_comanda(
                contexto.tenant_id, contexto.unidade_id, comanda_id
            )
            if atual is None:
                raise ErroSalao("recurso_indisponivel")
            return atual
        if comanda.status not in {StatusComanda.ABERTA, StatusComanda.EM_CONSUMO}:
            raise ErroSalao("transicao_comanda_invalida")
        if comanda.versao != expected_version:
            raise ErroSalao("comanda_concorrente")
        atualizado = replace(
            comanda,
            status=StatusComanda.CONTA_SOLICITADA,
            versao=comanda.versao + 1,
        )
        self.repositorio.salvar_comanda(atualizado, expected_version)
        _registrar_evento(
            self.repositorio,
            contexto,
            agregado_tipo="comanda",
            agregado_id=comanda_id,
            tipo="comanda.conta_solicitada",
            versao=atualizado.versao,
            chave=idempotency_key,
            ocorrido_em=self.agora(),
        )
        return atualizado

    def definir_divisao_pagamento(
        self,
        contexto: ContextoExecucao,
        *,
        comanda_id: str,
        expected_version: int,
        idempotency_key: str,
        divisoes: tuple[tuple[MetodoFechamento, Decimal, str | None], ...],
    ) -> tuple[Comanda, tuple[ParcelaFechamento, ...]]:
        comanda = _obter_comanda_ativa(self.repositorio, contexto, comanda_id)
        _autorizar(
            contexto,
            Permissao.COMANDA_ALTERAR,
            "comanda",
            comanda.tenant_id,
            comanda.unidade_id,
        )
        if _evento_existente(
            self.repositorio,
            contexto,
            chave=idempotency_key,
            tipo="comanda.fechamento_iniciado",
            agregado_id=comanda_id,
        ):
            atual = self.repositorio.obter_comanda(
                contexto.tenant_id, contexto.unidade_id, comanda_id
            )
            if atual is None:
                raise ErroSalao("recurso_indisponivel")
            return atual, self.repositorio.listar_parcelas(
                contexto.tenant_id, contexto.unidade_id, comanda_id
            )
        if comanda.status != StatusComanda.CONTA_SOLICITADA:
            raise ErroSalao("transicao_comanda_invalida")
        if comanda.versao != expected_version or not divisoes:
            raise ErroSalao("comanda_concorrente" if comanda.versao != expected_version else "divisao_vazia")
        total = _centavos(sum((_centavos(valor) for _, valor, _ in divisoes), Decimal("0.00")))
        if total != comanda.saldo:
            raise ErroSalao("divisao_nao_fecha_saldo")
        if any(
            metodo == MetodoFechamento.RECEBIMENTO_POSTERIOR
            for metodo, _, _ in divisoes
        ) and not comanda.recebimento_posterior_autorizado:
            raise ErroSalao("recebimento_posterior_nao_autorizado")
        participantes = {
            p.participante_id
            for p in self.repositorio.listar_participantes(
                contexto.tenant_id, contexto.unidade_id, comanda_id
            )
        }
        parcelas: list[ParcelaFechamento] = []
        for ordem, (metodo, valor, participante_id) in enumerate(divisoes, start=1):
            if participante_id is not None and participante_id not in participantes:
                raise ErroSalao("participante_indisponivel")
            parcelas.append(
                ParcelaFechamento(
                    parcela_id=str(uuid4()),
                    comanda_id=comanda_id,
                    metodo=metodo,
                    valor=_centavos(valor),
                    ordem=ordem,
                    participante_id=participante_id,
                )
            )
        conjunto = tuple(parcelas)
        self.repositorio.substituir_parcelas(
            contexto.tenant_id, contexto.unidade_id, comanda_id, conjunto
        )
        atualizado = replace(
            comanda,
            status=StatusComanda.FECHAMENTO_EM_ANDAMENTO,
            versao=comanda.versao + 1,
        )
        self.repositorio.salvar_comanda(atualizado, expected_version)
        _registrar_evento(
            self.repositorio,
            contexto,
            agregado_tipo="comanda",
            agregado_id=comanda_id,
            tipo="comanda.fechamento_iniciado",
            versao=atualizado.versao,
            chave=idempotency_key,
            ocorrido_em=self.agora(),
            payload=(("parcelas", str(len(conjunto))), ("saldo", str(comanda.saldo))),
        )
        return atualizado, conjunto

    def autorizar_recebimento_posterior(
        self,
        contexto: ContextoExecucao,
        *,
        comanda_id: str,
        expected_version: int,
        idempotency_key: str,
    ) -> Comanda:
        comanda = _obter_comanda_ativa(self.repositorio, contexto, comanda_id)
        _autorizar(
            contexto,
            Permissao.COMANDA_FECHAR,
            "comanda",
            comanda.tenant_id,
            comanda.unidade_id,
        )
        if not ({Papel.ADMINISTRADOR, Papel.GERENTE} & contexto.papeis):
            raise ErroSalao("alçada_insuficiente")
        if _evento_existente(
            self.repositorio,
            contexto,
            chave=idempotency_key,
            tipo="comanda.recebimento_posterior_autorizado",
            agregado_id=comanda_id,
        ):
            atual = self.repositorio.obter_comanda(
                contexto.tenant_id, contexto.unidade_id, comanda_id
            )
            if atual is None:
                raise ErroSalao("recurso_indisponivel")
            return atual
        if comanda.versao != expected_version:
            raise ErroSalao("comanda_concorrente")
        atualizado = replace(
            comanda,
            recebimento_posterior_autorizado=True,
            versao=comanda.versao + 1,
        )
        self.repositorio.salvar_comanda(atualizado, expected_version)
        _registrar_evento(
            self.repositorio,
            contexto,
            agregado_tipo="comanda",
            agregado_id=comanda_id,
            tipo="comanda.recebimento_posterior_autorizado",
            versao=atualizado.versao,
            chave=idempotency_key,
            ocorrido_em=self.agora(),
        )
        return atualizado

    def registrar_pagamento_confirmado(
        self,
        contexto: ContextoExecucao,
        *,
        comanda_id: str,
        pagamento_id: str,
        metodo: MetodoFechamento,
        valor: Decimal,
        expected_version: int,
        idempotency_key: str,
    ) -> Comanda:
        comanda = _obter_comanda_ativa(self.repositorio, contexto, comanda_id)
        _autorizar(
            contexto,
            Permissao.PAGAMENTO_CONFIRMAR,
            "pagamento",
            comanda.tenant_id,
            comanda.unidade_id,
        )
        if _evento_existente(
            self.repositorio,
            contexto,
            chave=idempotency_key,
            tipo="comanda.pagamento_confirmado",
            agregado_id=comanda_id,
        ):
            atual = self.repositorio.obter_comanda(
                contexto.tenant_id, contexto.unidade_id, comanda_id
            )
            if atual is None:
                raise ErroSalao("recurso_indisponivel")
            return atual
        if comanda.status not in {
            StatusComanda.FECHAMENTO_EM_ANDAMENTO,
            StatusComanda.PARCIALMENTE_PAGA,
        }:
            raise ErroSalao("comanda_nao_esta_em_fechamento")
        if comanda.versao != expected_version:
            raise ErroSalao("comanda_concorrente")
        valor = _centavos(valor)
        if valor <= 0 or valor > comanda.saldo:
            raise ErroSalao("valor_pagamento_invalido")
        instante = self.agora()
        self.repositorio.registrar_pagamento_confirmado(
            PagamentoConfirmadoComanda(
                registro_id=str(uuid4()),
                tenant_id=contexto.tenant_id,
                unidade_id=contexto.unidade_id,
                comanda_id=comanda_id,
                pagamento_id=pagamento_id,
                metodo=metodo,
                valor=valor,
                idempotency_key=f"pagamento:{idempotency_key}",
                confirmado_em=instante,
            )
        )
        pago = self.repositorio.total_pago_confirmado(
            contexto.tenant_id, contexto.unidade_id, comanda_id
        )
        if pago > comanda.total:
            raise ErroSalao("pagamento_excede_comanda")
        saldo = _centavos(comanda.total - pago)
        atualizado = replace(
            comanda,
            saldo=saldo,
            status=(
                StatusComanda.PARCIALMENTE_PAGA
                if saldo > 0
                else StatusComanda.FECHAMENTO_EM_ANDAMENTO
            ),
            versao=comanda.versao + 1,
        )
        self.repositorio.salvar_comanda(atualizado, expected_version)
        _registrar_evento(
            self.repositorio,
            contexto,
            agregado_tipo="comanda",
            agregado_id=comanda_id,
            tipo="comanda.pagamento_confirmado",
            versao=atualizado.versao,
            chave=idempotency_key,
            ocorrido_em=instante,
            payload=(("pagamento_id", pagamento_id), ("valor", str(valor))),
        )
        return atualizado

    def fechar_comanda(
        self,
        contexto: ContextoExecucao,
        *,
        comanda_id: str,
        expected_version: int,
        idempotency_key: str,
        pedidos_resolvidos: bool,
    ) -> Comanda:
        comanda = _obter_comanda_ativa(self.repositorio, contexto, comanda_id)
        _autorizar(
            contexto,
            Permissao.COMANDA_FECHAR,
            "comanda",
            comanda.tenant_id,
            comanda.unidade_id,
        )
        if _evento_existente(
            self.repositorio,
            contexto,
            chave=idempotency_key,
            tipo="comanda.fechada",
            agregado_id=comanda_id,
        ):
            atual = self.repositorio.obter_comanda(
                contexto.tenant_id, contexto.unidade_id, comanda_id
            )
            if atual is None:
                raise ErroSalao("recurso_indisponivel")
            return atual
        if comanda.status not in {
            StatusComanda.FECHAMENTO_EM_ANDAMENTO,
            StatusComanda.PARCIALMENTE_PAGA,
        }:
            raise ErroSalao("transicao_comanda_invalida")
        if comanda.versao != expected_version:
            raise ErroSalao("comanda_concorrente")
        if not pedidos_resolvidos:
            raise ErroSalao("pedidos_nao_resolvidos")
        if comanda.saldo > 0 and not comanda.recebimento_posterior_autorizado:
            raise ErroSalao("saldo_nao_resolvido")
        instante = self.agora()
        fechado = replace(
            comanda,
            status=StatusComanda.FECHADA,
            fechada_em=instante,
            versao=comanda.versao + 1,
        )
        self.repositorio.salvar_comanda(fechado, expected_version)
        if comanda.mesa_id and _outras_comandas_na_mesa(
            self.repositorio, contexto, comanda.mesa_id, exceto=comanda_id
        ) == 0:
            mesa = self.repositorio.obter_mesa(
                contexto.tenant_id, contexto.unidade_id, comanda.mesa_id
            )
            if mesa is not None:
                self.repositorio.salvar_mesa(
                    replace(
                        mesa,
                        status=StatusMesa.LIVRE,
                        versao=mesa.versao + 1,
                        atualizado_em=instante,
                    ),
                    mesa.versao,
                )
        _registrar_evento(
            self.repositorio,
            contexto,
            agregado_tipo="comanda",
            agregado_id=comanda_id,
            tipo="comanda.fechada",
            versao=fechado.versao,
            chave=idempotency_key,
            ocorrido_em=instante,
            payload=(("saldo", str(fechado.saldo)),),
        )
        return fechado
