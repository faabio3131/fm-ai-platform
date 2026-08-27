from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

from application.notificacoes_internas import despachar_alerta_estoque
from core.notificacoes_internas import (
    CanalNotificacaoInterna,
    ServicoNotificacoesInternas,
)
from core.seguranca.auditoria import RepositorioAuditoriaEmMemoria
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import MATRIZ_PADRAO, Papel, Permissao
from core.seguranca.segredos import SecretValue
from infra.integracoes.idempotencia_alertas import (
    chave_idempotencia_alerta_estoque_scoped,
)
from infra.notificacoes_internas.modelos_orm import (
    DestinatarioNotificacaoInternaORM,
)
from infra.notificacoes_internas.repositorio_sqlalchemy import (
    RepositorioNotificacoesInternasSQLAlchemy,
)
from migrations.internal_notification_recipients_v1 import (
    upgrade_internal_notification_recipients_v1,
)


_TENANT_A = "tenant-a"
_TENANT_B = "tenant-b"
_UNIT_A = "unidade-a"
_UNIT_B = "unidade-b"
_AGORA = datetime(2026, 8, 26, 22, 45, tzinfo=timezone.utc)
_ALERTA = {
    "insumo": "Queijo",
    "previsao_esgotamento": "Hoje às 20h",
    "mensagem_alerta": "Estoque crítico",
}


def _contexto(
    *,
    tenant_id: str = _TENANT_A,
    unidade_id: str = _UNIT_A,
    papel: Papel = Papel.GERENTE,
) -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id=tenant_id,
        unidade_id=unidade_id,
        usuario_id=f"{papel.value}-{tenant_id}-{unidade_id}",
        papeis=frozenset({papel}),
        permissoes=MATRIZ_PADRAO[papel],
        correlation_id=f"corr-{tenant_id}-{unidade_id}-{papel.value}",
        solicitado_em=_AGORA,
        origem="fitness.af10",
        unidades_permitidas=frozenset({unidade_id}),
    )


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as connection:
        upgrade_internal_notification_recipients_v1(connection)
    return engine


def _repositorio(session: Session) -> RepositorioNotificacoesInternasSQLAlchemy:
    return RepositorioNotificacoesInternasSQLAlchemy(
        session,
        master_key=Fernet.generate_key().decode("ascii"),
    )


def _configurar(
    servico: ServicoNotificacoesInternas,
    *,
    contexto: ContextoExecucao,
    destinatario_id: str,
    contato: str,
    ativo: bool = True,
    receber: bool = True,
):
    return servico.configurar_destinatario(
        contexto=contexto,
        destinatario_id=destinatario_id,
        nome_exibicao=f"Gestor {destinatario_id}",
        cargo="Gerente",
        canal=CanalNotificacaoInterna.WHATSAPP,
        contato=SecretValue(contato),
        receber_alertas_estoque=receber,
        ativo=ativo,
    )


class _EntregaFake:
    def __init__(self) -> None:
        self.chamadas: list[tuple[str, str, str, str]] = []

    def enviar(
        self,
        *,
        contexto: ContextoExecucao,
        referencia_contato: str,
        texto: str,
        idempotency_key: str,
    ) -> str:
        self.chamadas.append(
            (
                contexto.tenant_id,
                contexto.unidade_id,
                referencia_contato,
                idempotency_key,
            )
        )
        return f"msg-{len(self.chamadas)}"


def test_af10_a_lista_somente_destinatarios_do_escopo_ativo() -> None:
    engine = _engine()
    with Session(engine) as session:
        repo = _repositorio(session)
        servico = ServicoNotificacoesInternas(diretorio=repo)
        _configurar(
            servico,
            contexto=_contexto(),
            destinatario_id="dest-a",
            contato="5511999990001",
        )
        _configurar(
            servico,
            contexto=_contexto(unidade_id=_UNIT_B),
            destinatario_id="dest-b",
            contato="5511999990002",
        )
        _configurar(
            servico,
            contexto=_contexto(tenant_id=_TENANT_B),
            destinatario_id="dest-c",
            contato="5511999990003",
        )
        encontrados = servico.listar_alertas_estoque(contexto=_contexto())
        assert tuple(item.destinatario_id for item in encontrados) == ("dest-a",)


def test_af10_b_outro_tenant_nunca_e_retornado() -> None:
    engine = _engine()
    with Session(engine) as session:
        repo = _repositorio(session)
        servico = ServicoNotificacoesInternas(diretorio=repo)
        _configurar(
            servico,
            contexto=_contexto(tenant_id=_TENANT_B),
            destinatario_id="dest-outro-tenant",
            contato="5511999990010",
        )
        assert servico.listar_alertas_estoque(contexto=_contexto()) == ()


def test_af10_c_outra_unidade_nunca_e_retornada() -> None:
    engine = _engine()
    with Session(engine) as session:
        repo = _repositorio(session)
        servico = ServicoNotificacoesInternas(diretorio=repo)
        _configurar(
            servico,
            contexto=_contexto(unidade_id=_UNIT_B),
            destinatario_id="dest-outra-unidade",
            contato="5511999990011",
        )
        assert servico.listar_alertas_estoque(contexto=_contexto()) == ()


def test_af10_d_mesmo_contato_pode_existir_em_escopos_distintos() -> None:
    engine = _engine()
    with Session(engine) as session:
        repo = _repositorio(session)
        servico = ServicoNotificacoesInternas(diretorio=repo)
        contato = "5511999990020"
        a = _configurar(
            servico,
            contexto=_contexto(),
            destinatario_id="dest-scope-a",
            contato=contato,
        )
        b = _configurar(
            servico,
            contexto=_contexto(unidade_id=_UNIT_B),
            destinatario_id="dest-scope-b",
            contato=contato,
        )
        assert a.referencia_contato != b.referencia_contato


def test_af10_e_referencia_de_outro_escopo_falha_fechado() -> None:
    engine = _engine()
    with Session(engine) as session:
        repo = _repositorio(session)
        servico = ServicoNotificacoesInternas(diretorio=repo)
        destinatario = _configurar(
            servico,
            contexto=_contexto(),
            destinatario_id="dest-ref",
            contato="5511999990030",
        )
        with pytest.raises(LookupError, match="escopo"):
            repo.resolver_contato(
                contexto=_contexto(unidade_id=_UNIT_B),
                referencia_contato=destinatario.referencia_contato,
            )


def test_af10_f_configuracao_sem_capability_falha_sem_efeitos() -> None:
    capability = Permissao.NOTIFICACAO_INTERNA_GERENCIAR
    assert capability in MATRIZ_PADRAO[Papel.ADMINISTRADOR]
    assert capability in MATRIZ_PADRAO[Papel.GERENTE]
    assert all(
        capability not in permissoes
        for papel, permissoes in MATRIZ_PADRAO.items()
        if papel not in {Papel.ADMINISTRADOR, Papel.GERENTE}
    )

    engine = _engine()
    with Session(engine) as session:
        repo = _repositorio(session)
        servico = ServicoNotificacoesInternas(diretorio=repo)
        with pytest.raises(
            PermissionError,
            match="notificacao_interna.gerenciar",
        ):
            _configurar(
                servico,
                contexto=_contexto(papel=Papel.CAIXA),
                destinatario_id="dest-negado",
                contato="5511999990040",
            )
        quantidade = session.scalar(
            select(func.count()).select_from(
                DestinatarioNotificacaoInternaORM
            )
        )
        assert quantidade == 0


def test_af10_g_inativo_ou_sem_preferencia_nao_recebe_alerta() -> None:
    engine = _engine()
    with Session(engine) as session:
        repo = _repositorio(session)
        servico = ServicoNotificacoesInternas(diretorio=repo)
        _configurar(
            servico,
            contexto=_contexto(),
            destinatario_id="dest-inativo",
            contato="5511999990050",
        )
        servico.atualizar_preferencias(
            contexto=_contexto(),
            destinatario_id="dest-inativo",
            receber_alertas_estoque=False,
            ativo=False,
        )
        assert servico.listar_alertas_estoque(contexto=_contexto()) == ()


def test_af10_h_diretorio_vazio_nao_faz_fallback_legado() -> None:
    engine = _engine()
    with Session(engine) as session:
        repo = _repositorio(session)
        entrega = _EntregaFake()
        resultados = despachar_alerta_estoque(
            contexto=_contexto(),
            diretorio=repo,
            entrega=entrega,
            alerta=_ALERTA,
            texto="Alerta de estoque",
            data_referencia=date(2026, 8, 26),
        )
        assert resultados == ()
        assert entrega.chamadas == ()
    source = Path("application/notificacoes_internas.py").read_text(
        encoding="utf-8"
    )
    assert "ContatoGerencial" not in source
    assert "contatos_gerenciais" not in source


def test_af10_i_dispatcher_entrega_somente_para_o_escopo_ativo() -> None:
    engine = _engine()
    with Session(engine) as session:
        repo = _repositorio(session)
        servico = ServicoNotificacoesInternas(diretorio=repo)
        esperado = _configurar(
            servico,
            contexto=_contexto(),
            destinatario_id="dest-dispatch",
            contato="5511999990060",
        )
        _configurar(
            servico,
            contexto=_contexto(unidade_id=_UNIT_B),
            destinatario_id="dest-fora",
            contato="5511999990061",
        )
        entrega = _EntregaFake()
        resultados = despachar_alerta_estoque(
            contexto=_contexto(),
            diretorio=repo,
            entrega=entrega,
            alerta=_ALERTA,
            texto="Alerta de estoque",
            data_referencia=date(2026, 8, 26),
        )
        assert len(resultados) == 1
        assert resultados[0].destinatario_id == "dest-dispatch"
        assert resultados[0].enviado is True
        assert entrega.chamadas[0][2] == esperado.referencia_contato


def test_af10_j_idempotencia_inclui_tenant_e_unidade() -> None:
    base = dict(
        destinatario_id="dest-idem",
        alerta=_ALERTA,
        data_referencia=date(2026, 8, 26),
    )
    a = chave_idempotencia_alerta_estoque_scoped(
        tenant_id=_TENANT_A,
        unidade_id=_UNIT_A,
        **base,
    )
    replay = chave_idempotencia_alerta_estoque_scoped(
        tenant_id=_TENANT_A,
        unidade_id=_UNIT_A,
        **base,
    )
    outro_tenant = chave_idempotencia_alerta_estoque_scoped(
        tenant_id=_TENANT_B,
        unidade_id=_UNIT_A,
        **base,
    )
    outra_unidade = chave_idempotencia_alerta_estoque_scoped(
        tenant_id=_TENANT_A,
        unidade_id=_UNIT_B,
        **base,
    )
    assert a == replay
    assert len({a, outro_tenant, outra_unidade}) == 3


def test_af10_k_auditoria_preserva_scope_sem_pii() -> None:
    engine = _engine()
    auditoria = RepositorioAuditoriaEmMemoria()
    with Session(engine) as session:
        repo = _repositorio(session)
        servico = ServicoNotificacoesInternas(
            diretorio=repo,
            auditoria=auditoria,
        )
        _configurar(
            servico,
            contexto=_contexto(),
            destinatario_id="dest-audit",
            contato="5511999990070",
        )
        entrega = _EntregaFake()
        despachar_alerta_estoque(
            contexto=_contexto(),
            diretorio=repo,
            entrega=entrega,
            alerta=_ALERTA,
            texto="Alerta de estoque",
            data_referencia=date(2026, 8, 26),
            auditoria=auditoria,
        )
    assert auditoria.eventos
    serializado = repr(
        [evento.para_dict() for evento in auditoria.eventos]
    )
    assert "5511999990070" not in serializado
    assert "ciphertext" not in serializado.casefold()
    assert all(
        evento.tenant_id == _TENANT_A
        and evento.unidade_id == _UNIT_A
        and evento.correlation_id == _contexto().correlation_id
        for evento in auditoria.eventos
    )


def test_af10_l_migration_nao_inventa_backfill_do_legado_global() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE contatos_gerenciais ("
                "id INTEGER PRIMARY KEY, nome VARCHAR, whatsapp VARCHAR, "
                "cargo VARCHAR, receber_alertas_estoque INTEGER)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO contatos_gerenciais "
                "(id, nome, whatsapp, cargo, receber_alertas_estoque) "
                "VALUES (1, 'Gerente legado', '5511999990080', 'Gerente', 1)"
            )
        )
        upgrade_internal_notification_recipients_v1(connection)
        assert connection.execute(
            text(
                "SELECT COUNT(*) "
                "FROM notificacao_interna_destinatarios_v1"
            )
        ).scalar_one() == 0
        assert connection.execute(
            text("SELECT COUNT(*) FROM contatos_gerenciais")
        ).scalar_one() == 1


def test_af10_m_novo_codigo_nao_aumenta_dependencia_do_legado() -> None:
    proibidos: list[str] = []
    for raiz in ("core", "application", "infra"):
        for path in Path(raiz).rglob("*.py"):
            if path.as_posix() == "infra/legacy_schema.py":
                continue
            conteudo = path.read_text(encoding="utf-8")
            if "contatos_gerenciais" in conteudo or "ContatoGerencial" in conteudo:
                proibidos.append(path.as_posix())
    assert proibidos == []
