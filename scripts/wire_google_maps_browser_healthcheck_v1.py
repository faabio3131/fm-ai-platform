"""Adiciona prova real da Maps JavaScript API à UI administrativa."""

from __future__ import annotations

from pathlib import Path

TARGET = Path("infra/streamlit_app/integracoes_admin.py")


def _replace_once(texto: str, antigo: str, novo: str, rotulo: str) -> str:
    quantidade = texto.count(antigo)
    if quantidade == 0 and novo in texto:
        return texto
    if quantidade != 1:
        raise RuntimeError(f"patch_{rotulo}_esperava_1_encontrou_{quantidade}")
    return texto.replace(antigo, novo, 1)


def aplicar(texto: str) -> str:
    # Atualiza o wiring antigo baseado em components.html/srcdoc para a origem
    # HTTP local real. Isso corrige RefererNotAllowedMapError sem relaxar a key.
    texto = texto.replace(
        "components.html(preparacao.html, height=430, scrolling=False)",
        "components.iframe(preparacao.url, height=430, scrolling=False)",
    )

    if (
        "preparar_healthcheck_browser_google_maps" in texto
        and "Testar Google Maps real (navegador)" in texto
        and "components.iframe(preparacao.url" in texto
    ):
        return texto

    texto = _replace_once(
        texto,
        "import streamlit as st\n",
        "import streamlit as st\nimport streamlit.components.v1 as components\n",
        "import_components",
    )
    texto = _replace_once(
        texto,
        "from infra.integracoes.google_maps_healthcheck import executar_healthcheck_google_maps\n",
        "from infra.integracoes.google_maps_browser_healthcheck import preparar_healthcheck_browser_google_maps\nfrom infra.integracoes.google_maps_healthcheck import executar_healthcheck_google_maps\n",
        "import_browser_healthcheck",
    )

    marcador = '''        if spec.provedor == "gemini" and existing is not None:\n'''
    bloco = '''        if spec.provedor == "google_maps" and existing is not None:\n            evidencia_servidor = st.session_state.get(\n                _key(spec, "last_real_maps_server_healthcheck_evidence")\n            )\n            st.caption(\n                "Depois do teste servidor, valide aqui a Browser API Key carregando um mapa real pela Maps JavaScript API em uma origem HTTP local dedicada. "\n                "Para homologacao local, autorize http://localhost:8765/* na Browser API Key. A evidencia final so aparece se os tiles do mapa forem realmente carregados."\n            )\n            if st.button(\n                "Testar Google Maps real (navegador)",\n                key=_key(spec, "real_maps_browser_healthcheck"),\n                disabled=not bool(evidencia_servidor),\n            ):\n                pin_ok = _critical_pin_ok(\n                    identidade=identidade,\n                    pin=critical_pin,\n                    session_factory=session_factory,\n                )\n                _consume_sensitive_inputs(spec)\n                if not pin_ok:\n                    _set_flash(\n                        spec,\n                        "error",\n                        "PIN administrativo invalido. O teste real do navegador nao foi iniciado.",\n                    )\n                    st.rerun()\n                try:\n                    preparacao = preparar_healthcheck_browser_google_maps(\n                        session=session,\n                        secret_store=vault,\n                        contexto=contexto,\n                        configuracao_id=config_id,\n                        evidencia_servidor=str(evidencia_servidor or ""),\n                    )\n                    st.info(\n                        "O mapa abaixo e a prova real da Browser API Key em http://localhost:8765. Se carregar e ficar verde, copie a evidencia final exibida dentro do proprio teste. "\n                        "Se o Google rejeitar a chave, a integracao continua nao homologada."\n                    )\n                    components.iframe(preparacao.url, height=430, scrolling=False)\n                except Exception:\n                    st.error(\n                        "Nao foi possivel preparar o teste real do navegador. A integracao continua nao homologada; confirme a autorizacao de http://localhost:8765/* na Browser API Key e tente novamente. Nenhum segredo foi exposto."\n                    )\n\n'''
    texto = _replace_once(texto, marcador, bloco + marcador, "bloco_browser_maps")
    return texto


def main() -> None:
    original = TARGET.read_text(encoding="utf-8")
    atualizado = aplicar(original)
    if atualizado == original:
        print("UI ja contem o healthcheck browser do Google Maps em origem HTTP local; nenhuma alteracao necessaria.")
        return
    TARGET.write_text(atualizado, encoding="utf-8")
    print("UI atualizada para testar Maps JavaScript API em http://localhost:8765.")


if __name__ == "__main__":
    main()
