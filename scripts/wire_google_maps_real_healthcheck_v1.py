"""Adiciona à UI administrativa o healthcheck real de Google Maps pré-homologação."""

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
    if (
        "from infra.integracoes.google_maps_healthcheck import executar_healthcheck_google_maps"
        in texto
        and "last_real_maps_server_healthcheck_evidence" in texto
        and "Testar Google Maps real (servidor)" in texto
    ):
        return texto

    texto = _replace_once(
        texto,
        "from infra.integracoes.gemini_healthcheck import executar_healthcheck_gemini\n",
        "from infra.integracoes.gemini_healthcheck import executar_healthcheck_gemini\n"
        "from infra.integracoes.google_maps_healthcheck import executar_healthcheck_google_maps\n",
        "import_maps_healthcheck",
    )

    texto = _replace_once(
        texto,
        '''        if spec.provedor == "gemini" and ultima_evidencia_real:\n            st.success("Último healthcheck externo real do Gemini concluído com sucesso.")\n            st.code(str(ultima_evidencia_real), language=None)\n            st.caption(\n                "Copie esta referência para o campo de evidência abaixo. Ela não contém a API key nem conteúdo sensível."\n            )\n        st.caption(\n''',
        '''        if spec.provedor == "gemini" and ultima_evidencia_real:\n            st.success("Último healthcheck externo real do Gemini concluído com sucesso.")\n            st.code(str(ultima_evidencia_real), language=None)\n            st.caption(\n                "Copie esta referência para o campo de evidência abaixo. Ela não contém a API key nem conteúdo sensível."\n            )\n        ultima_evidencia_maps = st.session_state.get(\n            _key(spec, "last_real_maps_server_healthcheck_evidence")\n        )\n        if spec.provedor == "google_maps" and ultima_evidencia_maps:\n            st.success("Geocoding API e Routes API foram validadas externamente com a chave de servidor.")\n            st.code(str(ultima_evidencia_maps), language=None)\n            st.caption(\n                "Esta referência comprova somente o caminho servidor. A chave de navegador ainda precisa de prova real no navegador antes da homologação final."\n            )\n        st.caption(\n''',
        "mostra_maps_evidencia",
    )

    marcador = '''        if spec.provedor == "gemini" and existing is not None:\n'''
    bloco = '''        if spec.provedor == "google_maps" and existing is not None:\n            st.caption(\n                "O teste abaixo chama de verdade a Geocoding API e a Routes API usando somente a Server API Key salva no cofre. "\n                "Ele também confirma que a Browser API Key existe e pode ser resolvida, mas não a considera externamente homologada no navegador."\n            )\n            if st.button(\n                "Testar Google Maps real (servidor)",\n                key=_key(spec, "real_maps_server_healthcheck"),\n            ):\n                pin_ok = _critical_pin_ok(\n                    identidade=identidade,\n                    pin=critical_pin,\n                    session_factory=session_factory,\n                )\n                _consume_sensitive_inputs(spec)\n                if not pin_ok:\n                    _set_flash(\n                        spec,\n                        "error",\n                        "PIN administrativo inválido. O healthcheck externo do Google Maps não foi executado.",\n                    )\n                    st.rerun()\n                try:\n                    resultado = executar_healthcheck_google_maps(\n                        session=session,\n                        secret_store=vault,\n                        contexto=contexto,\n                        configuracao_id=config_id,\n                    )\n                    st.session_state[_key(spec, "last_real_maps_server_healthcheck_evidence")] = (\n                        resultado.evidencia_ref\n                    )\n                    _set_flash(\n                        spec,\n                        "success",\n                        f"Google Maps servidor validado de ponta a ponta: geocodificação + rota real, "\n                        f"{resultado.distancia_metros / 1000:.1f} km e ETA aproximado de "\n                        f"{max(1, (resultado.duracao_segundos + 59) // 60)} min. "\n                        "A chave de navegador ainda precisa de prova real no navegador antes da homologação final.",\n                    )\n                    st.rerun()\n                except Exception:\n                    _set_flash(\n                        spec,\n                        "error",\n                        "O healthcheck externo real do Google Maps falhou. A integração continua não homologada; revise habilitação das APIs, restrições das chaves e faturamento do projeto. Nenhum segredo foi exposto.",\n                    )\n                    st.rerun()\n\n'''
    texto = _replace_once(texto, marcador, bloco + marcador, "botao_maps_healthcheck")
    return texto


def main() -> None:
    original = TARGET.read_text(encoding="utf-8")
    atualizado = aplicar(original)
    if atualizado == original:
        print("UI já contém o healthcheck real do Google Maps; nenhuma alteração necessária.")
        return
    TARGET.write_text(atualizado, encoding="utf-8")
    print("UI atualizada com healthcheck real do Google Maps pré-homologação.")


if __name__ == "__main__":
    main()
