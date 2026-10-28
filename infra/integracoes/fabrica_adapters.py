"""Composição runtime de adapters externos sob escopo tenant/unidade."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.integracoes.evolution import (
    ConfiguracaoEvolution,
    EvolutionAdapter,
    nome_instancia_evolution,
)
from core.integracoes.google_maps import (
    ConfiguracaoGoogleMaps,
    GoogleMapsAdapter,
    PortaHTTPMaps,
)
from core.integracoes.modelos import AmbienteIntegracao, ErroConfiguracaoServico
from core.integracoes.platform_scope import (
    FM_PLATFORM_TENANT_ID,
    FM_PLATFORM_UNIT_ID,
)
from core.integracoes.provedores import (
    ConfiguracaoGeminiTenant,
    ConfiguracaoMercadoPago,
    ConfiguracaoMeta,
    ConfiguracaoOpenAITenant,
    GeminiTenantAdapter,
    MercadoPagoAdapter,
    MetaAdapter,
    OpenAITenantAdapter,
    PortaDownloadBinario,
    PortaGeminiTenant,
    PortaHTTPProvedor,
    PortaOpenAITenant,
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
    OpenAIChatTenantGateway,
    RequestsBinaryTransport,
    RequestsGoogleMapsTransport,
    RequestsProviderTransport,
)


class FabricaAdaptersExternos:
    def __init__(self, *, session: Session, secret_store: SecretStore) -> None:
        self._session = session
        self._store = secret_store
        self._configs = RepositorioConfiguracoesExternasSQLAlchemy(session)

    @staticmethod
    def _validar_config(config, *, exigir_homologacao: bool = True):
        if config is None:
            raise ErroConfiguracaoServico("configuracao_indisponivel")
        if not config.habilitada:
            raise ErroConfiguracaoServico("integracao_desabilitada")
        if exigir_homologacao and not config.homologada:
            raise ErroConfiguracaoServico("integracao_nao_homologada")
        return config

    def _config(
        self,
        contexto: ContextoExecucao,
        configuracao_id: str,
        *,
        exigir_homologacao: bool = True,
    ):
        config = self._configs.obter(
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
            configuracao_id=configuracao_id,
        )
        return self._validar_config(
            config,
            exigir_homologacao=exigir_homologacao,
        )

    def _config_plataforma_ou_legado(
        self,
        contexto: ContextoExecucao,
        configuracao_id: str,
    ):
        """Resolve primeiro o Command e usa ponte legada somente se inequívoca.

        A ponte permite que as credenciais FM já homologadas no staging continuem
        atendendo novos tenants durante a migração. Assim que existir configuração
        no escopo do Command, ela se torna a única autoridade e o fallback deixa de
        ser considerado.
        """

        central = self._configs.obter(
            tenant_id=FM_PLATFORM_TENANT_ID,
            unidade_id=FM_PLATFORM_UNIT_ID,
            configuracao_id=configuracao_id,
        )
        if central is not None:
            return self._validar_config(central)

        legado_atual = self._configs.obter(
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
            configuracao_id=configuracao_id,
        )
        if legado_atual is not None:
            return self._validar_config(legado_atual)

        candidatos = tuple(
            config
            for config in self._configs.listar_homologadas_por_configuracao_id(
                configuracao_id=configuracao_id,
            )
            if not (
                config.tenant_id == FM_PLATFORM_TENANT_ID
                and config.unidade_id == FM_PLATFORM_UNIT_ID
            )
        )
        if not candidatos:
            raise ErroConfiguracaoServico("configuracao_plataforma_indisponivel")
        if len(candidatos) != 1:
            raise ErroConfiguracaoServico("configuracao_plataforma_legada_ambigua")
        return candidatos[0]

    def _segredo(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        provedor: str,
        finalidade: str,
    ) -> str:
        row = self._session.scalar(
            select(CredencialReferenciaORM)
            .where(
                CredencialReferenciaORM.tenant_id == tenant_id,
                CredencialReferenciaORM.unidade_id == unidade_id,
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

    def _credencial_por_papel(self, config, papel: str) -> str:
        finalidade = config.credenciais.get(papel)
        if not finalidade:
            raise ErroConfiguracaoServico("finalidade_credencial_indisponivel")
        return self._segredo(
            tenant_id=config.tenant_id,
            unidade_id=config.unidade_id,
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
        config = self._config_plataforma_ou_legado(contexto, configuracao_id)
        if (config.servico, config.provedor) != ("mapas", "google_maps"):
            raise ErroConfiguracaoServico("adapter_incompativel")
        parametros = config.parametros
        return GoogleMapsAdapter(
            configuracao=ConfiguracaoGoogleMaps(
                server_api_key=self._credencial_por_papel(config, "server_api_key"),
                language=str(parametros["language"]),
                country_code=str(parametros["country_code"]),
            ),
            http=http or RequestsGoogleMapsTransport(),
            sleep=sleep,
        )

    def chave_navegador_maps(
        self, *, contexto: ContextoExecucao, configuracao_id: str
    ) -> str:
        config = self._config_plataforma_ou_legado(contexto, configuracao_id)
        if (config.servico, config.provedor) != ("mapas", "google_maps"):
            raise ErroConfiguracaoServico("adapter_incompativel")
        return self._credencial_por_papel(config, "browser_api_key")

    def meta(
        self,
        *,
        contexto: ContextoExecucao,
        configuracao_id: str,
        http: PortaHTTPProvedor | None = None,
        media_http: PortaDownloadBinario | None = None,
        sleep: Callable[[float], None] = lambda _: None,
        exigir_homologacao: bool = True,
    ) -> MetaAdapter:
        config = self._config(
            contexto,
            configuracao_id,
            exigir_homologacao=exigir_homologacao,
        )
        if config.provedor != "meta":
            raise ErroConfiguracaoServico("adapter_incompativel")
        parametros = config.parametros
        return MetaAdapter(
            configuracao=ConfiguracaoMeta(
                servico=config.servico,
                access_token=self._credencial_por_papel(config, "access_token"),
                app_secret=self._credencial_por_papel(config, "app_secret"),
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
                    self._credencial_por_papel(config, "webhook_verify_token")
                    if "webhook_verify_token" in config.credenciais
                    else None
                ),
                graph_api_version=str(parametros.get("graph_api_version", "v23.0")),
            ),
            http=http or RequestsProviderTransport(),
            media_http=media_http or RequestsBinaryTransport(),
            sleep=sleep,
        )

    def evolution(
        self,
        *,
        contexto: ContextoExecucao,
        configuracao_id: str = "mensageria.whatsapp--evolution",
        http: PortaHTTPProvedor | None = None,
        exigir_homologacao: bool = True,
    ) -> EvolutionAdapter:
        config = self._config(
            contexto,
            configuracao_id,
            exigir_homologacao=exigir_homologacao,
        )
        if (config.servico, config.provedor) != ("mensageria.whatsapp", "evolution"):
            raise ErroConfiguracaoServico("adapter_incompativel")
        parametros = config.parametros
        return EvolutionAdapter(
            configuracao=ConfiguracaoEvolution(
                base_url=str(parametros["base_url"]),
                api_key=self._credencial_por_papel(config, "api_key"),
                webhook_token=self._credencial_por_papel(config, "webhook_token"),
                instance_name=nome_instancia_evolution(
                    contexto.tenant_id, contexto.unidade_id
                ),
            ),
            http=http or RequestsProviderTransport(),
        )

    def whatsapp(self, *, contexto: ContextoExecucao):
        """Resolve exatamente um transporte WhatsApp homologado, sem fallback."""
        disponiveis = []
        for config_id, builder in (
            ("mensageria.whatsapp--meta", self.meta),
            ("mensageria.whatsapp--evolution", self.evolution),
        ):
            try:
                disponiveis.append(
                    builder(contexto=contexto, configuracao_id=config_id)
                )
            except ErroConfiguracaoServico:
                continue
        if len(disponiveis) != 1:
            raise ErroConfiguracaoServico(
                "whatsapp_sem_provedor_unico"
                if not disponiveis
                else "whatsapp_provedor_ambiguo"
            )
        return disponiveis[0]

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
                access_token=self._credencial_por_papel(config, "access_token"),
                webhook_secret=self._credencial_por_papel(config, "webhook_secret"),
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
                token=self._credencial_por_papel(config, "api_token"),
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
        config = self._config_plataforma_ou_legado(contexto, configuracao_id)
        if (config.servico, config.provedor) != ("ia.generativa", "gemini"):
            raise ErroConfiguracaoServico("adapter_incompativel")
        return GeminiTenantAdapter(
            configuracao=ConfiguracaoGeminiTenant(
                api_key=self._credencial_por_papel(config, "api_key"),
                model=str(config.parametros["model"]),
            ),
            gateway=gateway or GoogleGenAITenantGateway(),
            sleep=sleep,
        )


    def openai(
        self,
        *,
        contexto: ContextoExecucao,
        configuracao_id: str,
        gateway: PortaOpenAITenant | None = None,
        sleep: Callable[[float], None] = lambda _: None,
    ) -> OpenAITenantAdapter:
        config = self._config_plataforma_ou_legado(contexto, configuracao_id)
        if (config.servico, config.provedor) != ("ia.generativa", "openai"):
            raise ErroConfiguracaoServico("adapter_incompativel")
        return OpenAITenantAdapter(
            configuracao=ConfiguracaoOpenAITenant(
                api_key=self._credencial_por_papel(config, "api_key"),
                model=str(config.parametros["model"]),
            ),
            gateway=gateway or OpenAIChatTenantGateway(),
            sleep=sleep,
        )
