"""Portas do Gerente IA V1.

Nenhuma porta expõe Session, ORM, SQL, credencial ou segredo. O Gerente IA só
orquestra serviços/projeções previamente autorizados pelo domínio.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from .modelos import (
    CampanhaAprovada,
    CampanhaPublicavel,
    PreviewAcao,
    RascunhoCampanha,
    RegistroGerencial,
    ResultadoAcao,
    ToolGerenteIA,
    ValorPrimitivo,
)


class PortaConsultasGerenciais(Protocol):
    def consultar_pedidos(
        self, *, tenant_id: str, unidade_id: str, filtros: dict[str, ValorPrimitivo]
    ) -> tuple[RegistroGerencial, ...]: ...

    def consultar_atrasos(
        self, *, tenant_id: str, unidade_id: str, filtros: dict[str, ValorPrimitivo]
    ) -> tuple[RegistroGerencial, ...]: ...

    def consultar_mesas(
        self, *, tenant_id: str, unidade_id: str, filtros: dict[str, ValorPrimitivo]
    ) -> tuple[RegistroGerencial, ...]: ...

    def consultar_cozinha(
        self, *, tenant_id: str, unidade_id: str, filtros: dict[str, ValorPrimitivo]
    ) -> tuple[RegistroGerencial, ...]: ...

    def consultar_entregas(
        self, *, tenant_id: str, unidade_id: str, filtros: dict[str, ValorPrimitivo]
    ) -> tuple[RegistroGerencial, ...]: ...

    def consultar_estoque(
        self, *, tenant_id: str, unidade_id: str, filtros: dict[str, ValorPrimitivo]
    ) -> tuple[RegistroGerencial, ...]: ...

    def sugerir_compra(
        self, *, tenant_id: str, unidade_id: str, filtros: dict[str, ValorPrimitivo]
    ) -> tuple[RegistroGerencial, ...]: ...

    def gerar_relatorio(
        self, *, tenant_id: str, unidade_id: str, filtros: dict[str, ValorPrimitivo]
    ) -> tuple[RegistroGerencial, ...]: ...

    def acompanhar_conversao(
        self, *, tenant_id: str, unidade_id: str, filtros: dict[str, ValorPrimitivo]
    ) -> tuple[RegistroGerencial, ...]: ...


class PortaAcoesGerenciais(Protocol):
    def previsualizar_priorizacao(
        self, *, tenant_id: str, unidade_id: str, pedido_id: str, prioridade: int
    ) -> RegistroGerencial: ...

    def priorizar_pedido(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        pedido_id: str,
        prioridade: int,
        motivo: str,
        idempotency_key: str,
        usuario_id: str,
        correlation_id: str,
    ) -> str: ...

    def previsualizar_pausa_produto(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        produto_id: str,
        duracao_minutos: int | None,
    ) -> RegistroGerencial: ...

    def pausar_produto(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        produto_id: str,
        motivo: str,
        duracao_minutos: int | None,
        idempotency_key: str,
        usuario_id: str,
        correlation_id: str,
    ) -> str: ...


class PortaCampanhasGerenciais(Protocol):
    def preparar_rascunho(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        canal: str,
        finalidade: str,
        objetivo: str,
        texto_base: str,
        usuario_id: str,
        correlation_id: str,
        idempotency_key: str,
    ) -> RascunhoCampanha: ...

@runtime_checkable
class PortaCampanhasGovernadas(PortaCampanhasGerenciais, Protocol):
    def aprovar(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        campanha_id: str,
        usuario_id: str,
        correlation_id: str,
        idempotency_key: str,
        agora: datetime,
    ) -> CampanhaAprovada: ...

    def publicar(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        campanha_id: str,
        usuario_id: str,
        correlation_id: str,
        idempotency_key: str,
        agora: datetime,
    ) -> CampanhaPublicavel: ...


class RepositorioPreviewsGerenteIA(Protocol):
    def adicionar(self, preview: PreviewAcao) -> None: ...

    def obter(
        self, *, tenant_id: str, unidade_id: str, preview_id: str
    ) -> PreviewAcao | None: ...

    def reservar_execucao(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        preview_id: str,
        fingerprint: str,
    ) -> PreviewAcao: ...

    def liberar_execucao(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        preview_id: str,
        fingerprint: str,
    ) -> None: ...

    def concluir(self, resultado: ResultadoAcao) -> None: ...

    def obter_resultado_por_idempotencia(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        idempotency_key: str,
    ) -> ResultadoAcao | None: ...

    def registrar_idempotencia(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        resultado: ResultadoAcao,
    ) -> None: ...


class PortaRegistroTools(Protocol):
    def tool_disponivel(self, tool: ToolGerenteIA) -> bool: ...
