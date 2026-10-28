"""Application boundary para extração documental governada e sem gravação de estoque."""
from __future__ import annotations

import io
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from application.ai_router_runtime import construir_ai_model_router
from application.legacy_estoque_leitura_visual import AplicacaoLeituraVisualEstoqueV1, ResultadoLeituraVisualEstoque
from core.ai_router import CapabilityIA, SolicitacaoIA
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.segredos import SecretStore
from infra.transacoes.uow import UnitOfWorkV1


def extrair_documento_estoque(
    *,
    contexto: ContextoExecucao,
    arquivo: bytes,
    session_factory: Callable[[], Session],
    secret_store_factory: Callable[[Session], SecretStore],
    aplicacao: AplicacaoLeituraVisualEstoqueV1,
) -> ResultadoLeituraVisualEstoque:
    """O UoW da aplicação possui a transação de auditoria; upload não grava insumos."""
    with UnitOfWorkV1(session_factory) as uow:
        session = uow.session
        if session is None:
            raise RuntimeError("estoque.uow_indisponivel")
        router = construir_ai_model_router(
            session=session,
            contexto=contexto,
            secret_store=secret_store_factory(session),
        )

        def gerar(*, contents: Any) -> Any:
            resposta = router.executar(
                SolicitacaoIA(
                    tenant_id=contexto.tenant_id,
                    unidade_id=contexto.unidade_id,
                    request_id=str(uuid4()),
                    correlation_id=contexto.correlation_id or str(uuid4()),
                    capability=CapabilityIA.ESTOQUE_LEITURA_DOCUMENTAL,
                    conteudo=contents,
                )
            )
            return SimpleNamespace(text=str(resposta.conteudo))

        resultado = aplicacao.executar(
            contexto, fonte_imagem=io.BytesIO(arquivo), generate_content=gerar
        )
        uow.commit()
        return resultado
