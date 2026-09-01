"""Adiciona/alinha healthcheck real somente leitura do Mercado Pago na UI administrativa."""

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
    if "executar_healthcheck_mercado_pago" not in texto:
        texto = _replace_once(
            texto,
            "from infra.integracoes.meta_healthcheck import executar_healthcheck_meta\n",
            "from infra.integracoes.meta_healthcheck import executar_healthcheck_meta\n"
            "from infra.integracoes.mercado_pago_healthcheck import executar_healthcheck_mercado_pago\n",
            "import_healthcheck_mp",
        )

    marcador_evidencia = '''        ultima_evidencia_meta = st.session_state.get(\n'''
    bloco_evidencia = '''        ultima_evidencia_mp = st.session_state.get(
            _key(spec, "last_real_mercado_pago_access_evidence")
        )
        if spec.provedor == "mercado_pago" and ultima_evidencia_mp:
            st.success(
                "Access Token do Mercado Pago validado externamente em modo somente leitura."
            )
            st.code(str(ultima_evidencia_mp), language=None)
            st.caption(
                "Esta evidência confirma autenticação da credencial sem criar pagamento. A capacidade PIX será comprovada pela Order sandbox controlada, com QR Code, consulta de status e webhook."
            )
'''
    if "last_real_mercado_pago_access_evidence" not in texto:
        texto = _replace_once(
            texto,
            marcador_evidencia,
            bloco_evidencia + marcador_evidencia,
            "evidencia_mp",
        )

    marcador_acao = '''        if spec.provedor == "meta" and existing is not None:\n'''
    bloco_acao = '''        if spec.provedor == "mercado_pago" and existing is not None:
            st.caption(
                "Este healthcheck valida de verdade o Access Token salvo no cofre por uma chamada autenticada somente leitura. Não cria PIX, não cobra ninguém e não homologa automaticamente; o PIX será comprovado pela Order sandbox controlada."
            )
            if st.button(
                "Testar acesso real Mercado Pago (sem criar pagamento)",
                key=_key(spec, "real_mercado_pago_access_healthcheck"),
            ):
                pin_ok = _critical_pin_ok(
                    identidade=identidade,
                    pin=critical_pin,
                    session_factory=session_factory,
                )
                _consume_sensitive_inputs(spec)
                if not pin_ok:
                    _set_flash(
                        spec,
                        "error",
                        "PIN administrativo inválido. O healthcheck externo do Mercado Pago não foi executado.",
                    )
                    st.rerun()
                try:
                    resultado = executar_healthcheck_mercado_pago(
                        session=session,
                        secret_store=vault,
                        contexto=contexto,
                        configuracao_id=config_id,
                    )
                    st.session_state[
                        _key(spec, "last_real_mercado_pago_access_evidence")
                    ] = resultado.evidencia_ref
                    _set_flash(
                        spec,
                        "success",
                        "Mercado Pago aceitou o Access Token salvo no cofre. Nenhum pagamento foi criado. A prova PIX transacional sandbox continua pendente.",
                    )
                    st.rerun()
                except Exception:
                    _set_flash(
                        spec,
                        "error",
                        "O healthcheck externo do Mercado Pago falhou. A integração continua não homologada; revise ambiente e Access Token. Nenhum segredo foi exposto e nenhum pagamento foi criado.",
                    )
                    st.rerun()

'''
    if "Testar acesso real Mercado Pago (sem criar pagamento)" not in texto:
        texto = _replace_once(
            texto,
            marcador_acao,
            bloco_acao + marcador_acao,
            "acao_mp",
        )

    substituicoes = (
        (
            "Acesso externo Mercado Pago e disponibilidade de PIX validados em modo somente leitura.",
            "Access Token do Mercado Pago validado externamente em modo somente leitura.",
            "evidencia_texto",
        ),
        (
            "Esta evidência não criou pagamento nem movimentou dinheiro. A homologação final ainda exige criar um PIX controlado em ambiente de teste e validar status/webhook.",
            "Esta evidência confirma autenticação da credencial sem criar pagamento. A capacidade PIX será comprovada pela Order sandbox controlada, com QR Code, consulta de status e webhook.",
            "evidencia_caption",
        ),
        (
            "Este healthcheck consulta de verdade os meios de pagamento disponíveis usando o Access Token salvo no cofre. É somente leitura: não cria PIX, não cobra ninguém e não homologa automaticamente.",
            "Este healthcheck valida de verdade o Access Token salvo no cofre por uma chamada autenticada somente leitura. Não cria PIX, não cobra ninguém e não homologa automaticamente; o PIX será comprovado pela Order sandbox controlada.",
            "acao_caption",
        ),
        (
            "Mercado Pago respondeu com sucesso e o PIX está disponível para a credencial configurada. Nenhum pagamento foi criado. A prova transacional controlada continua pendente.",
            "Mercado Pago aceitou o Access Token salvo no cofre. Nenhum pagamento foi criado. A prova PIX transacional sandbox continua pendente.",
            "acao_sucesso",
        ),
        (
            "O healthcheck externo do Mercado Pago falhou. A integração continua não homologada; revise ambiente, Access Token e disponibilidade do PIX. Nenhum segredo foi exposto e nenhum pagamento foi criado.",
            "O healthcheck externo do Mercado Pago falhou. A integração continua não homologada; revise ambiente e Access Token. Nenhum segredo foi exposto e nenhum pagamento foi criado.",
            "acao_erro",
        ),
    )
    for antigo, novo, rotulo in substituicoes:
        if antigo in texto:
            texto = _replace_once(texto, antigo, novo, rotulo)

    return texto


def main() -> None:
    original = TARGET.read_text(encoding="utf-8")
    atualizado = aplicar(original)
    if atualizado == original:
        print("UI ja contem o healthcheck Mercado Pago alinhado; nenhuma alteracao necessaria.")
        return
    TARGET.write_text(atualizado, encoding="utf-8")
    print("UI alinhada: healthcheck Mercado Pago valida credencial; prova PIX permanece transacional sandbox.")


if __name__ == "__main__":
    main()
