"""Aplicação do Painel Proprietário / Administrador V1.

Composição de autoridades existentes: identidade/RBAC, Pedido, Pagamento, Estoque,
Entrega, integrações e auditoria. Não contém segredos nem cria autoridades paralelas.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import MetaData, Table, func, select
from sqlalchemy.orm import Session

from core.administracao import (
    ConfiguracaoEstabelecimento,
    EmpresaAdministrativa,
    UnidadeAdministrativa,
)
from core.entrega.modelos_orm import EntregaORM
from core.estoque.modelos_orm import SaldoEstoqueORM
from core.integracoes.modelos import EstadoProntidaoServico
from core.pagamentos.modelos_orm import PagamentoORM, VendaFinanceiraORM
from core.pedidos.modelos_orm import ItemPedidoORM, PedidoORM
from core.seguranca.auditoria import EventoAuditoria
from core.seguranca.autenticacao import IdentidadeUsuario
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Papel, Permissao
from infra.administracao.repositorio_sqlalchemy import (
    RepositorioAdministracaoSQLAlchemy,
)
from infra.integracoes.repositorio_sqlalchemy import (
    RepositorioConfiguracoesExternasSQLAlchemy,
)
from infra.legacy_product_scope import resolver_loja_id_legada
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy
from infra.seguranca.auditoria_sqlalchemy import RepositorioAuditoriaSQLAlchemy
from infra.seguranca.modelos_orm import UsuarioSegurancaORM

SessionFactory = Callable[[], Session]


@dataclass(frozen=True, kw_only=True)
class ResumoFinanceiroAdmin:
    vendas_reconhecidas: Decimal
    quantidade_vendas: int
    ticket_medio: Decimal
    pagamentos_pagos: Decimal
    pagamentos_pendentes: Decimal
    pagamentos_estornados: Decimal
    recebido_dinheiro: Decimal
    cmv_estimado_atual: Decimal | None
    margem_estimada_atual: Decimal | None
    cobertura_cmv_itens_pct: Decimal


@dataclass(frozen=True, kw_only=True)
class ResumoOperacionalAdmin:
    pedidos: int
    estoque_fisico_total: Decimal
    estoque_reservado_total: Decimal
    entregas_por_status: tuple[tuple[str, int], ...]
    integracoes_configuradas: int
    integracoes_homologadas: int
    usuarios_ativos: int


@dataclass(frozen=True, kw_only=True)
class PainelExecutivoAdmin:
    tenant_id: str
    unidades: tuple[str, ...]
    financeiro: ResumoFinanceiroAdmin
    operacional: ResumoOperacionalAdmin


@dataclass(frozen=True, kw_only=True)
class UsuarioAdminResumo:
    usuario_id: str
    email: str
    ativo: bool
    papeis: tuple[str, ...]
    unidades: tuple[str, ...]
    unidade_padrao: str
    acesso_admin_sensivel: bool
    permissoes_efetivas: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class IntegracaoAdminResumo:
    unidade_id: str
    configuracao_id: str
    servico: str
    provedor: str
    estado: str
    habilitada: bool
    homologada: bool


def _papel_efetivo(contexto: ContextoExecucao) -> Papel | None:
    if Papel.ADMINISTRADOR in contexto.papeis:
        return Papel.ADMINISTRADOR
    if Papel.GERENTE in contexto.papeis:
        return Papel.GERENTE
    return next(iter(contexto.papeis), None)


def _exigir(contexto: ContextoExecucao, permissao: Permissao) -> None:
    if contexto.identidade_sistema:
        raise PermissionError("administracao_requer_identidade_humana")
    if Permissao.ADMIN_ACESSAR not in contexto.permissoes:
        raise PermissionError("administracao_sem_acesso")
    if permissao not in contexto.permissoes:
        raise PermissionError(f"administracao_sem_permissao:{permissao.value}")


def _decimal(valor: object | None) -> Decimal:
    if valor is None:
        return Decimal("0")
    return Decimal(valor)


def _administrador_tenant(contexto: ContextoExecucao) -> bool:
    return Papel.ADMINISTRADOR in contexto.papeis


class AplicacaoAdministracaoProprietarioV1:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def _unidades_administraveis(
        self,
        *,
        session: Session,
        contexto: ContextoExecucao,
        incluir_inativas: bool = True,
    ) -> tuple[UnidadeAdministrativa, ...]:
        todas = RepositorioAdministracaoSQLAlchemy(session).listar_unidades(
            tenant_id=contexto.tenant_id,
            incluir_inativas=incluir_inativas,
        )
        if _administrador_tenant(contexto):
            return todas
        permitidas = set(contexto.unidades_permitidas)
        return tuple(
            unidade for unidade in todas if unidade.unidade_id in permitidas
        )

    def _exigir_unidade_administravel(
        self,
        *,
        session: Session,
        contexto: ContextoExecucao,
        unidade_id: str,
    ) -> UnidadeAdministrativa:
        unidades = self._unidades_administraveis(
            session=session,
            contexto=contexto,
            incluir_inativas=True,
        )
        for unidade in unidades:
            if unidade.unidade_id == unidade_id:
                return unidade
        raise PermissionError("unidade_fora_do_escopo_administrativo")

    def _auditar(
        self,
        *,
        session: Session,
        contexto: ContextoExecucao,
        acao: str,
        recurso_tipo: str,
        recurso_id: str | None,
        antes: dict[str, object] | None = None,
        depois: dict[str, object] | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        RepositorioAuditoriaSQLAlchemy(session).adicionar(
            EventoAuditoria(
                audit_id=str(uuid4()),
                tenant_id=contexto.tenant_id,
                unidade_id=contexto.unidade_id,
                usuario_id=contexto.usuario_id,
                papel_efetivo=_papel_efetivo(contexto),
                acao=acao,
                recurso_tipo=recurso_tipo,
                recurso_id=recurso_id,
                resultado="permitido",
                motivo="acao administrativa autorizada",
                correlation_id=contexto.correlation_id,
                timestamp=datetime.now(timezone.utc),
                origem=contexto.origem,
                politica="administracao_proprietario_v1",
                causation_id=contexto.causation_id,
                antes_resumido=tuple(sorted((antes or {}).items())),
                depois_resumido=tuple(sorted((depois or {}).items())),
                metadata=tuple(sorted((metadata or {}).items())),
            )
        )

    def registrar_acesso(self, *, contexto: ContextoExecucao) -> None:
        _exigir(contexto, Permissao.ADMIN_ACESSAR)
        with self._session_factory() as session:
            self._auditar(
                session=session,
                contexto=contexto,
                acao="administracao.acessar",
                recurso_tipo="painel_admin",
                recurso_id=contexto.tenant_id,
                metadata={"unidade_ativa": contexto.unidade_id},
            )
            session.commit()

    def obter_empresa(
        self, *, contexto: ContextoExecucao
    ) -> EmpresaAdministrativa:
        _exigir(contexto, Permissao.CONFIGURACAO_ALTERAR)
        with self._session_factory() as session:
            empresa = RepositorioAdministracaoSQLAlchemy(session).obter_empresa(
                tenant_id=contexto.tenant_id
            )
            if empresa is None:
                raise LookupError("empresa_admin_nao_inicializada")
            return empresa

    def listar_unidades(
        self,
        *,
        contexto: ContextoExecucao,
        incluir_inativas: bool = True,
    ) -> tuple[UnidadeAdministrativa, ...]:
        _exigir(contexto, Permissao.CONFIGURACAO_ALTERAR)
        with self._session_factory() as session:
            return self._unidades_administraveis(
                session=session,
                contexto=contexto,
                incluir_inativas=incluir_inativas,
            )

    def obter_configuracao(
        self,
        *,
        contexto: ContextoExecucao,
        unidade_id: str,
    ) -> ConfiguracaoEstabelecimento:
        _exigir(contexto, Permissao.CONFIGURACAO_ALTERAR)
        with self._session_factory() as session:
            self._exigir_unidade_administravel(
                session=session,
                contexto=contexto,
                unidade_id=unidade_id,
            )
            config = RepositorioAdministracaoSQLAlchemy(session).obter_configuracao(
                tenant_id=contexto.tenant_id,
                unidade_id=unidade_id,
            )
            if config is None:
                raise LookupError("configuracao_estabelecimento_ausente")
            return config

    def atualizar_empresa(
        self,
        *,
        contexto: ContextoExecucao,
        empresa: EmpresaAdministrativa,
        versao_esperada: int,
    ) -> EmpresaAdministrativa:
        _exigir(contexto, Permissao.CONFIGURACAO_ALTERAR)
        if empresa.tenant_id != contexto.tenant_id:
            raise PermissionError("tenant_admin_divergente")
        with self._session_factory() as session:
            repo = RepositorioAdministracaoSQLAlchemy(session)
            anterior = repo.obter_empresa(tenant_id=contexto.tenant_id)
            if anterior is None:
                raise LookupError("empresa_admin_nao_inicializada")
            atual = repo.atualizar_empresa(
                empresa,
                versao_esperada=versao_esperada,
            )
            self._auditar(
                session=session,
                contexto=contexto,
                acao="administracao.empresa_atualizar",
                recurso_tipo="empresa",
                recurso_id=contexto.tenant_id,
                antes={
                    "nome": anterior.nome_exibicao,
                    "ativa": anterior.ativa,
                    "versao": anterior.versao,
                },
                depois={
                    "nome": atual.nome_exibicao,
                    "ativa": atual.ativa,
                    "versao": atual.versao,
                },
            )
            session.commit()
            return atual

    def criar_unidade(
        self,
        *,
        contexto: ContextoExecucao,
        unidade: UnidadeAdministrativa,
    ) -> UnidadeAdministrativa:
        _exigir(contexto, Permissao.CONFIGURACAO_ALTERAR)
        if unidade.tenant_id != contexto.tenant_id:
            raise PermissionError("tenant_admin_divergente")
        with self._session_factory() as session:
            repo = RepositorioAdministracaoSQLAlchemy(session)
            criada = repo.criar_unidade(unidade)

            # O criador administrativo recebe explicitamente membership na nova
            # unidade para que o novo escopo não exista fora da autoridade de RBAC.
            identidades = RepositorioIdentidadesSQLAlchemy(session)
            criador = identidades.obter_por_id(usuario_id=contexto.usuario_id)
            if criador is not None:
                identidades.definir_unidades(
                    usuario_id=criador.usuario_id,
                    unidades_permitidas={
                        *criador.unidades_permitidas,
                        criada.unidade_id,
                    },
                    unidade_padrao_id=criador.unidade_id,
                )

            self._auditar(
                session=session,
                contexto=contexto,
                acao="administracao.unidade_criar",
                recurso_tipo="unidade",
                recurso_id=criada.unidade_id,
                depois={
                    "codigo": criada.codigo,
                    "tipo": criada.tipo,
                    "ativa": criada.ativa,
                    "versao": criada.versao,
                },
            )
            session.commit()
            return criada

    def atualizar_unidade(
        self,
        *,
        contexto: ContextoExecucao,
        unidade: UnidadeAdministrativa,
        versao_esperada: int,
    ) -> UnidadeAdministrativa:
        _exigir(contexto, Permissao.CONFIGURACAO_ALTERAR)
        if unidade.tenant_id != contexto.tenant_id:
            raise PermissionError("tenant_admin_divergente")
        with self._session_factory() as session:
            self._exigir_unidade_administravel(
                session=session,
                contexto=contexto,
                unidade_id=unidade.unidade_id,
            )
            repo = RepositorioAdministracaoSQLAlchemy(session)
            anterior = repo.obter_unidade(
                tenant_id=contexto.tenant_id,
                unidade_id=unidade.unidade_id,
            )
            if anterior is None:
                raise LookupError("unidade_admin_ausente")
            atual = repo.atualizar_unidade(
                unidade,
                versao_esperada=versao_esperada,
            )
            self._auditar(
                session=session,
                contexto=contexto,
                acao="administracao.unidade_atualizar",
                recurso_tipo="unidade",
                recurso_id=unidade.unidade_id,
                antes={
                    "codigo": anterior.codigo,
                    "tipo": anterior.tipo,
                    "ativa": anterior.ativa,
                    "versao": anterior.versao,
                },
                depois={
                    "codigo": atual.codigo,
                    "tipo": atual.tipo,
                    "ativa": atual.ativa,
                    "versao": atual.versao,
                },
            )
            session.commit()
            return atual

    def salvar_configuracao(
        self,
        *,
        contexto: ContextoExecucao,
        configuracao: ConfiguracaoEstabelecimento,
        versao_esperada: int,
    ) -> ConfiguracaoEstabelecimento:
        _exigir(contexto, Permissao.CONFIGURACAO_ALTERAR)
        if configuracao.tenant_id != contexto.tenant_id:
            raise PermissionError("tenant_admin_divergente")
        with self._session_factory() as session:
            unidade = self._exigir_unidade_administravel(
                session=session,
                contexto=contexto,
                unidade_id=configuracao.unidade_id,
            )
            repo = RepositorioAdministracaoSQLAlchemy(session)
            if unidade is None:
                raise LookupError("unidade_admin_ausente")
            anterior = repo.obter_configuracao(
                tenant_id=contexto.tenant_id,
                unidade_id=configuracao.unidade_id,
            )
            if anterior is None:
                raise LookupError("configuracao_estabelecimento_ausente")
            atual = repo.salvar_configuracao(
                configuracao,
                versao_esperada=versao_esperada,
            )
            self._auditar(
                session=session,
                contexto=contexto,
                acao="administracao.configuracao_atualizar",
                recurso_tipo="configuracao_estabelecimento",
                recurso_id=configuracao.unidade_id,
                antes={
                    "formas": len(anterior.formas_pagamento),
                    "taxa_servico": str(anterior.taxa_servico_percentual),
                    "versao": anterior.versao,
                },
                depois={
                    "formas": len(atual.formas_pagamento),
                    "taxa_servico": str(atual.taxa_servico_percentual),
                    "versao": atual.versao,
                },
            )
            session.commit()
            return atual

    def listar_usuarios(
        self, *, contexto: ContextoExecucao
    ) -> tuple[UsuarioAdminResumo, ...]:
        _exigir(contexto, Permissao.USUARIO_GERENCIAR)
        with self._session_factory() as session:
            identidades = RepositorioIdentidadesSQLAlchemy(session).listar_por_tenant(
                tenant_id=contexto.tenant_id
            )
            if not _administrador_tenant(contexto):
                permitidas = set(contexto.unidades_permitidas)
                identidades = tuple(
                    identidade
                    for identidade in identidades
                    if set(identidade.unidades_permitidas) & permitidas
                )
            return tuple(
                UsuarioAdminResumo(
                    usuario_id=identidade.usuario_id,
                    email=identidade.email,
                    ativo=identidade.ativo,
                    papeis=tuple(sorted(papel.value for papel in identidade.papeis)),
                    unidades=tuple(sorted(identidade.unidades_permitidas)),
                    unidade_padrao=identidade.unidade_id,
                    acesso_admin_sensivel=identidade.acesso_admin_sensivel,
                    permissoes_efetivas=tuple(
                        sorted(permissao.value for permissao in identidade.permissoes)
                    ),
                )
                for identidade in identidades
            )

    def criar_usuario(
        self,
        *,
        contexto: ContextoExecucao,
        email: str,
        password: str,
        unidade_padrao_id: str,
        papeis: Iterable[Papel],
        unidades_permitidas: Iterable[str],
        acesso_admin_sensivel: bool = False,
        admin_pin: str | None = None,
    ) -> IdentidadeUsuario:
        _exigir(contexto, Permissao.USUARIO_GERENCIAR)
        papeis_set = frozenset(papeis)
        if acesso_admin_sensivel or Papel.ADMINISTRADOR in papeis_set:
            _exigir(contexto, Permissao.PERMISSAO_GERENCIAR)
        unidades = frozenset(str(item).strip() for item in unidades_permitidas)
        with self._session_factory() as session:
            validas = {
                unidade.unidade_id
                for unidade in self._unidades_administraveis(
                    session=session,
                    contexto=contexto,
                    incluir_inativas=True,
                )
            }
            if not unidades or not unidades <= validas:
                raise PermissionError("usuario_unidades_fora_do_tenant")
            identidade = RepositorioIdentidadesSQLAlchemy(session).criar_usuario(
                email=email,
                password=password,
                tenant_id=contexto.tenant_id,
                unidade_padrao_id=unidade_padrao_id,
                papeis=papeis_set,
                unidades_permitidas=unidades,
                admin_pin=admin_pin,
                acesso_admin_sensivel=acesso_admin_sensivel,
            )
            self._auditar(
                session=session,
                contexto=contexto,
                acao="administracao.usuario_criar",
                recurso_tipo="usuario",
                recurso_id=identidade.usuario_id,
                depois={
                    "ativo": identidade.ativo,
                    "papeis": ",".join(sorted(p.value for p in identidade.papeis)),
                    "unidades": len(identidade.unidades_permitidas),
                    "admin_sensivel": identidade.acesso_admin_sensivel,
                },
            )
            session.commit()
            return identidade

    def atualizar_usuario(
        self,
        *,
        contexto: ContextoExecucao,
        usuario_id: str,
        papeis: Iterable[Papel],
        unidades_permitidas: Iterable[str],
        unidade_padrao_id: str,
        ativo: bool,
        acesso_admin_sensivel: bool,
        nova_senha: str | None = None,
    ) -> IdentidadeUsuario:
        _exigir(contexto, Permissao.USUARIO_GERENCIAR)
        _exigir(contexto, Permissao.PERMISSAO_GERENCIAR)
        if usuario_id == contexto.usuario_id and not ativo:
            raise ValueError("administrador_nao_pode_desativar_a_si_mesmo")

        papeis_set = frozenset(papeis)
        unidades = frozenset(str(item).strip() for item in unidades_permitidas)
        with self._session_factory() as session:
            validas = {
                unidade.unidade_id
                for unidade in self._unidades_administraveis(
                    session=session,
                    contexto=contexto,
                    incluir_inativas=True,
                )
            }
            if not unidades or not unidades <= validas:
                raise PermissionError("usuario_unidades_fora_do_tenant")
            repo = RepositorioIdentidadesSQLAlchemy(session)
            anterior = repo.obter_por_id(usuario_id=usuario_id)
            if anterior is None or anterior.tenant_id != contexto.tenant_id:
                raise LookupError("usuario_admin_ausente")

            repo.definir_papeis(usuario_id=usuario_id, papeis=papeis_set)
            repo.definir_unidades(
                usuario_id=usuario_id,
                unidades_permitidas=unidades,
                unidade_padrao_id=unidade_padrao_id,
            )
            repo.definir_ativo(usuario_id=usuario_id, ativo=ativo)
            repo.definir_acesso_admin_sensivel(
                usuario_id=usuario_id,
                autorizado=acesso_admin_sensivel,
            )
            if nova_senha is not None and nova_senha.strip():
                repo.trocar_senha(usuario_id=usuario_id, nova_senha=nova_senha)

            atual = repo.obter_por_id(usuario_id=usuario_id)
            if atual is None:
                raise RuntimeError("usuario_admin_nao_reconstruido")
            self._auditar(
                session=session,
                contexto=contexto,
                acao="administracao.usuario_atualizar",
                recurso_tipo="usuario",
                recurso_id=usuario_id,
                antes={
                    "ativo": anterior.ativo,
                    "papeis": ",".join(sorted(p.value for p in anterior.papeis)),
                    "unidades": len(anterior.unidades_permitidas),
                    "admin_sensivel": anterior.acesso_admin_sensivel,
                },
                depois={
                    "ativo": atual.ativo,
                    "papeis": ",".join(sorted(p.value for p in atual.papeis)),
                    "unidades": len(atual.unidades_permitidas),
                    "admin_sensivel": atual.acesso_admin_sensivel,
                },
            )
            session.commit()
            return atual

    def listar_integracoes(
        self,
        *,
        contexto: ContextoExecucao,
        unidades: Iterable[str] | None = None,
    ) -> tuple[IntegracaoAdminResumo, ...]:
        _exigir(contexto, Permissao.INTEGRACAO_GERENCIAR)
        unidades_alvo = set(unidades or ())
        with self._session_factory() as session:
            repo = RepositorioConfiguracoesExternasSQLAlchemy(session)
            unidades_validas = {
                u.unidade_id
                for u in self._unidades_administraveis(
                    session=session,
                    contexto=contexto,
                    incluir_inativas=True,
                )
            }
            if unidades_alvo:
                if not unidades_alvo <= unidades_validas:
                    raise PermissionError("integracao_unidade_fora_do_tenant")
            else:
                unidades_alvo = unidades_validas

            saida: list[IntegracaoAdminResumo] = []
            for unidade_id in sorted(unidades_alvo):
                configs = repo.listar(
                    tenant_id=contexto.tenant_id,
                    unidade_id=unidade_id,
                )
                for config in configs:
                    if not config.habilitada:
                        estado = EstadoProntidaoServico.DESATIVADO.value
                    elif config.homologada:
                        estado = EstadoProntidaoServico.PRONTO.value
                    else:
                        estado = EstadoProntidaoServico.CONFIGURADO.value
                    saida.append(
                        IntegracaoAdminResumo(
                            unidade_id=unidade_id,
                            configuracao_id=config.configuracao_id,
                            servico=config.servico,
                            provedor=config.provedor,
                            estado=estado,
                            habilitada=config.habilitada,
                            homologada=config.homologada,
                        )
                    )
            return tuple(saida)

    def listar_auditoria(
        self,
        *,
        contexto: ContextoExecucao,
        unidade_id: str | None = None,
        limite: int = 200,
    ) -> tuple[EventoAuditoria, ...]:
        _exigir(contexto, Permissao.AUDITORIA_VISUALIZAR)
        alvo = unidade_id or contexto.unidade_id
        with self._session_factory() as session:
            self._exigir_unidade_administravel(
                session=session,
                contexto=contexto,
                unidade_id=alvo,
            )
            return RepositorioAuditoriaSQLAlchemy(session).listar(
                tenant_id=contexto.tenant_id,
                unidade_id=alvo,
                limite=limite,
            )

    def _cmv_estimado(
        self,
        *,
        session: Session,
        tenant_id: str,
        unidades: tuple[str, ...],
    ) -> tuple[Decimal | None, Decimal]:
        total_itens = 0
        itens_cobertos = 0
        custo = Decimal("0")
        for unidade_id in unidades:
            vendas = session.execute(
                select(VendaFinanceiraORM.pedido_id).where(
                    VendaFinanceiraORM.tenant_id == tenant_id,
                    VendaFinanceiraORM.unidade_id == unidade_id,
                )
            ).scalars().all()
            if not vendas:
                continue
            itens = session.scalars(
                select(ItemPedidoORM).where(
                    ItemPedidoORM.tenant_id == tenant_id,
                    ItemPedidoORM.unidade_id == unidade_id,
                    ItemPedidoORM.pedido_id.in_(tuple(vendas)),
                )
            ).all()
            total_itens += len(itens)
            try:
                loja_id = resolver_loja_id_legada(
                    session,
                    tenant_id=tenant_id,
                    unidade_id=unidade_id,
                )
                produtos = Table(
                    "produtos",
                    MetaData(),
                    autoload_with=session.connection(),
                )
                if "custo_total_cmv" not in produtos.c or "loja_id" not in produtos.c:
                    continue
            except Exception:  # noqa: BLE001 - estimativa não bloqueia o painel
                continue
            for item in itens:
                bruto = str(item.produto_id or "").removeprefix("legacy:produto:")
                try:
                    produto_id = int(bruto)
                except ValueError:
                    continue
                row = session.execute(
                    select(produtos.c.custo_total_cmv).where(
                        produtos.c.id == produto_id,
                        produtos.c.loja_id == loja_id,
                    )
                ).first()
                if row is None or row[0] is None:
                    continue
                custo += Decimal(str(row[0])) * Decimal(item.quantidade)
                itens_cobertos += 1

        if total_itens == 0:
            return None, Decimal("0")
        cobertura = (
            Decimal(itens_cobertos) * Decimal("100") / Decimal(total_itens)
        )
        return (custo if itens_cobertos else None), cobertura

    def painel_executivo(
        self,
        *,
        contexto: ContextoExecucao,
        unidades: Iterable[str] | None = None,
    ) -> PainelExecutivoAdmin:
        _exigir(contexto, Permissao.FINANCEIRO_VISUALIZAR)
        with self._session_factory() as session:
            registradas = {
                u.unidade_id
                for u in self._unidades_administraveis(
                    session=session,
                    contexto=contexto,
                    incluir_inativas=True,
                )
            }
            alvo = tuple(sorted(set(unidades or registradas)))
            if not alvo or not set(alvo) <= registradas:
                raise PermissionError("painel_unidade_fora_do_tenant")

            vendas_total, vendas_qtd = session.execute(
                select(
                    func.coalesce(func.sum(VendaFinanceiraORM.valor), 0),
                    func.count(VendaFinanceiraORM.id),
                ).where(
                    VendaFinanceiraORM.tenant_id == contexto.tenant_id,
                    VendaFinanceiraORM.unidade_id.in_(alvo),
                )
            ).one()
            vendas_total_dec = _decimal(vendas_total)
            vendas_qtd_int = int(vendas_qtd or 0)

            pagamentos = session.execute(
                select(
                    PagamentoORM.status,
                    func.coalesce(func.sum(PagamentoORM.valor_pago), 0),
                    func.coalesce(func.sum(PagamentoORM.valor_estornado), 0),
                    func.coalesce(func.sum(PagamentoORM.saldo), 0),
                )
                .where(
                    PagamentoORM.tenant_id == contexto.tenant_id,
                    PagamentoORM.unidade_id.in_(alvo),
                )
                .group_by(PagamentoORM.status)
            ).all()
            pagos = Decimal("0")
            pendentes = Decimal("0")
            estornados = Decimal("0")
            for status, valor_pago, valor_estornado, saldo in pagamentos:
                status_normalizado = str(status).casefold()
                pagos += _decimal(valor_pago)
                estornados += _decimal(valor_estornado)
                if status_normalizado not in {"pago", "estornado", "cancelado"}:
                    pendentes += _decimal(saldo)

            dinheiro = _decimal(
                session.scalar(
                    select(func.coalesce(func.sum(PagamentoORM.valor_pago), 0)).where(
                        PagamentoORM.tenant_id == contexto.tenant_id,
                        PagamentoORM.unidade_id.in_(alvo),
                        PagamentoORM.metodo == "dinheiro",
                    )
                )
            )
            pedidos = int(
                session.scalar(
                    select(func.count(PedidoORM.id)).where(
                        PedidoORM.tenant_id == contexto.tenant_id,
                        PedidoORM.unidade_id.in_(alvo),
                    )
                )
                or 0
            )
            estoque_fisico, estoque_reservado = session.execute(
                select(
                    func.coalesce(func.sum(SaldoEstoqueORM.saldo_fisico), 0),
                    func.coalesce(func.sum(SaldoEstoqueORM.saldo_reservado), 0),
                ).where(
                    SaldoEstoqueORM.tenant_id == contexto.tenant_id,
                    SaldoEstoqueORM.unidade_id.in_(alvo),
                )
            ).one()
            entregas = session.execute(
                select(EntregaORM.status, func.count(EntregaORM.id))
                .where(
                    EntregaORM.tenant_id == contexto.tenant_id,
                    EntregaORM.unidade_id.in_(alvo),
                )
                .group_by(EntregaORM.status)
                .order_by(EntregaORM.status)
            ).all()

            integracoes = self.listar_integracoes(
                contexto=contexto,
                unidades=alvo,
            )
            usuarios_ativos = int(
                session.scalar(
                    select(func.count(UsuarioSegurancaORM.usuario_id)).where(
                        UsuarioSegurancaORM.tenant_id == contexto.tenant_id,
                        UsuarioSegurancaORM.ativo.is_(True),
                    )
                )
                or 0
            )
            cmv, cobertura = self._cmv_estimado(
                session=session,
                tenant_id=contexto.tenant_id,
                unidades=alvo,
            )
            margem = vendas_total_dec - cmv if cmv is not None else None

            return PainelExecutivoAdmin(
                tenant_id=contexto.tenant_id,
                unidades=alvo,
                financeiro=ResumoFinanceiroAdmin(
                    vendas_reconhecidas=vendas_total_dec,
                    quantidade_vendas=vendas_qtd_int,
                    ticket_medio=(
                        vendas_total_dec / Decimal(vendas_qtd_int)
                        if vendas_qtd_int
                        else Decimal("0")
                    ),
                    pagamentos_pagos=pagos,
                    pagamentos_pendentes=pendentes,
                    pagamentos_estornados=estornados,
                    recebido_dinheiro=dinheiro,
                    cmv_estimado_atual=cmv,
                    margem_estimada_atual=margem,
                    cobertura_cmv_itens_pct=cobertura,
                ),
                operacional=ResumoOperacionalAdmin(
                    pedidos=pedidos,
                    estoque_fisico_total=_decimal(estoque_fisico),
                    estoque_reservado_total=_decimal(estoque_reservado),
                    entregas_por_status=tuple(
                        (str(status), int(total)) for status, total in entregas
                    ),
                    integracoes_configuradas=len(integracoes),
                    integracoes_homologadas=sum(
                        1 for item in integracoes if item.homologada
                    ),
                    usuarios_ativos=usuarios_ativos,
                ),
            )
