"""Política versionada de liberação à cozinha."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from core.dominio.decisoes import DecisaoCozinha
from core.dominio.enums import (
    CanalAtendimento,
    CodigoDecisaoCozinha,
    MomentoPagamento,
    OrigemPedido,
    PapelUsuario,
    RiscoPedido,
)
from core.seguranca import ContextoExecucao, Papel, Permissao
from core.seguranca.auditoria import sanitizar_metadata


@dataclass(frozen=True, kw_only=True)
class PoliticaCozinha:
    policy_id: str
    version: int
    canal: CanalAtendimento
    origem: OrigemPedido
    momento_pagamento: MomentoPagamento
    risco: RiscoPedido = RiscoPedido.BAIXO
    permite_pagamento_posterior: bool = False
    requer_pagamento_confirmado: bool = True
    requer_estoque_disponivel: bool = True
    requer_confirmacao_humana: bool = False
    override_permitido: bool = False
    papel_override: Papel = Papel.GERENTE
    metadata: dict[str, Any] = field(default_factory=dict)


def pode_enviar_para_cozinha(
    *,
    politica: PoliticaCozinha,
    contexto: ContextoExecucao,
    pagamento_confirmado: bool,
    estoque_disponivel: bool,
    confirmacao_humana: bool = False,
    solicitar_override: bool = False,
    decidido_em: datetime | None = None,
) -> DecisaoCozinha:
    agora = decidido_em or contexto.solicitado_em
    override = (
        solicitar_override
        and politica.override_permitido
        and politica.papel_override in contexto.papeis
        and Permissao.PEDIDO_LIBERAR_COZINHA in contexto.permissoes
        and Papel.GERENTE_IA not in contexto.papeis
    )
    codigo = CodigoDecisaoCozinha.PERMITIDO_PAGAMENTO_CONFIRMADO
    permitido = True
    motivo = "Pagamento confirmado"
    exige = False
    if politica.risco in {RiscoPedido.ALTO, RiscoPedido.BLOQUEADO} and not override:
        permitido, codigo, motivo, exige = (
            False,
            CodigoDecisaoCozinha.BLOQUEADO_RISCO_ALTO,
            "Risco exige análise humana",
            True,
        )
    elif politica.requer_estoque_disponivel and not estoque_disponivel and not override:
        permitido, codigo, motivo = (
            False,
            CodigoDecisaoCozinha.BLOQUEADO_ESTOQUE,
            "Estoque indisponível",
        )
    elif politica.requer_confirmacao_humana and not confirmacao_humana and not override:
        permitido, codigo, motivo, exige = (
            False,
            CodigoDecisaoCozinha.EXIGE_APROVACAO_MANUAL,
            "Confirmação humana exigida",
            True,
        )
    elif (
        politica.requer_pagamento_confirmado
        and not pagamento_confirmado
        and not override
    ):
        permitido, codigo, motivo = (
            False,
            CodigoDecisaoCozinha.BLOQUEADO_PAGAMENTO_PENDENTE,
            "Pagamento pendente",
        )
    elif not pagamento_confirmado:
        if politica.permite_pagamento_posterior or politica.momento_pagamento in {
            MomentoPagamento.NA_ENTREGA,
            MomentoPagamento.NO_FECHAMENTO,
            MomentoPagamento.NA_RETIRADA,
            MomentoPagamento.POSTERIOR_AUTORIZADO,
        }:
            codigo, motivo = (
                CodigoDecisaoCozinha.PERMITIDO_PAGAMENTO_POSTERIOR,
                "Pagamento posterior permitido pela política",
            )
        elif not override:
            permitido, codigo, motivo = (
                False,
                CodigoDecisaoCozinha.BLOQUEADO_POLITICA_CANAL,
                "Canal não permite liberação",
            )
    if override:
        permitido, codigo, motivo = (
            True,
            CodigoDecisaoCozinha.PERMITIDO_PAGAMENTO_POSTERIOR,
            "Override humano autorizado e auditável",
        )
    papel = PapelUsuario(politica.papel_override.value) if exige else None
    return DecisaoCozinha(
        permitido=permitido,
        codigo_decisao=codigo,
        justificativa=motivo,
        confirmacao_exigida=exige,
        risco=politica.risco,
        politica_aplicada=politica.policy_id,
        versao_politica=str(politica.version),
        decidido_em=agora,
        papel_responsavel_exigido=papel,
        metadados=dict(
            sanitizar_metadata(
                {
                    **politica.metadata,
                    "override": override,
                    "canal": politica.canal.value,
                    "origem": politica.origem.value,
                }
            )
        ),
    )
