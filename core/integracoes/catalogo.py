"""Catálogo extensível de capacidades externas conhecidas pela V1."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .modelos import ErroConfiguracaoServico, normalizar_identificador


class EscopoGestaoIntegracao(StrEnum):
    TENANT_MANAGED = "tenant_managed"
    PLATFORM_MANAGED = "platform_managed"


@dataclass(frozen=True, kw_only=True)
class EspecificacaoServico:
    servico: str
    provedor: str
    parametros_obrigatorios: frozenset[str]
    credenciais_obrigatorias: frozenset[str]
    escopo_gestao: EscopoGestaoIntegracao = EscopoGestaoIntegracao.TENANT_MANAGED
    # Catálogo/cadastro não significa adapter de cobrança implementado.
    runtime_operacional: bool = True
    credenciais_opcionais: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "servico", normalizar_identificador(self.servico, "servico")
        )
        object.__setattr__(
            self, "provedor", normalizar_identificador(self.provedor, "provedor")
        )


class CatalogoServicosExternos:
    def __init__(self, especificacoes: tuple[EspecificacaoServico, ...]) -> None:
        self._itens: dict[tuple[str, str], EspecificacaoServico] = {}
        for item in especificacoes:
            chave = item.servico, item.provedor
            if chave in self._itens:
                raise ErroConfiguracaoServico("servico_provedor_duplicado")
            self._itens[chave] = item

    def obter(self, servico: str, provedor: str) -> EspecificacaoServico:
        chave = (
            normalizar_identificador(servico, "servico"),
            normalizar_identificador(provedor, "provedor"),
        )
        try:
            return self._itens[chave]
        except KeyError as exc:
            raise ErroConfiguracaoServico("servico_provedor_nao_suportado") from exc

    def listar(self) -> tuple[EspecificacaoServico, ...]:
        return tuple(
            self._itens[chave]
            for chave in sorted(self._itens, key=lambda item: (item[0], item[1]))
        )

    def listar_por_escopo(
        self,
        escopo: EscopoGestaoIntegracao,
    ) -> tuple[EspecificacaoServico, ...]:
        return tuple(item for item in self.listar() if item.escopo_gestao is escopo)


CATALOGO_V1 = CatalogoServicosExternos(
    (
        EspecificacaoServico(
            servico="social.facebook",
            provedor="meta",
            parametros_obrigatorios=frozenset({"page_id", "app_id"}),
            credenciais_obrigatorias=frozenset({"access_token", "app_secret"}),
        ),
        EspecificacaoServico(
            servico="social.instagram",
            provedor="meta",
            parametros_obrigatorios=frozenset(
                {"business_account_id", "facebook_page_id", "app_id"}
            ),
            credenciais_obrigatorias=frozenset({"access_token", "app_secret"}),
        ),
        EspecificacaoServico(
            servico="mensageria.whatsapp",
            provedor="meta",
            parametros_obrigatorios=frozenset(
                {"business_account_id", "phone_number_id", "app_id"}
            ),
            credenciais_obrigatorias=frozenset(
                {"access_token", "app_secret", "webhook_verify_token"}
            ),
        ),
        EspecificacaoServico(
            servico="mensageria.whatsapp",
            provedor="evolution",
            parametros_obrigatorios=frozenset({"base_url", "webhook_url"}),
            credenciais_obrigatorias=frozenset({"api_key", "webhook_token"}),
        ),
        EspecificacaoServico(
            servico="mapas",
            provedor="google_maps",
            escopo_gestao=EscopoGestaoIntegracao.PLATFORM_MANAGED,
            # O adapter executável usa apenas idioma e país como parâmetros
            # públicos. Endereço de origem pertence ao contexto de cada rota e
            # moeda não participa de geocodificação/Routes API; mantê-los como
            # obrigatórios criava campos mortos no Control Plane.
            parametros_obrigatorios=frozenset({"country_code", "language"}),
            credenciais_obrigatorias=frozenset(
                {"browser_api_key", "server_api_key"}
            ),
        ),
        EspecificacaoServico(
            servico="pagamentos.pix",
            provedor="pagbank",
            parametros_obrigatorios=frozenset({"notification_url"}),
            credenciais_obrigatorias=frozenset({"api_token"}),
        ),
        EspecificacaoServico(
            servico="pagamentos.pix",
            provedor="mercado_pago",
            parametros_obrigatorios=frozenset({"notification_url"}),
            credenciais_obrigatorias=frozenset({"access_token", "webhook_secret"}),
        ),
        EspecificacaoServico(
            servico="marketplace.pedidos",
            provedor="ifood",
            parametros_obrigatorios=frozenset(),
            credenciais_obrigatorias=frozenset({"client_id", "client_secret"}),
        ),
        EspecificacaoServico(
            servico="marketplace.pedidos",
            provedor="keeta",
            parametros_obrigatorios=frozenset(),
            credenciais_obrigatorias=frozenset({"client_id", "client_secret"}),
        ),
        # Provedores financeiros configuráveis pelo estabelecimento.
        # Na V1 estas novas opções são CADASTRO SEGURO, não captura nem
        # liquidação implementadas; operações dependem de adapters certificados.
        *(
            EspecificacaoServico(
                servico="pagamentos.pix",
                provedor=provedor,
                parametros_obrigatorios=frozenset({"notification_url"}),
                credenciais_obrigatorias=frozenset(papeis),
                runtime_operacional=False,
            )
            for provedor, papeis in (
                ("asaas", ("api_key",)),
                ("picpay", ("client_id", "client_secret")),
                ("pagarme", ("api_key",)),
                ("efi", ("client_id", "client_secret")),
            )
        ),
        *(
            EspecificacaoServico(
                servico="pagamentos.cartao",
                provedor=provedor,
                parametros_obrigatorios=frozenset(),
                credenciais_obrigatorias=frozenset(papeis),
                runtime_operacional=False,
            )
            for provedor, papeis in (
                ("mercado_pago", ("access_token",)),
                ("asaas", ("api_key",)),
                ("picpay", ("client_id", "client_secret")),
                ("pagarme", ("api_key",)),
                ("stone", ("api_key",)),
                ("cielo", ("merchant_id", "merchant_key")),
                ("rede", ("pv", "integration_key")),
                ("getnet", ("client_id", "client_secret")),
                ("sumup", ("access_token",)),
                ("infinitepay", ("api_key",)),
            )
        ),
        # Dados bancários são protegidos no Vault, não enviados por HTTP como
        # parâmetros públicos. Isto é cadastro de destino, não Open Banking.
        *(
            EspecificacaoServico(
                servico="financeiro.conta_bancaria",
                provedor=provedor,
                parametros_obrigatorios=frozenset({"tipo_conta"}),
                credenciais_obrigatorias=frozenset(
                    {"agencia", "numero_conta"}
                ),
                credenciais_opcionais=frozenset(
                    {"chave_pix", "digito_conta"}
                ),
                runtime_operacional=False,
            )
            for provedor in (
                "banco_do_brasil",
                "itau",
                "bradesco",
                "caixa",
                "santander",
                "nubank",
                "inter",
                "sicredi",
                "sicoob",
                "c6",
                "btg_pactual",
                "original",
                "mercado_pago",
                "pagbank",
                "asaas",
                "picpay",
            )
        ),
        EspecificacaoServico(
            servico="fiscal.documentos",
            provedor="sefaz",
            parametros_obrigatorios=frozenset(
                {"signer_kind", "signing_algorithm", "adapter_version"}
            ),
            credenciais_obrigatorias=frozenset(
                {"certificate_pfx", "certificate_password"}
            ),
        ),
        EspecificacaoServico(
            servico="ia.generativa",
            provedor="openai",
            escopo_gestao=EscopoGestaoIntegracao.PLATFORM_MANAGED,
            parametros_obrigatorios=frozenset({"model"}),
            credenciais_obrigatorias=frozenset({"api_key"}),
        ),
        EspecificacaoServico(
            servico="ia.generativa",
            provedor="gemini",
            escopo_gestao=EscopoGestaoIntegracao.PLATFORM_MANAGED,
            # O runtime Gemini baseado em API key usa somente o modelo como
            # configuração pública efetivamente consumida. Exigir ``region`` aqui
            # criava um campo morto: o control plane o marcava como obrigatório,
            # mas nenhum adapter/gateway o utilizava. Parâmetros obrigatórios devem
            # corresponder apenas ao contrato executável real.
            parametros_obrigatorios=frozenset({"model"}),
            credenciais_obrigatorias=frozenset({"api_key"}),
        ),
    )
)
