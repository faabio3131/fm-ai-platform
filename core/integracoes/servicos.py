"""Casos de uso de configuração e prontidão de integrações externas."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime, timezone
from uuid import uuid4

from core.seguranca.auditoria import EventoAuditoria, RepositorioAuditoria
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.erros import PermissaoInsuficiente
from core.seguranca.permissoes import Papel, Permissao

from .catalogo import CATALOGO_V1, CatalogoServicosExternos
from .modelos import (
    AmbienteIntegracao,
    ConfiguracaoServicoExterno,
    ErroConfiguracaoServico,
    EstadoProntidaoServico,
    ProntidaoServicoExterno,
    ValorParametro,
    normalizar_credenciais,
    normalizar_parametros,
)
from .repositorios import PortaProntidaoCredenciais, RepositorioConfiguracoesExternas


class ServicoConfiguracoesExternas:
    def __init__(
        self,
        *,
        repositorio: RepositorioConfiguracoesExternas,
        prontidao_credenciais: PortaProntidaoCredenciais,
        auditoria: RepositorioAuditoria,
        catalogo: CatalogoServicosExternos = CATALOGO_V1,
    ) -> None:
        self._repositorio = repositorio
        self._prontidao_credenciais = prontidao_credenciais
        self._auditoria = auditoria
        self._catalogo = catalogo

    @staticmethod
    def _autorizar(contexto: ContextoExecucao) -> None:
        if Permissao.INTEGRACAO_GERENCIAR not in contexto.permissoes:
            raise PermissaoInsuficiente("integracao.gerenciar obrigatoria")

    def configurar(
        self,
        *,
        contexto: ContextoExecucao,
        configuracao_id: str,
        servico: str,
        provedor: str,
        conta_externa: str,
        ambiente: AmbienteIntegracao,
        parametros_publicos: Mapping[str, ValorParametro],
        finalidades_credenciais: Mapping[str, str],
        habilitada: bool,
        versao_esperada: int,
    ) -> ConfiguracaoServicoExterno:
        self._autorizar(contexto)
        especificacao = self._catalogo.obter(servico, provedor)
        existente = self._repositorio.obter(
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
            configuracao_id=configuracao_id,
        )
        if existente is not None and (
            existente.servico != especificacao.servico
            or existente.provedor != especificacao.provedor
        ):
            raise ErroConfiguracaoServico("identidade_configuracao_inalteravel")

        parametros_normalizados = normalizar_parametros(parametros_publicos)
        credenciais_normalizadas = normalizar_credenciais(finalidades_credenciais)
        preserva_homologacao = bool(
            existente
            and existente.conta_externa == conta_externa.strip()
            and existente.ambiente is ambiente
            and existente.parametros_publicos == parametros_normalizados
            and existente.finalidades_credenciais == credenciais_normalizadas
        )
        agora = datetime.now(timezone.utc)
        configuracao = ConfiguracaoServicoExterno(
            configuracao_id=configuracao_id.strip(),
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
            servico=especificacao.servico,
            provedor=especificacao.provedor,
            conta_externa=conta_externa.strip(),
            ambiente=ambiente,
            parametros_publicos=parametros_normalizados,
            finalidades_credenciais=credenciais_normalizadas,
            habilitada=habilitada,
            homologada=bool(existente and existente.homologada and preserva_homologacao),
            evidencia_homologacao_ref=(
                existente.evidencia_homologacao_ref
                if existente and preserva_homologacao
                else None
            ),
            versao=versao_esperada + 1,
            atualizado_por=contexto.usuario_id,
            correlation_id=contexto.correlation_id,
            atualizado_em=agora,
        )
        salvo = self._repositorio.salvar(
            configuracao, versao_esperada=versao_esperada
        )
        self._auditar(
            contexto=contexto,
            configuracao=salvo,
            acao="integracao.configurar",
            motivo="configuracao externa versionada",
        )
        return salvo

    def registrar_homologacao(
        self,
        *,
        contexto: ContextoExecucao,
        configuracao_id: str,
        evidencia_ref: str,
        versao_esperada: int,
    ) -> ConfiguracaoServicoExterno:
        self._autorizar(contexto)
        if Papel.ADMINISTRADOR not in contexto.papeis:
            raise PermissaoInsuficiente("administrador obrigatorio para homologacao")
        atual = self.obter(contexto=contexto, configuracao_id=configuracao_id)
        if not evidencia_ref.strip():
            raise ErroConfiguracaoServico("homologacao_sem_evidencia")
        status = self.avaliar(contexto=contexto, configuracao_id=configuracao_id)
        if status.faltam_parametros or status.faltam_finalidades or status.faltam_credenciais:
            raise ErroConfiguracaoServico("homologacao_com_configuracao_incompleta")

        homologada = replace(
            atual,
            homologada=True,
            evidencia_homologacao_ref=evidencia_ref.strip(),
            versao=versao_esperada + 1,
            atualizado_por=contexto.usuario_id,
            correlation_id=contexto.correlation_id,
            atualizado_em=datetime.now(timezone.utc),
        )
        salvo = self._repositorio.salvar(
            homologada, versao_esperada=versao_esperada
        )
        self._auditar(
            contexto=contexto,
            configuracao=salvo,
            acao="integracao.homologar",
            motivo="homologacao registrada com evidencia",
        )
        return salvo

    def obter(
        self, *, contexto: ContextoExecucao, configuracao_id: str
    ) -> ConfiguracaoServicoExterno:
        self._autorizar(contexto)
        configuracao = self._repositorio.obter(
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
            configuracao_id=configuracao_id,
        )
        if configuracao is None:
            raise ErroConfiguracaoServico("configuracao_indisponivel")
        return configuracao

    def listar(
        self, *, contexto: ContextoExecucao
    ) -> tuple[ConfiguracaoServicoExterno, ...]:
        self._autorizar(contexto)
        return self._repositorio.listar(
            tenant_id=contexto.tenant_id, unidade_id=contexto.unidade_id
        )

    def avaliar(
        self, *, contexto: ContextoExecucao, configuracao_id: str
    ) -> ProntidaoServicoExterno:
        configuracao = self.obter(
            contexto=contexto, configuracao_id=configuracao_id
        )
        especificacao = self._catalogo.obter(
            configuracao.servico, configuracao.provedor
        )
        parametros = configuracao.parametros
        credenciais = configuracao.credenciais
        faltam_parametros = tuple(
            sorted(
                nome
                for nome in especificacao.parametros_obrigatorios
                if nome not in parametros or parametros[nome] in (None, "")
            )
        )
        faltam_finalidades = tuple(
            sorted(especificacao.credenciais_obrigatorias - credenciais.keys())
        )
        finalidades = tuple(
            credenciais[papel]
            for papel in sorted(especificacao.credenciais_obrigatorias)
            if papel in credenciais
        )
        faltam_credenciais = self._prontidao_credenciais.faltantes(
            tenant_id=configuracao.tenant_id,
            unidade_id=configuracao.unidade_id,
            provedor=configuracao.provedor,
            finalidades=finalidades,
        )
        if not configuracao.habilitada:
            estado = EstadoProntidaoServico.DESATIVADO
        elif faltam_parametros or faltam_finalidades or faltam_credenciais:
            estado = EstadoProntidaoServico.BLOQUEADO
        elif not configuracao.homologada:
            estado = EstadoProntidaoServico.CONFIGURADO
        else:
            estado = EstadoProntidaoServico.PRONTO
        return ProntidaoServicoExterno(
            estado=estado,
            faltam_parametros=faltam_parametros,
            faltam_finalidades=faltam_finalidades,
            faltam_credenciais=faltam_credenciais,
        )

    def _auditar(
        self,
        *,
        contexto: ContextoExecucao,
        configuracao: ConfiguracaoServicoExterno,
        acao: str,
        motivo: str,
    ) -> None:
        papel = (
            min(contexto.papeis, key=lambda item: item.value)
            if contexto.papeis
            else None
        )
        self._auditoria.adicionar(
            EventoAuditoria(
                audit_id=f"audit-{uuid4().hex}",
                tenant_id=contexto.tenant_id,
                unidade_id=contexto.unidade_id,
                usuario_id=contexto.usuario_id,
                papel_efetivo=papel,
                acao=acao,
                recurso_tipo="configuracao_servico_externo",
                recurso_id=configuracao.configuracao_id,
                resultado="permitido",
                motivo=motivo,
                correlation_id=contexto.correlation_id,
                timestamp=datetime.now(timezone.utc),
                origem=contexto.origem,
                politica="integracoes.configuracao.v1",
                causation_id=contexto.causation_id,
                depois_resumido=(
                    ("ambiente", configuracao.ambiente.value),
                    ("habilitada", configuracao.habilitada),
                    ("homologada", configuracao.homologada),
                    ("provedor", configuracao.provedor),
                    ("servico", configuracao.servico),
                    ("versao", configuracao.versao),
                ),
            )
        )
