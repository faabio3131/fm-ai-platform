"""Catálogo extensível de capacidades externas conhecidas pela V1."""

from __future__ import annotations

from dataclasses import dataclass

from .modelos import ErroConfiguracaoServico, normalizar_identificador


@dataclass(frozen=True, kw_only=True)
class EspecificacaoServico:
    servico: str
    provedor: str
    parametros_obrigatorios: frozenset[str]
    credenciais_obrigatorias: frozenset[str]

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
            servico="mapas",
            provedor="google_maps",
            parametros_obrigatorios=frozenset(
                {"origin_address", "country_code", "language", "currency"}
            ),
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
            servico="ia.generativa",
            provedor="gemini",
            parametros_obrigatorios=frozenset({"model", "region"}),
            credenciais_obrigatorias=frozenset({"api_key"}),
        ),
    )
)
