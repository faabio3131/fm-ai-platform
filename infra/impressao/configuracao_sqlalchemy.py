"""Resolve destinos comerciais de impressão da configuração administrativa durável."""

from __future__ import annotations

from core.impressao import DestinoImpressao
from infra.administracao.repositorio_sqlalchemy import RepositorioAdministracaoSQLAlchemy
from sqlalchemy.orm import Session


class ResolverDestinosImpressaoSQLAlchemy:
    """Lê parametros_operacionais.impressao sem fallback entre tenants/unidades."""

    def __init__(self, session: Session) -> None:
        self._repo = RepositorioAdministracaoSQLAlchemy(session)

    def listar(self, *, tenant_id: str, unidade_id: str) -> tuple[DestinoImpressao, ...]:
        config = self._repo.obter_configuracao(tenant_id=tenant_id, unidade_id=unidade_id)
        if config is None:
            return ()
        bloco = config.parametros_operacionais.get("impressao", {})
        if not isinstance(bloco, dict):
            return ()
        bruto = bloco.get("destinos", [])
        if not isinstance(bruto, list):
            return ()
        destinos: list[DestinoImpressao] = []
        for item in bruto:
            if not isinstance(item, dict):
                continue
            if str(item.get("provider", "")).strip().lower() != "raw_tcp":
                continue
            try:
                destinos.append(
                    DestinoImpressao(
                        tenant_id=tenant_id,
                        unidade_id=unidade_id,
                        setor_id=str(item["setor_id"]).strip(),
                        impressora_id=str(item["impressora_id"]).strip(),
                        ativo=bool(item.get("ativo", True)),
                        max_tentativas=int(item.get("max_tentativas", 3)),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return tuple(destinos)
