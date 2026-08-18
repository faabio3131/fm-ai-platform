"""Prova real da Browser API Key do Google Maps sem homologacao automatica.

O helper resolve a chave de navegador escopada no cofre e prepara um componente
HTML efemero. A evidencia somente aparece dentro do componente depois que a
Maps JavaScript API carrega e o mapa dispara ``tilesloaded``. A chave, por ser
uma browser key, necessariamente segue ao navegador, mas nunca entra na
referencia de evidencia, logs ou mensagens do servidor.
"""

from __future__ import annotations

import hashlib
import html
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.integracoes.modelos import ErroConfiguracaoServico
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.segredos import SecretStore
from infra.seguranca.modelos_orm import CredencialReferenciaORM

from .repositorio_sqlalchemy import RepositorioConfiguracoesExternasSQLAlchemy


@dataclass(frozen=True, kw_only=True)
class PreparacaoHealthcheckBrowserMaps:
    html: str
    evidencia_ref: str


def _evidencia_browser(
    *,
    contexto: ContextoExecucao,
    configuracao_id: str,
    evidencia_servidor: str,
    agora: datetime,
) -> str:
    instante = agora.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    material = "|".join(
        (
            contexto.tenant_id,
            contexto.unidade_id,
            configuracao_id,
            evidencia_servidor,
            instante,
            "maps-javascript-tilesloaded",
        )
    )
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"healthcheck://google-maps-full/{instante}/{digest}"


def preparar_healthcheck_browser_google_maps(
    *,
    session: Session,
    secret_store: SecretStore,
    contexto: ContextoExecucao,
    evidencia_servidor: str,
    configuracao_id: str = "mapas--google_maps",
    agora: datetime | None = None,
) -> PreparacaoHealthcheckBrowserMaps:
    """Prepara um mapa real que so revela a evidencia apos ``tilesloaded``."""

    if not evidencia_servidor.startswith("healthcheck://google-maps-server/"):
        raise ErroConfiguracaoServico("evidencia_servidor_maps_ausente")

    config = RepositorioConfiguracoesExternasSQLAlchemy(session).obter(
        tenant_id=contexto.tenant_id,
        unidade_id=contexto.unidade_id,
        configuracao_id=configuracao_id,
    )
    if config is None:
        raise ErroConfiguracaoServico("configuracao_indisponivel")
    if not config.habilitada:
        raise ErroConfiguracaoServico("integracao_desabilitada")
    if (config.servico, config.provedor) != ("mapas", "google_maps"):
        raise ErroConfiguracaoServico("adapter_incompativel")

    finalidade = str(config.credenciais.get("browser_api_key") or "").strip()
    if not finalidade:
        raise ErroConfiguracaoServico("browser_api_key_indisponivel")

    row = session.scalar(
        select(CredencialReferenciaORM)
        .where(
            CredencialReferenciaORM.tenant_id == contexto.tenant_id,
            CredencialReferenciaORM.unidade_id == contexto.unidade_id,
            CredencialReferenciaORM.provedor == "google_maps",
            CredencialReferenciaORM.finalidade == finalidade,
            CredencialReferenciaORM.ativa.is_(True),
        )
        .order_by(CredencialReferenciaORM.versao.desc())
        .limit(1)
    )
    if row is None:
        raise ErroConfiguracaoServico("credencial_indisponivel")

    browser_key = secret_store.resolve(row.referencia).reveal()
    evidencia = _evidencia_browser(
        contexto=contexto,
        configuracao_id=configuracao_id,
        evidencia_servidor=evidencia_servidor,
        agora=agora or datetime.now(timezone.utc),
    )

    key_url = quote(browser_key, safe="")
    evidencia_html = html.escape(evidencia, quote=True)
    html_doc = f"""<!doctype html>
<html lang=\"pt-BR\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"referrer\" content=\"strict-origin-when-cross-origin\" />
  <style>
    body {{ margin: 0; font-family: Arial, sans-serif; background: #0e1117; color: #fafafa; }}
    #status {{ padding: 10px 12px; border-radius: 8px; margin-bottom: 8px; background: #3a2d0b; }}
    #map {{ width: 100%; height: 340px; border-radius: 10px; overflow: hidden; }}
    #evidence {{ display: none; margin-top: 8px; padding: 10px 12px; border-radius: 8px; background: #123d2a; word-break: break-all; }}
    code {{ user-select: all; }}
  </style>
  <script>
    let proved = false;
    function fail(message) {{
      document.getElementById('status').textContent = 'Falha no teste real do navegador: ' + message;
      document.getElementById('status').style.background = '#5b1d1d';
    }}
    window.gm_authFailure = function() {{ fail('autenticacao/restricao da Browser API Key rejeitada pelo Google Maps.'); }};
    window.initMap = function() {{
      try {{
        const map = new google.maps.Map(document.getElementById('map'), {{
          center: {{ lat: -23.55052, lng: -46.633308 }},
          zoom: 13,
          mapTypeControl: false,
          streetViewControl: false,
        }});
        google.maps.event.addListenerOnce(map, 'tilesloaded', function() {{
          if (proved) return;
          proved = true;
          document.getElementById('status').textContent = 'Maps JavaScript API validada externamente no navegador. O mapa real carregou com sucesso.';
          document.getElementById('status').style.background = '#123d2a';
          document.getElementById('evidence').style.display = 'block';
        }});
      }} catch (err) {{ fail('nao foi possivel inicializar o mapa.'); }}
    }};
  </script>
</head>
<body>
  <div id=\"status\">Carregando Google Maps real no navegador...</div>
  <div id=\"map\"></div>
  <div id=\"evidence\"><strong>Evidencia final Google Maps:</strong><br><code>{evidencia_html}</code></div>
  <script async defer src=\"https://maps.googleapis.com/maps/api/js?key={key_url}&callback=initMap&v=weekly\" onerror=\"fail('script da Maps JavaScript API nao carregou.')\"></script>
</body>
</html>"""

    return PreparacaoHealthcheckBrowserMaps(html=html_doc, evidencia_ref=evidencia)
