"""Composição do fechamento do Garçom Web sobre autoridades canônicas existentes."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.administracao import ConfiguracaoEstabelecimento
from core.garcom import ErroGarcom
from core.salao import (
    Comanda,
    ErroSalao,
    EventoSalao,
    RepositorioSalaoSQLAlchemy,
    StatusComanda,
)
from core.salao.modelos_orm import EventoSalaoORM
from core.seguranca import AutorizarAcao, ContextoExecucao, Papel, Permissao
from infra.administracao.repositorio_sqlalchemy import (
    RepositorioAdministracaoSQLAlchemy,
)
from infra.transacoes.uow import UnitOfWorkV1

SessionFactory = Callable[[], Session]
CENTAVOS = Decimal("0.01")


class ModoRecebimentoGarcom(StrEnum):
    NA_MESA = "na_mesa"
    NO_CAIXA = "no_caixa"
    HIBRIDO = "hibrido"


class DestinoRecebimento(StrEnum):
    MESA = "mesa"
    CAIXA = "caixa"


@dataclass(frozen=True)
class ConfiguracaoFechamentoGarcom:
    tenant_id: str
    unidade_id: str
    modo_recebimento: ModoRecebimentoGarcom
    taxa_servico_percentual: Decimal
    couvert_ativado: bool
    couvert_valor: Decimal
    versao: int


@dataclass(frozen=True)
class DemonstrativoFechamentoGarcom:
    comanda_id: str
    consumo: Decimal
    couvert_artistico: Decimal
    taxa_servico_percentual: Decimal
    taxa_servico_valor: Decimal
    taxa_servico_incluida: bool
    desconto: Decimal
    total: Decimal
    saldo: Decimal
    configuracao_versao: int
    consolidado: bool
    destino_recebimento: DestinoRecebimento | None = None


def _agora_utc() -> datetime:
    return datetime.now(timezone.utc)


def _dinheiro(value: Decimal | str | int | object) -> Decimal:
    return Decimal(str(value)).quantize(CENTAVOS, rounding=ROUND_HALF_UP)


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


def _parametros(config: ConfiguracaoEstabelecimento) -> dict[str, object]:
    return dict(config.parametros_operacionais)


def configuracao_fechamento(
    config: ConfiguracaoEstabelecimento,
) -> ConfiguracaoFechamentoGarcom:
    params = _parametros(config)
    modo_raw = str(
        params.get("recebimento_garcom", ModoRecebimentoGarcom.NO_CAIXA.value)
    )
    try:
        modo = ModoRecebimentoGarcom(modo_raw)
    except ValueError:
        modo = ModoRecebimentoGarcom.NO_CAIXA

    couvert_raw = params.get("couvert_artistico", {})
    couvert: Mapping[str, object] = (
        couvert_raw if isinstance(couvert_raw, Mapping) else {}
    )
    ativado = bool(couvert.get("ativado", False))
    try:
        valor = _dinheiro(couvert.get("valor", "0"))
    except Exception as exc:
        raise ErroSalao("couvert_configuracao_invalida") from exc
    if valor < 0:
        raise ErroSalao("couvert_configuracao_invalida")

    return ConfiguracaoFechamentoGarcom(
        tenant_id=config.tenant_id,
        unidade_id=config.unidade_id,
        modo_recebimento=modo,
        taxa_servico_percentual=_dinheiro(config.taxa_servico_percentual),
        couvert_ativado=ativado,
        couvert_valor=valor,
        versao=config.versao,
    )


def _parse_payload(payload: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in payload.split(";"):
        key, sep, value = item.partition("=")
        if sep and key:
            result[key] = value
    return result


class AplicacaoFechamentoGarcomV1:
    """Compõe fechamento sem substituir Salão, Pagamentos ou Administração."""

    SNAPSHOT_EVENT = "comanda.componentes_fechamento_consolidados"
    DESTINO_EVENT = "comanda.destino_recebimento_definido"

    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        agora: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._agora = agora or _agora_utc

    @staticmethod
    def _comanda_na_alcada(
        contexto: ContextoExecucao,
        repo: RepositorioSalaoSQLAlchemy,
        comanda_id: str,
    ) -> Comanda:
        _autorizar(contexto, Permissao.PEDIDO_VISUALIZAR, "interface_garcom")
        comanda = repo.obter_comanda(
            contexto.tenant_id,
            contexto.unidade_id,
            comanda_id,
        )
        if comanda is None:
            raise ErroGarcom("comanda_indisponivel")
        elevado = contexto.identidade_sistema or bool(
            contexto.papeis.intersection({Papel.ADMINISTRADOR, Papel.GERENTE})
        )
        if (
            not elevado
            and Papel.GARCOM in contexto.papeis
            and comanda.responsavel_id != contexto.usuario_id
        ):
            raise ErroGarcom("comanda_fora_alcada")
        return comanda

    @staticmethod
    def _config(
        contexto: ContextoExecucao,
        session: Session,
    ) -> ConfiguracaoEstabelecimento:
        config = RepositorioAdministracaoSQLAlchemy(session).obter_configuracao(
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
        )
        if config is None:
            raise ErroSalao("configuracao_estabelecimento_ausente")
        return config

    @staticmethod
    def _evento(
        session: Session,
        contexto: ContextoExecucao,
        comanda_id: str,
        tipo: str,
    ) -> EventoSalaoORM | None:
        return session.scalar(
            select(EventoSalaoORM)
            .where(
                EventoSalaoORM.tenant_id == contexto.tenant_id,
                EventoSalaoORM.unidade_id == contexto.unidade_id,
                EventoSalaoORM.agregado_id == comanda_id,
                EventoSalaoORM.tipo == tipo,
            )
            .order_by(EventoSalaoORM.ocorrido_em.desc())
            .limit(1)
        )

    def obter_configuracao(
        self,
        contexto: ContextoExecucao,
    ) -> ConfiguracaoFechamentoGarcom:
        with self._session_factory() as session:
            return configuracao_fechamento(self._config(contexto, session))

    def salvar_configuracao(
        self,
        contexto: ContextoExecucao,
        *,
        modo_recebimento: ModoRecebimentoGarcom,
        couvert_ativado: bool,
        couvert_valor: Decimal,
        expected_version: int,
    ) -> ConfiguracaoFechamentoGarcom:
        _autorizar(contexto, Permissao.CONFIGURACAO_ALTERAR, "configuracao")
        valor = _dinheiro(couvert_valor)
        if valor < 0:
            raise ErroSalao("couvert_valor_invalido")
        with UnitOfWorkV1(self._session_factory) as uow:
            if uow.session is None:
                raise RuntimeError("UnitOfWorkV1 sem Session ativa")
            repo = RepositorioAdministracaoSQLAlchemy(uow.session)
            atual = self._config(contexto, uow.session)
            if atual.versao != expected_version:
                raise ErroSalao("configuracao_concorrente")
            parametros = dict(atual.parametros_operacionais)
            parametros["recebimento_garcom"] = modo_recebimento.value
            parametros["couvert_artistico"] = {
                "ativado": bool(couvert_ativado),
                "valor": str(valor),
            }
            atualizado = repo.salvar_configuracao(
                ConfiguracaoEstabelecimento(
                    tenant_id=atual.tenant_id,
                    unidade_id=atual.unidade_id,
                    formas_pagamento=atual.formas_pagamento,
                    taxa_servico_percentual=atual.taxa_servico_percentual,
                    parametros_operacionais=parametros,
                    politica_financeira=atual.politica_financeira,
                    versao=atual.versao,
                ),
                versao_esperada=expected_version,
                agora=self._agora(),
            )
            uow.commit()
            return configuracao_fechamento(atualizado)

    def demonstrativo(
        self,
        contexto: ContextoExecucao,
        *,
        comanda_id: str,
        incluir_taxa_servico: bool = True,
    ) -> DemonstrativoFechamentoGarcom:
        with self._session_factory() as session:
            repo = RepositorioSalaoSQLAlchemy(session)
            comanda = self._comanda_na_alcada(contexto, repo, comanda_id)
            config = configuracao_fechamento(self._config(contexto, session))
            evento = self._evento(
                session,
                contexto,
                comanda_id,
                self.SNAPSHOT_EVENT,
            )
            destino_evento = self._evento(
                session,
                contexto,
                comanda_id,
                self.DESTINO_EVENT,
            )
            destino = None
            if destino_evento is not None:
                raw = _parse_payload(destino_evento.payload_resumo).get("destino")
                if raw:
                    destino = DestinoRecebimento(raw)

            if evento is not None:
                data = _parse_payload(evento.payload_resumo)
                return DemonstrativoFechamentoGarcom(
                    comanda_id=comanda_id,
                    consumo=_dinheiro(data["consumo"]),
                    couvert_artistico=_dinheiro(data["couvert"]),
                    taxa_servico_percentual=_dinheiro(data["taxa_percentual"]),
                    taxa_servico_valor=_dinheiro(data["taxa_valor"]),
                    taxa_servico_incluida=data["taxa_incluida"] == "1",
                    desconto=_dinheiro(data.get("desconto", "0")),
                    total=_dinheiro(data["total"]),
                    saldo=_dinheiro(comanda.saldo),
                    configuracao_versao=int(data["configuracao_versao"]),
                    consolidado=True,
                    destino_recebimento=destino,
                )

            consumo = _dinheiro(comanda.total)
            couvert = (
                config.couvert_valor
                if config.couvert_ativado
                else Decimal("0.00")
            )
            taxa = (
                _dinheiro(
                    consumo
                    * config.taxa_servico_percentual
                    / Decimal(100)
                )
                if incluir_taxa_servico
                else Decimal("0.00")
            )
            return DemonstrativoFechamentoGarcom(
                comanda_id=comanda_id,
                consumo=consumo,
                couvert_artistico=couvert,
                taxa_servico_percentual=config.taxa_servico_percentual,
                taxa_servico_valor=taxa,
                taxa_servico_incluida=incluir_taxa_servico and taxa > 0,
                desconto=Decimal("0.00"),
                total=_dinheiro(consumo + couvert + taxa),
                saldo=_dinheiro(comanda.saldo),
                configuracao_versao=config.versao,
                consolidado=False,
                destino_recebimento=destino,
            )

    def consolidar_componentes(
        self,
        contexto: ContextoExecucao,
        *,
        comanda_id: str,
        incluir_taxa_servico: bool,
        expected_version: int,
        idempotency_key: str,
    ) -> DemonstrativoFechamentoGarcom:
        with UnitOfWorkV1(self._session_factory) as uow:
            if uow.session is None:
                raise RuntimeError("UnitOfWorkV1 sem Session ativa")
            session = uow.session
            repo = RepositorioSalaoSQLAlchemy(session)
            comanda = self._comanda_na_alcada(contexto, repo, comanda_id)
            existente = self._evento(
                session,
                contexto,
                comanda_id,
                self.SNAPSHOT_EVENT,
            )
            if existente is not None:
                data = _parse_payload(existente.payload_resumo)
                return DemonstrativoFechamentoGarcom(
                    comanda_id=comanda_id,
                    consumo=_dinheiro(data["consumo"]),
                    couvert_artistico=_dinheiro(data["couvert"]),
                    taxa_servico_percentual=_dinheiro(data["taxa_percentual"]),
                    taxa_servico_valor=_dinheiro(data["taxa_valor"]),
                    taxa_servico_incluida=data["taxa_incluida"] == "1",
                    desconto=_dinheiro(data.get("desconto", "0")),
                    total=_dinheiro(data["total"]),
                    saldo=_dinheiro(comanda.saldo),
                    configuracao_versao=int(data["configuracao_versao"]),
                    consolidado=True,
                )
            if comanda.status is not StatusComanda.CONTA_SOLICITADA:
                raise ErroSalao("transicao_comanda_invalida")
            if comanda.versao != expected_version:
                raise ErroSalao("comanda_concorrente")
            if comanda.saldo != comanda.total:
                raise ErroSalao("fechamento_componentes_apos_pagamento")
            _autorizar(contexto, Permissao.COMANDA_ALTERAR, "comanda")

            config = configuracao_fechamento(self._config(contexto, session))
            consumo = _dinheiro(comanda.total)
            couvert = (
                config.couvert_valor
                if config.couvert_ativado
                else Decimal("0.00")
            )
            taxa = (
                _dinheiro(
                    consumo
                    * config.taxa_servico_percentual
                    / Decimal(100)
                )
                if incluir_taxa_servico
                else Decimal("0.00")
            )
            total = _dinheiro(consumo + couvert + taxa)
            atualizado = replace(
                comanda,
                total=total,
                saldo=total,
                versao=comanda.versao + 1,
            )
            repo.salvar_comanda(atualizado, expected_version)
            repo.adicionar_evento(
                EventoSalao(
                    evento_id=str(uuid4()),
                    tenant_id=contexto.tenant_id,
                    unidade_id=contexto.unidade_id,
                    agregado_tipo="comanda",
                    agregado_id=comanda_id,
                    tipo=self.SNAPSHOT_EVENT,
                    versao=atualizado.versao,
                    ator_id=contexto.usuario_id,
                    correlation_id=contexto.correlation_id,
                    idempotency_key=idempotency_key,
                    ocorrido_em=self._agora(),
                    payload=(
                        ("consumo", str(consumo)),
                        ("couvert", str(couvert)),
                        (
                            "taxa_percentual",
                            str(config.taxa_servico_percentual),
                        ),
                        ("taxa_valor", str(taxa)),
                        (
                            "taxa_incluida",
                            "1"
                            if incluir_taxa_servico and taxa > 0
                            else "0",
                        ),
                        ("desconto", "0.00"),
                        ("total", str(total)),
                        ("configuracao_versao", str(config.versao)),
                    ),
                )
            )
            uow.commit()

        return self.demonstrativo(
            contexto,
            comanda_id=comanda_id,
            incluir_taxa_servico=incluir_taxa_servico,
        )

    def definir_destino(
        self,
        contexto: ContextoExecucao,
        *,
        comanda_id: str,
        destino: DestinoRecebimento,
        expected_version: int,
        idempotency_key: str,
    ) -> DestinoRecebimento:
        with UnitOfWorkV1(self._session_factory) as uow:
            if uow.session is None:
                raise RuntimeError("UnitOfWorkV1 sem Session ativa")
            session = uow.session
            repo = RepositorioSalaoSQLAlchemy(session)
            comanda = self._comanda_na_alcada(contexto, repo, comanda_id)
            if comanda.status is not StatusComanda.CONTA_SOLICITADA:
                raise ErroSalao("transicao_comanda_invalida")
            if comanda.versao != expected_version:
                raise ErroSalao("comanda_concorrente")
            _autorizar(contexto, Permissao.COMANDA_ALTERAR, "comanda")

            existente = self._evento(
                session,
                contexto,
                comanda_id,
                self.DESTINO_EVENT,
            )
            if existente is not None:
                atual = _parse_payload(existente.payload_resumo).get("destino")
                if atual == destino.value:
                    return destino
                raise ErroSalao("destino_recebimento_ja_definido")

            config = configuracao_fechamento(self._config(contexto, session))
            permitidos = {
                ModoRecebimentoGarcom.NA_MESA: {DestinoRecebimento.MESA},
                ModoRecebimentoGarcom.NO_CAIXA: {DestinoRecebimento.CAIXA},
                ModoRecebimentoGarcom.HIBRIDO: {
                    DestinoRecebimento.MESA,
                    DestinoRecebimento.CAIXA,
                },
            }[config.modo_recebimento]
            if destino not in permitidos:
                raise ErroSalao("destino_recebimento_nao_permitido")

            repo.adicionar_evento(
                EventoSalao(
                    evento_id=str(uuid4()),
                    tenant_id=contexto.tenant_id,
                    unidade_id=contexto.unidade_id,
                    agregado_tipo="comanda",
                    agregado_id=comanda_id,
                    tipo=self.DESTINO_EVENT,
                    versao=comanda.versao,
                    ator_id=contexto.usuario_id,
                    correlation_id=contexto.correlation_id,
                    idempotency_key=idempotency_key,
                    ocorrido_em=self._agora(),
                    payload=(
                        ("destino", destino.value),
                        ("modo", config.modo_recebimento.value),
                    ),
                )
            )
            uow.commit()
            return destino
