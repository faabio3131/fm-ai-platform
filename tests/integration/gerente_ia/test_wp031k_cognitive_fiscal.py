from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from application.gerente_ia_runtime import RuntimeGerenteIAV1
from core.gerente_ia.erros import ErroGerenteIA
from core.gerente_ia.modelos import ChamadaTool, NaturezaTool, ToolGerenteIA
from core.gerente_ia.tools import natureza_tool, validar_argumentos
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Papel, Permissao
from infra.fiscal.modelos_orm import FiscalDocumentProjectionORM
from infra.integracoes.modelos_orm import ServicoExternoConfigORM
from infra.seguranca.segredos_orm import SegredoIntegracaoORM
from migrations.runner import run_migrations

NOW = datetime(2026, 9, 20, 22, 0, tzinfo=timezone.utc)


def _contexto(*permissoes: Permissao) -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id="tenant-a",
        unidade_id="unit-a",
        usuario_id="admin-a",
        papeis=frozenset({Papel.ADMINISTRADOR}),
        permissoes=frozenset(permissoes),
        correlation_id="corr-wp031k",
        solicitado_em=NOW,
        origem="teste_wp031k",
        unidades_permitidas=frozenset({"unit-a"}),
    )


def _engine():
    engine = create_engine("sqlite:///:memory:")
    run_migrations(engine)
    return engine


def _seed(session: Session) -> None:
    session.add_all(
        [
            FiscalDocumentProjectionORM(
                document_id="doc-a-hom",
                tenant_id="tenant-a",
                unit_id="unit-a",
                environment="homologation",
                source_type="venda",
                source_id="sale-a",
                document_kind="nfce",
                state="rejected",
                access_key=None,
                protocol_reference=None,
                rejection_code="999",
                rejection_message="synthetic",
                correlation_id="corr-a",
                version=1,
                updated_at=NOW,
            ),
            FiscalDocumentProjectionORM(
                document_id="doc-b-hom",
                tenant_id="tenant-b",
                unit_id="unit-a",
                environment="homologation",
                source_type="venda",
                source_id="sale-b",
                document_kind="nfce",
                state="authorized",
                access_key=None,
                protocol_reference="p-b",
                rejection_code=None,
                rejection_message=None,
                correlation_id="corr-b",
                version=1,
                updated_at=NOW,
            ),
            FiscalDocumentProjectionORM(
                document_id="doc-a-prod",
                tenant_id="tenant-a",
                unit_id="unit-a",
                environment="production",
                source_type="venda",
                source_id="sale-prod",
                document_kind="nfce",
                state="authorized",
                access_key=None,
                protocol_reference="p-prod",
                rejection_code=None,
                rejection_message=None,
                correlation_id="corr-prod",
                version=1,
                updated_at=NOW,
            ),
            ServicoExternoConfigORM(
                tenant_id="tenant-a",
                unidade_id="unit-a",
                configuracao_id="fiscal.documentos--sefaz",
                servico="fiscal.documentos",
                provedor="sefaz",
                conta_externa="principal",
                ambiente="homologacao",
                parametros_publicos={"adapter_version": "wp031i-v1"},
                finalidades_credenciais={
                    "certificate_pfx": "fiscal_certificate_pfx",
                    "certificate_password": "fiscal_certificate_password",
                },
                habilitada=True,
                homologada=False,
                evidencia_homologacao_ref=None,
                versao=1,
                atualizado_por="admin-a",
                correlation_id="corr-config",
                criado_em=NOW,
                atualizado_em=NOW,
            ),
            SegredoIntegracaoORM(
                referencia="vault:wp031k-secret",
                tenant_id="tenant-a",
                unidade_id="unit-a",
                provedor="sefaz",
                finalidade="fiscal_certificate_password",
                ciphertext="SUPERSECRET-WP031K-MUST-NOT-LEAK",
                criado_por="admin-a",
                correlation_id="corr-secret",
                criado_em=NOW,
            ),
        ]
    )
    session.commit()


def test_wp031k_tool_is_read_only_and_rejects_scope_override() -> None:
    assert natureza_tool(ToolGerenteIA.CONSULTAR_FISCAL) is NaturezaTool.CONSULTA
    assert validar_argumentos(
        ToolGerenteIA.CONSULTAR_FISCAL,
        {"environment": "homologation", "tema": "resumo", "limite": 10},
    )["environment"] == "homologation"
    with pytest.raises(ErroGerenteIA, match="argumento_de_escopo_proibido"):
        validar_argumentos(
            ToolGerenteIA.CONSULTAR_FISCAL,
            {"tenant_id": "tenant-b"},
        )
    with pytest.raises(ErroGerenteIA, match="environment_fiscal_invalido"):
        validar_argumentos(
            ToolGerenteIA.CONSULTAR_FISCAL,
            {"environment": "development"},
        )


def test_wp031k_requires_core_and_fiscal_permissions() -> None:
    engine = _engine()
    with Session(engine) as session:
        runtime = RuntimeGerenteIAV1(session)
        chamada = ChamadaTool.de_dict(
            ToolGerenteIA.CONSULTAR_FISCAL,
            {"environment": "homologation"},
        )
        with pytest.raises(ErroGerenteIA):
            runtime.executar_tool(
                contexto=_contexto(Permissao.GERENTE_IA_CONSULTAR),
                chamada=chamada,
            )


def test_wp031k_isolates_tenant_unit_environment_and_never_reads_secret_value() -> None:
    engine = _engine()
    with Session(engine) as session:
        _seed(session)
        runtime = RuntimeGerenteIAV1(session)
        resultado = runtime.executar_tool(
            contexto=_contexto(
                Permissao.GERENTE_IA_CONSULTAR,
                Permissao.FISCAL_VISUALIZAR,
            ),
            chamada=ChamadaTool.de_dict(
                ToolGerenteIA.CONSULTAR_FISCAL,
                {"environment": "homologation", "tema": "documentos"},
            ),
        )
        payload = [item.para_dict() for item in resultado.registros]

    assert resultado.tool is ToolGerenteIA.CONSULTAR_FISCAL
    assert payload[0]["documentos_saida"] == 1
    assert payload[0]["documentos_rejeitados"] == 1
    assert any(item.get("document_id") == "doc-a-hom" for item in payload)
    serialized = repr(payload)
    assert "doc-b-hom" not in serialized
    assert "doc-a-prod" not in serialized
    assert "SUPERSECRET-WP031K-MUST-NOT-LEAK" not in serialized
    assert "ciphertext" not in serialized


def test_wp031k_recommendations_are_explicit_and_never_execute() -> None:
    engine = _engine()
    with Session(engine) as session:
        _seed(session)
        runtime = RuntimeGerenteIAV1(session)
        resultado = runtime.executar_tool(
            contexto=_contexto(
                Permissao.GERENTE_IA_CONSULTAR,
                Permissao.FISCAL_VISUALIZAR,
            ),
            chamada=ChamadaTool.de_dict(
                ToolGerenteIA.CONSULTAR_FISCAL,
                {"environment": "homologation", "tema": "pendencias"},
            ),
        )
        payload = [item.para_dict() for item in resultado.registros]

    recomendacoes = [
        item for item in payload if item.get("natureza") == "recomendacao"
    ]
    assert recomendacoes
    assert all(item["execucao"] == "nao_executada" for item in recomendacoes)
    assert any(
        item.get("codigo") == "configurar_perfil_emissor"
        for item in recomendacoes
    )
    assert any(
        item.get("codigo") == "revisar_documentos_rejeitados"
        for item in recomendacoes
    )
