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
    texto = texto.replace(
        "components.html(preparacao.html, height=430, scrolling=False)",
        "components.iframe(preparacao.url, height=520, scrolling=False)",
    )
    texto = texto.replace(
        "components.iframe(preparacao.url, height=430, scrolling=False)",
        "components.iframe(preparacao.url, height=520, scrolling=False)",
    )

    import_antigo = (
        "from infra.integracoes.google_maps_browser_healthcheck import "
        "preparar_healthcheck_browser_google_maps\n"
    )
    import_novo = '''from infra.integracoes.google_maps_browser_healthcheck import (
    obter_evidencia_confirmada_google_maps,
    preparar_healthcheck_browser_google_maps,
)
'''
    if import_antigo in texto:
        texto = texto.replace(import_antigo, import_novo, 1)

    if "obter_evidencia_confirmada_google_maps" not in texto:
        texto = _replace_once(
            texto,
            "from infra.integracoes.google_maps_healthcheck import executar_healthcheck_google_maps\n",
            import_novo
            + "from infra.integracoes.google_maps_healthcheck import executar_healthcheck_google_maps\n",
            "import_browser_healthcheck",
        )

    campo_antigo = '''        evidence_ref = st.text_input(
            "Referência da evidência de homologação",
            value="",
            max_chars=512,
            placeholder="Ex.: healthcheck://meta/2026-08-17/resultado-123",
            key=_key(spec, "homolog_evidence_ref"),
        )
'''
    campo_novo = '''        evidence_key = _key(spec, "homolog_evidence_ref")
        if spec.provedor == "google_maps":
            prefill_key = _key(spec, "maps_full_evidence_prefill")
            prefill = st.session_state.pop(prefill_key, None)
            if prefill and not str(st.session_state.get(evidence_key) or "").strip():
                st.session_state[evidence_key] = str(prefill)

            token_pendente = str(
                st.session_state.get(_key(spec, "maps_browser_proof_token")) or ""
            )
            evidencia_confirmada = obter_evidencia_confirmada_google_maps(token_pendente)
            if evidencia_confirmada:
                st.session_state[_key(spec, "last_real_maps_full_healthcheck_evidence")] = (
                    evidencia_confirmada
                )
                if not str(st.session_state.get(evidence_key) or "").strip():
                    st.session_state[evidence_key] = evidencia_confirmada
                st.session_state.pop(_key(spec, "maps_browser_proof_token"), None)

            evidencia_full = st.session_state.get(
                _key(spec, "last_real_maps_full_healthcheck_evidence")
            )
            if evidencia_full:
                st.success(
                    "Prova completa do Google Maps confirmada: servidor + Maps JavaScript API no navegador."
                )
                st.code(str(evidencia_full), language=None)
                st.caption(
                    "A referência foi preenchida automaticamente no campo de homologação abaixo."
                )

        evidence_ref = st.text_input(
            "Referência da evidência de homologação",
            value="",
            max_chars=512,
            placeholder="Ex.: healthcheck://meta/2026-08-17/resultado-123",
            key=evidence_key,
        )
'''
    if campo_antigo in texto:
        texto = texto.replace(campo_antigo, campo_novo, 1)

    trecho_preparacao = '''                    preparacao = preparar_healthcheck_browser_google_maps(
                        session=session,
                        secret_store=vault,
                        contexto=contexto,
                        configuracao_id=config_id,
                        evidencia_servidor=str(evidencia_servidor or ""),
                    )
                    st.info(
'''
    trecho_preparacao_novo = '''                    preparacao = preparar_healthcheck_browser_google_maps(
                        session=session,
                        secret_store=vault,
                        contexto=contexto,
                        configuracao_id=config_id,
                        evidencia_servidor=str(evidencia_servidor or ""),
                    )
                    st.session_state[_key(spec, "maps_browser_proof_token")] = preparacao.token
                    st.session_state.pop(
                        _key(spec, "last_real_maps_full_healthcheck_evidence"), None
                    )
                    st.info(
'''
    if trecho_preparacao in texto and "maps_browser_proof_token\")] = preparacao.token" not in texto:
        texto = texto.replace(trecho_preparacao, trecho_preparacao_novo, 1)

    texto = texto.replace(
        '"O mapa abaixo e a prova real da Browser API Key em http://localhost:8765. Se carregar e ficar verde, copie a evidencia final exibida dentro do proprio teste. "\n'
        '                        "Se o Google rejeitar a chave, a integracao continua nao homologada."',
        '"O mapa abaixo e a prova real da Browser API Key em http://localhost:8765. Quando ficar verde, a evidencia sera confirmada pelo servidor local. "\n'
        '                        "Use o botao Concluir teste logo abaixo; o campo de homologacao sera preenchido sem copiar manualmente."',
    )
    texto = texto.replace(
        '"O mapa abaixo e a prova real da Browser API Key. Se carregar e ficar verde, copie a evidencia final exibida dentro do proprio teste. "\n'
        '                        "Se o Google rejeitar a chave, o painel mostrara falha e a integracao continua nao homologada."',
        '"O mapa abaixo e a prova real da Browser API Key. Quando ficar verde, a evidencia sera confirmada pelo servidor local. "\n'
        '                        "Use o botao Concluir teste logo abaixo; o campo de homologacao sera preenchido sem copiar manualmente."',
    )

    marcador = '''        if spec.provedor == "gemini" and existing is not None:\n'''
    bloco_concluir = '''        if spec.provedor == "google_maps" and existing is not None:
            token_pendente = str(
                st.session_state.get(_key(spec, "maps_browser_proof_token")) or ""
            )
            if token_pendente:
                st.caption(
                    "Depois que o mapa ficar verde, conclua a prova para trazer a evidência ao painel automaticamente."
                )
                if st.button(
                    "Concluir teste e preencher evidência",
                    key=_key(spec, "confirm_maps_browser_healthcheck"),
                ):
                    evidencia_confirmada = obter_evidencia_confirmada_google_maps(
                        token_pendente
                    )
                    if evidencia_confirmada:
                        st.session_state[
                            _key(spec, "last_real_maps_full_healthcheck_evidence")
                        ] = evidencia_confirmada
                        st.session_state[
                            _key(spec, "maps_full_evidence_prefill")
                        ] = evidencia_confirmada
                        st.session_state.pop(
                            _key(spec, "maps_browser_proof_token"), None
                        )
                        _set_flash(
                            spec,
                            "success",
                            "Prova completa do Google Maps confirmada. A referência de homologação foi preenchida automaticamente.",
                        )
                        st.rerun()
                    else:
                        st.warning(
                            "A prova do navegador ainda não foi confirmada. Aguarde o mapa ficar verde e tente concluir novamente."
                        )

'''
    if "Concluir teste e preencher evidência" not in texto:
        texto = _replace_once(
            texto,
            marcador,
            bloco_concluir + marcador,
            "conclusao_browser_maps",
        )

    return texto


def main() -> None:
    original = TARGET.read_text(encoding="utf-8")
    atualizado = aplicar(original)
    if atualizado == original:
        print("UI ja contem a UX final do healthcheck browser do Google Maps; nenhuma alteracao necessaria.")
        return
    TARGET.write_text(atualizado, encoding="utf-8")
    print("UI atualizada: evidencia Google Maps visivel e preenchimento de homologacao assistido.")


if __name__ == "__main__":
    main()
