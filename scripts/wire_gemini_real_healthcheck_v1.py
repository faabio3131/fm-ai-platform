"""Adiciona à UI administrativa o healthcheck Gemini real pré-homologação."""

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
    # Se os três marcadores canônicos já existem, a UI já está integralmente
    # conectada. Retornar imediatamente evita duplicar o import em uma segunda
    # execução do patch, pois o bloco antigo de imports continua contido no novo.
    if (
        "from infra.integracoes.gemini_healthcheck import executar_healthcheck_gemini"
        in texto
        and "last_real_healthcheck_evidence" in texto
        and "Testar Gemini real antes de homologar" in texto
    ):
        return texto

    texto = _replace_once(
        texto,
        '''from infra.integracoes.repositorio_sqlalchemy import (\n    ProntidaoCredenciaisSQLAlchemy,\n    RepositorioConfiguracoesExternasSQLAlchemy,\n)\n''',
        '''from infra.integracoes.gemini_healthcheck import executar_healthcheck_gemini\nfrom infra.integracoes.repositorio_sqlalchemy import (\n    ProntidaoCredenciaisSQLAlchemy,\n    RepositorioConfiguracoesExternasSQLAlchemy,\n)\n''',
        "import_healthcheck",
    )

    texto = _replace_once(
        texto,
        '''        st.markdown("**Homologação**")\n        st.caption(\n''',
        '''        st.markdown("**Homologação**")\n        ultima_evidencia_real = st.session_state.get(\n            _key(spec, "last_real_healthcheck_evidence")\n        )\n        if spec.provedor == "gemini" and ultima_evidencia_real:\n            st.success("Último healthcheck externo real do Gemini concluído com sucesso.")\n            st.code(str(ultima_evidencia_real), language=None)\n            st.caption(\n                "Copie esta referência para o campo de evidência abaixo. Ela não contém a API key nem conteúdo sensível."\n            )\n        st.caption(\n''',
        "mostra_evidencia_real",
    )

    texto = _replace_once(
        texto,
        '''        c_save, c_validate, c_homolog = st.columns(3)\n''',
        '''        if spec.provedor == "gemini" and existing is not None:\n            st.caption(\n                "O teste abaixo faz uma chamada mínima real ao Google Gemini usando somente a credencial já salva no cofre. "\n                "Ele valida o modelo configurado, gera uma referência sanitizada e não homologa automaticamente."\n            )\n            if st.button(\n                "Testar Gemini real antes de homologar",\n                key=_key(spec, "real_healthcheck"),\n            ):\n                pin_ok = _critical_pin_ok(\n                    identidade=identidade,\n                    pin=critical_pin,\n                    session_factory=session_factory,\n                )\n                _consume_sensitive_inputs(spec)\n                if not pin_ok:\n                    _set_flash(\n                        spec,\n                        "error",\n                        "PIN administrativo inválido. O healthcheck externo não foi executado.",\n                    )\n                    st.rerun()\n                try:\n                    resultado = executar_healthcheck_gemini(\n                        session=session,\n                        secret_store=vault,\n                        contexto=contexto,\n                        configuracao_id=config_id,\n                    )\n                    st.session_state[_key(spec, "last_real_healthcheck_evidence")] = (\n                        resultado.evidencia_ref\n                    )\n                    _set_flash(\n                        spec,\n                        "success",\n                        f"Healthcheck externo real concluído com sucesso usando o modelo {resultado.model}. "\n                        "A referência sanitizada foi gerada abaixo para a homologação.",\n                    )\n                    st.rerun()\n                except Exception:\n                    _set_flash(\n                        spec,\n                        "error",\n                        "O healthcheck externo real do Gemini falhou. A integração continua não homologada; revise o modelo, a credencial e a disponibilidade da conta. Nenhum segredo foi exposto.",\n                    )\n                    st.rerun()\n\n        c_save, c_validate, c_homolog = st.columns(3)\n''',
        "botao_healthcheck",
    )
    return texto


def main() -> None:
    original = TARGET.read_text(encoding="utf-8")
    atualizado = aplicar(original)
    if atualizado == original:
        print("UI já contém o healthcheck real do Gemini; nenhuma alteração necessária.")
        return
    TARGET.write_text(atualizado, encoding="utf-8")
    print("UI atualizada com healthcheck real do Gemini pré-homologação.")


if __name__ == "__main__":
    main()
