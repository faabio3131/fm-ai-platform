"""Compatibilidade para o antigo placeholder `core.gerente_ai`.

A implementação V1 vive em `core.gerente_ia` e permanece desacoplada de ORM/UI.
"""

from core.gerente_ia import (
    ChamadaTool,
    ErroGerenteIA,
    PreviewAcao,
    RascunhoCampanha,
    ResultadoAcao,
    ResultadoTool,
    ServicoGerenteIA,
    ToolGerenteIA,
    gerente_ia_v1_enabled,
)

__all__ = [
    "ChamadaTool",
    "ErroGerenteIA",
    "PreviewAcao",
    "RascunhoCampanha",
    "ResultadoAcao",
    "ResultadoTool",
    "ServicoGerenteIA",
    "ToolGerenteIA",
    "gerente_ia_v1_enabled",
]
