"""Prova real da Browser API Key do Google Maps sem homologacao automatica.

A Maps JavaScript API nao pode ser homologada de forma confiavel dentro de
``components.html`` do Streamlit porque esse componente usa ``about:srcdoc`` e o
Google enxerga um referenciador opaco. Este helper resolve a Browser API Key
escopada no cofre e registra uma pagina efemera em um servidor HTTP local,
bindado somente em 127.0.0.1. A pagina e carregada pelo navegador em
``http://localhost:8765/...`` e a evidencia so e confirmada depois de
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
    token: str


class _ServidorProvaMaps(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self) -> None:
        super().__init__((_LOCAL_HOST, _LOCAL_PORT), _HandlerProvaMaps)
        self.paginas: dict[str, str] = {}
        self.evidencias: dict[str, str] = {}
        self.confirmados: set[str] = set()
        self._lock = threading.Lock()

    def registrar(self, *, token: str, html_doc: str, evidencia_ref: str) -> str:
        path = f"/google-maps-proof/{token}"
        with self._lock:
            self.paginas[path] = html_doc
            self.evidencias[token] = evidencia_ref
            if len(self.paginas) > 12:
                antigos = tuple(self.paginas)[:-12]
                for antigo_path in antigos:
                    self.paginas.pop(antigo_path, None)
                    antigo_token = antigo_path.rsplit("/", 1)[-1]
                    self.evidencias.pop(antigo_token, None)
                    self.confirmados.discard(antigo_token)
        return f"http://{_LOCAL_PUBLIC_HOST}:{_LOCAL_PORT}{path}"

    def obter(self, path: str) -> str | None:
        with self._lock:
            return self.paginas.get(path)

    def marcar_sucesso(self, token: str) -> bool:
        with self._lock:
            if token not in self.evidencias:
                return False
            self.confirmados.add(token)
            return True

    def evidencia_confirmada(self, token: str) -> str | None:
        with self._lock:
            if token not in self.confirmados:
                return None
            return self.evidencias.get(token)


class _HandlerProvaMaps(BaseHTTPRequestHandler):
    server: _ServidorProvaMaps

    def _headers_no_store(self) -> None:
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")

    def do_GET(self) -> None:  # noqa: N802 - contrato BaseHTTPRequestHandler
        path = urlparse(self.path).path
        pagina = self.server.obter(path)
        if pagina is None:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self._headers_no_store()
            self.end_headers()
            self.wfile.write(b"Prova indisponivel.")
            return
        payload = pagina.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self._headers_no_store()
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self) -> None:  # noqa: N802 - contrato BaseHTTPRequestHandler
        path = urlparse(self.path).path
        prefixo = "/google-maps-proof/"
        sufixo = "/success"
        if not (path.startswith(prefixo) and path.endswith(sufixo)):
            self.send_response(404)
            self._headers_no_store()
            self.end_headers()
            return
        token = path[len(prefixo) : -len(sufixo)].strip("/")
        if not token or not self.server.marcar_sucesso(token):
            self.send_response(404)
            self._headers_no_store()
            self.end_headers()
            return
        self.send_response(204)
        self._headers_no_store()
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
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


def obter_evidencia_confirmada_google_maps(token: str) -> str | None:
    """Retorna evidencia somente depois que o navegador confirmou ``tilesloaded``."""

    if not token:
        return None
    with _SERVIDOR_LOCK:
        servidor = _SERVIDOR
    if servidor is None:
        return None
    return servidor.evidencia_confirmada(token)


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


def _pagina_prova(*, browser_key: str, evidencia: str, token: str) -> str:
    key_url = quote(browser_key, safe="")
    evidencia_html = html.escape(evidencia, quote=True)
    token_url = quote(token, safe="")
    return f"""<!doctype html>
<html lang=\"pt-BR\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"referrer\" content=\"strict-origin-when-cross-origin\" />
  <meta http-equiv=\"Cache-Control\" content=\"no-store\" />
  <style>
    body {{ margin: 0; font-family: Arial, sans-serif; background: #0e1117; color: #fafafa; }}
    #status {{ padding: 10px 12px; border-radius: 8px; margin-bottom: 8px; background: #3a2d0b; }}
    #map {{ width: 100%; height: 330px; border-radius: 10px; overflow: hidden; }}
    #evidence {{ display: none; margin-top: 10px; padding: 12px; border-radius: 8px; background: #123d2a; }}
    #evidence code {{ display: block; margin: 8px 0; padding: 9px; background: #0e1117; border-radius: 6px; word-break: break-all; user-select: all; }}
    #copy {{ border: 1px solid #7bdcb5; background: transparent; color: #fafafa; border-radius: 6px; padding: 7px 10px; cursor: pointer; }}
  </style>
  <script>
    let proved = false;
    function fail(message) {{
      document.getElementById('status').textContent = 'Falha no teste real do navegador: ' + message;
      document.getElementById('status').style.background = '#5b1d1d';
    }}
    async function confirmProof() {{
      const response = await fetch('/google-maps-proof/{token_url}/success', {{method: 'POST', cache: 'no-store'}});
      if (!response.ok) throw new Error('confirmacao_local_falhou');
    }}
    async function success() {{
      if (proved) return;
      try {{
        await confirmProof();
        proved = true;
        document.getElementById('status').textContent = 'Maps JavaScript API validada externamente no navegador. O mapa real carregou com sucesso.';
        document.getElementById('status').style.background = '#123d2a';
        document.getElementById('evidence').style.display = 'block';
      }} catch (_) {{
        fail('o mapa carregou, mas a confirmacao local da evidencia falhou.');
      }}
    }}
    async function copyEvidence() {{
      try {{
        await navigator.clipboard.writeText('{evidencia_html}');
        document.getElementById('copy').textContent = 'Copiado';
      }} catch (_) {{
        document.getElementById('copy').textContent = 'Selecione a evidencia acima';
      }}
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
        google.maps.event.addListenerOnce(map, 'tilesloaded', success);
      }} catch (_) {{
        fail('nao foi possivel inicializar o mapa.');
      }}
    }};
  </script>
</head>
<body>
  <div id=\"status\">Carregando Google Maps real no navegador...</div>
  <div id=\"map\"></div>
  <div id=\"evidence\">
    <strong>Evidencia final Google Maps</strong>
    <code>{evidencia_html}</code>
    <button id=\"copy\" type=\"button\" onclick=\"copyEvidence()\">Copiar evidencia</button>
  </div>
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
    """Prepara pagina HTTP local que confirma a evidencia apos ``tilesloaded``."""

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
    pagina = _pagina_prova(browser_key=browser_key, evidencia=evidencia, token=token)
    url = _servidor_local().registrar(
        token=token,
        html_doc=pagina,
        evidencia_ref=evidencia,
    )
    return PreparacaoHealthcheckBrowserMaps(
        url=url,
        evidencia_ref=evidencia,
        token=token,
    )
