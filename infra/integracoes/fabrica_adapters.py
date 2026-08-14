"""Composição runtime de adapters externos sob escopo tenant/unidade."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.integracoes.google_maps import (
    ConfiguracaoGoogleMaps,
    GoogleMapsAdapter,
    PortaHTTPMaps,
)
from core.integracoes.modelos import AmbienteIntegracao, ErroConfiguracaoServico
from core.integracoes.provedores import (
    ConfiguracaoGeminiTenant,
    ConfiguracaoMercadoPago,
    ConfiguracaoMeta,
    GeminiTenantAdapter,
    MercadoPagoAdapter,
    MetaAdapter,
    PortaGeminiTenant,
    PortaHTTPProvedor,
)
from core.pagamentos.pagbank import (
    AdapterPagBank,
    ConfiguracaoPagBank,
    TransporteHTTP,
)
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.segredos import SecretStore
from infra.seguranca.modelos_orm import CredencialReferenciaORM

from .repositorio_sqlalchemy import RepositorioConfiguracoesExternasSQLAlchemy
from .transportes import (
    GoogleGenAITenantGateway,
    RequestsGoogleMapsTransport,
    RequestsProviderTransport,
)


class FabricaAdaptersExternos:
    def __init__(self, *, session: Session, secret_store: SecretStore) -> None:
        self._session = session
        self._store = secret_store
        self._configs = RepositorioConfiguracoesExternasSQLAlchemy(session)

    def _config(self, contexto: ContextoExecucao, configuracao_id: str):
        config = self._configs.obter(
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
            configuracao_id=configuracao_id,
        )
        if config is None:
            raise ErroConfiguracaoServico("configuracao_indisponivel")
        if not config.habilitada or not config.homologada:
            raise ErroConfiguracaoServico("integracao_nao_homologada")
        return config

    def _segredo(
        self,
        *,
        contexto: ContextoExecucao,
        provedor: str,
        finalidade: str,
    ) -> str:
        row = self._session.scalar(
            select(CredencialReferenciaORM)
            .where(
                CredencialReferenciaORM.tenant_id == contexto.tenant_id,
                CredencialReferenciaORM.unidade_id == contexto.unidade_id,
                CredencialReferenciaORM.provedor == provedor,
                CredencialReferenciaORM.finalidade == finalidade,
                CredencialReferenciaORM.ativa.is_(True),
            )
            .order_by(CredencialReferenciaORM.versao.desc())
            .limit(1)
        )
        if row is None:
            raise ErroConfiguracaoServico("credencial_indisponivel")
        return self._store.resolve(row.referencia).reveal()

    def _credencial_por_papel(self, contexto: ContextoExecucao, config, papel: str) -> str:
        finalidade = config.credenciais.get(papel)
        if not finalidade:
            raise ErroConfiguracaoServico("finalidade_credencial_indisponivel")
        return self._segredo(
            contexto=contexto,
            provedor=config.provedor,
            finalidade=finalidade,
        )

    def google_maps(
        self,
        *,
        contexto: ContextoExecucao,
        configuracao_id: str,
        http: PortaHTTPMaps | None = None,
        sleep: Callable[[float], None] = lambda _: None,
    ) -> GoogleMapsAdapter:
        config = self._config(contexto, configuracao_id)
        if (config.servico, config.provedor) != ("mapas", "google_maps"):
            raise ErroConfiguracaoServico("adapter_incompativel")
        parametros = config.parametros
        return GoogleMapsAdapter(
            configuracao=ConfiguracaoGoogleMaps(
                server_api_key=self._credencial_por_papel(
                    contexto, config, "server_api_key"
                ),
                language=str(parametros["language"]),
                country_code=str(parametros["country_code"]),
            ),
            http=http or RequestsGoogleMapsTransport(),
            sleep=sleep,
        )

    def chave_navegador_maps(
        self, *, contexto: ContextoExecucao, configuracao_id: str
    ) -> str:
        config = self._config(contexto, configuracao_id)
        if (config.servico, config.provedor) != ("mapas", "google_maps"):
            raise ErroConfiguracaoServico("adapter_incompativel")
        return self._credencial_por_papel(contexto, config, "browser_api_key")

    def meta(
        self,
        *,
        contexto: ContextoExecucao,
        configuracao_id: str,
        http: PortaHTTPProvedor | None = None,
        sleep: Callable[[float], None] = lambda _: None,
    ) -> MetaAdapter:
        config = self._config(contexto, configuracao_id)
        if config.provedor != "meta":
            raise ErroConfiguracaoServico("adapter_incompativel")
        parametros = config.parametros
        return MetaAdapter(
            configuracao=ConfiguracaoMeta(
                servico=config.servico,
                access_token=self._credencial_por_papel(contexto, config, "access_token"),
                app_secret=self._credencial_por_papel(contexto, config, "app_secret"),
                app_id=str(parametros["app_id"]),
                page_id=(
                    str(parametros["page_id"]) if parametros.get("page_id") else None
                ),
                business_account_id=(
                    str(parametros["business_account_id"])
                    if parametros.get("business_account_id")
                    else None
                ),
                facebook_page_id=(
                    str(parametros["facebook_page_id"])
                    if parametros.get("facebook_page_id")
                    else None
                ),
                phone_number_id=(
                    str(parametros["phone_number_id"])
                    if parametros.get("phone_number_id")
                    else None
                ),
                webhook_verify_token=(
                    self._credencial_por_papel(contexto, config, "webhook_verify_token")
                    if "webhook_verify_token" in config.credenciais
                    else None
                ),
                graph_api_version=str(parametros.get("graph_api_version", "v23.0")),
            ),
            http=http or RequestsProviderTransport(),
            sleep=sleep,
        )

    def mercado_pago(
        self,
        *,
        contexto: ContextoExecucao,
        configuracao_id: str,
        http: PortaHTTPProvedor | None = None,
        sleep: Callable[[float], None] = lambda _: None,
    ) -> MercadoPagoAdapter:
        config = self._config(contexto, configuracao_id)
        if (config.servico, config.provedor) != ("pagamentos.pix", "mercado_pago"):
            raise ErroConfiguracaoServico("adapter_incompativel")
        return MercadoPagoAdapter(
            configuracao=ConfiguracaoMercadoPago(
                access_token=self._credencial_por_papel(contexto, config, "access_token"),
                webhook_secret=self._credencial_por_papel(contexto, config, "webhook_secret"),
                notification_url=str(config.parametros["notification_url"]),
            ),
            http=http or RequestsProviderTransport(),
            sleep=sleep,
        )

    def pagbank(
        self,
        *,
        contexto: ContextoExecucao,
        configuracao_id: str,
        transporte: TransporteHTTP | None = None,
    ) -> AdapterPagBank:
        config = self._config(contexto, configuracao_id)
        if (config.servico, config.provedor) != ("pagamentos.pix", "pagbank"):
            raise ErroConfiguracaoServico("adapter_incompativel")
        ambiente = (
            "production"
            if config.ambiente is AmbienteIntegracao.PRODUCAO
            else "sandbox"
        )
        parametros = config.parametros
        return AdapterPagBank(
            ConfiguracaoPagBank(
                token=self._credencial_por_papel(contexto, config, "api_token"),
                ambiente=ambiente,
                notification_url=str(parametros["notification_url"]),
                timeout_seconds=float(parametros.get("timeout_seconds", 10.0)),
            ),
            transporte=transporte,
        )

    def gemini(
        self,
        *,
        contexto: ContextoExecucao,
        configuracao_id: str,
        gateway: PortaGeminiTenant | None = None,
        sleep: Callable[[float], None] = lambda _: None,
    ) -> GeminiTenantAdapter:
        config = self._config(contexto, configuracao_id)
        if (config.servico, config.provedor) != ("ia.generativa", "gemini"):
            raise ErroConfiguracaoServico("adapter_incompativel")
        return GeminiTenantAdapter(
            configuracao=ConfiguracaoGeminiTenant(
                api_key=self._credencial_por_papel(contexto, config, "api_key"),
                model=str(config.parametros["model"]),
            ),
            gateway=gateway or GoogleGenAITenantGateway(),
            sleep=sleep,
        )
