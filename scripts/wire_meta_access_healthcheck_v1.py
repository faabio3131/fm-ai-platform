"""Adiciona healthcheck Meta somente leitura à UI administrativa."""

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
        "executar_healthcheck_meta" in texto
        and "Testar acesso real Meta (somente leitura)" in texto
        and "last_real_meta_access_evidence" in texto
    ):
        return texto

    texto = _replace_once(
        texto,
        "from infra.integracoes.google_maps_healthcheck import executar_healthcheck_google_maps\n",
        "from infra.integracoes.google_maps_healthcheck import executar_healthcheck_google_maps\n"
        "from infra.integracoes.meta_healthcheck import executar_healthcheck_meta\n",
        "import_meta_healthcheck",
    )

    marcador_evidencia = '''        st.caption(\n            "O status Ativo só deve ser registrado após validação real do provedor. "\n'''
    bloco_evidencia = '''        ultima_evidencia_meta = st.session_state.get(\n            _key(spec, "last_real_meta_access_evidence")\n        )\n        if spec.provedor == "meta" and ultima_evidencia_meta:\n            st.success(\n                "Acesso externo Meta validado em modo somente leitura para o recurso configurado."\n            )\n            st.code(str(ultima_evidencia_meta), language=None)\n            st.caption(\n                "Esta evidência comprova autenticação e acesso ao ativo Meta. A homologação final ainda exige a prova prática específica do serviço: publicação controlada no Facebook/Instagram ou envio/webhook real no WhatsApp."\n            )\n'''
    texto = _replace_once(
        texto,
        marcador_evidencia,
        bloco_evidencia + marcador_evidencia,
        "evidencia_meta",
    )

    marcador_acao = '''        if spec.provedor == "google_maps" and existing is not None:\n            st.caption(\n                "O teste abaixo chama de verdade a Geocoding API e a Routes API usando somente a Server API Key salva no cofre. "\n'''
    bloco_acao = '''        if spec.provedor == "meta" and existing is not None:\n            st.caption(\n                "Este healthcheck faz uma chamada real e somente leitura à Graph API usando o Access Token e o App Secret salvos no cofre. Ele valida o ativo configurado sem publicar, enviar mensagem ou alterar dados externos."\n            )\n            if st.button(\n                "Testar acesso real Meta (somente leitura)",\n                key=_key(spec, "real_meta_access_healthcheck"),\n            ):\n                pin_ok = _critical_pin_ok(\n                    identidade=identidade,\n                    pin=critical_pin,\n                    session_factory=session_factory,\n                )\n                _consume_sensitive_inputs(spec)\n                if not pin_ok:\n                    _set_flash(\n                        spec,\n                        "error",\n                        "PIN administrativo inválido. O healthcheck externo Meta não foi executado.",\n                    )\n                    st.rerun()\n                try:\n                    resultado = executar_healthcheck_meta(\n                        session=session,\n                        secret_store=vault,\n                        contexto=contexto,\n                        configuracao_id=config_id,\n                    )\n                    st.session_state[_key(spec, "last_real_meta_access_evidence")] = (\n                        resultado.evidencia_ref\n                    )\n                    _set_flash(\n                        spec,\n                        "success",\n                        "Acesso externo Meta validado com sucesso em modo somente leitura. Nenhuma publicação, mensagem ou alteração foi feita. A prova prática específica do serviço continua pendente antes da homologação final.",\n                    )\n                    st.rerun()\n                except Exception:\n                    _set_flash(\n                        spec,\n                        "error",\n                        "O healthcheck externo Meta falhou. A integração continua não homologada; revise o recurso configurado, permissões, token, App Secret e versão da Graph API. Nenhum segredo foi exposto.",\n                    )\n                    st.rerun()\n\n'''
    texto = _replace_once(
        texto,
        marcador_acao,
        bloco_acao + marcador_acao,
        "acao_meta",
    )
    return texto


def main() -> None:
    original = TARGET.read_text(encoding="utf-8")
    atualizado = aplicar(original)
    if atualizado == original:
        print("UI ja contem o healthcheck Meta somente leitura; nenhuma alteracao necessaria.")
        return
    TARGET.write_text(atualizado, encoding="utf-8")
    print("UI atualizada com healthcheck Meta somente leitura pre-homologacao.")


if __name__ == "__main__":
    main()
