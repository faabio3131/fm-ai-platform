"""Prova real da Browser API Key do Google Maps sem homologacao automatica.

A Maps JavaScript API nao pode ser homologada de forma confiavel dentro de
``components.html`` do Streamlit porque esse componente usa ``about:srcdoc`` e o
Google enxerga um referenciador opaco. Este helper resolve a Browser API Key
escopada no cofre e registra uma pagina efemera em um servidor HTTP local,
bindado somente em 127.0.0.1. A pagina e carregada pelo navegador em
``http://localhost:8765/...`` e a evidencia so fica visivel depois de
``tilesloaded``.

A Browser API Key necessariamente segue ao navegador para a Maps JavaScript
API, mas nao entra em logs, mensagens do servidor nem na referencia de
evidencia.
"""

from __future__ import annotations

import hashlib
import html
import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote, urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.integracoes.modelos import ErroConfiguracaoServico
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.segredos import SecretStore
from infra.seguranca.modelos_orm import CredencialReferenciaORM

from .repositorio_sqlalchemy import RepositorioConfiguracoesExternasSQLAlchemy

_LOCAL_HOST = "127.0.0.1"
_LOCAL_PUBLIC_HOST = "localhost"
_LOCAL_PORT = 8765


@dataclass(frozen=True, kw_only=True)
class PreparacaoHealthcheckBrowserMaps:
    url: str
    evidencia_ref: str


class _ServidorProvaMaps(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self) -> None:
        super().__init__((_LOCAL_HOST, _LOCAL_PORT), _HandlerProvaMaps)
        self.paginas: dict[str, str] = {}
        self._lock = threading.Lock()

    def registrar(self, *, token: str, html_doc: str) -> str:
        path = f"/google-maps-proof/{token}"
        with self._lock:
            self.paginas[path] = html_doc
            # Mantem somente uma janela curta de provas recentes em memoria.
            if len(self.paginas) > 12:
                for antigo in tuple(self.paginas)[:-12]:
                    self.paginas.pop(antigo, None)
        return f"http://{_LOCAL_PUBLIC_HOST}:{_LOCAL_PORT}{path}"

    def obter(self, path: str) -> str | None:
        with self._lock:
            return self.paginas.get(path)


class _HandlerProvaMaps(BaseHTTPRequestHandler):
    server: _ServidorProvaMaps

    def do_GET(self) -> None:  # noqa: N802 - contrato BaseHTTPRequestHandler
        path = urlparse(self.path).path
        pagina = self.server.obter(path)
        if pagina is None:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b"Prova indisponivel.")
            return
        payload = pagina.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        # Nunca registrar URL/payload da prova para evitar exposicao acidental.
        return


_SERVIDOR_LOCK = threading.Lock()
_SERVIDOR: _ServidorProvaMaps | None = None


def _servidor_local() -> _ServidorProvaMaps:
    global _SERVIDOR
    with _SERVIDOR_LOCK:
        if _SERVIDOR is not None:
            return _SERVIDOR
        try:
            servidor = _ServidorProvaMaps()
        except OSError as exc:
            raise ErroConfiguracaoServico("porta_local_maps_indisponivel") from exc
        thread = threading.Thread(
            target=servidor.serve_forever,
            name="kordena-google-maps-browser-proof",
            daemon=True,
        )
        thread.start()
        _SERVIDOR = servidor
        return servidor


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


def _pagina_prova(*, browser_key: str, evidencia: str) -> str:
    key_url = quote(browser_key, safe="")
    evidencia_html = html.escape(evidencia, quote=True)
    return f"""<!doctype html>
<html lang=\"pt-BR\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"referrer\" content=\"strict-origin-when-cross-origin\" />
  <meta http-equiv=\"Cache-Control\" content=\"no-store\" />
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
    window.gm_authFailure = function() {{
      fail('autenticacao/restricao da Browser API Key rejeitada pelo Google Maps.');
    }};
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
      }} catch (err) {{
        fail('nao foi possivel inicializar o mapa.');
      }}
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


def preparar_healthcheck_browser_google_maps(
    *,
    session: Session,
    secret_store: SecretStore,
    contexto: ContextoExecucao,
    evidencia_servidor: str,
    configuracao_id: str = "mapas--google_maps",
    agora: datetime | None = None,
) -> PreparacaoHealthcheckBrowserMaps:
    """Prepara pagina HTTP local que so revela a evidencia apos ``tilesloaded``."""

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
    token = secrets.token_urlsafe(24)
    pagina = _pagina_prova(browser_key=browser_key, evidencia=evidencia)
    url = _servidor_local().registrar(token=token, html_doc=pagina)
    return PreparacaoHealthcheckBrowserMaps(url=url, evidencia_ref=evidencia)
