"""Aplica wiring idempotente da persistência Pix V1 no PDV comercial.

Uso local controlado:
    python -m scripts.wire_pix_pdv_durability_v1

O script só altera app.py quando encontra exatamente o contrato esperado da branch.
Se o arquivo divergir, falha fechado sem gravar conteúdo parcial.
"""

from __future__ import annotations

from pathlib import Path

APP = Path("app.py")


def _replace_once(texto: str, antigo: str, novo: str, rotulo: str) -> str:
    quantidade = texto.count(antigo)
    if quantidade == 0 and novo in texto:
        return texto
    if quantidade != 1:
        raise RuntimeError(f"patch_{rotulo}_esperava_1_encontrou_{quantidade}")
    return texto.replace(antigo, novo, 1)


def aplicar(texto: str) -> str:
    antigo_criar = '''        return criar_cobranca_pix_por_control_plane(\n            repositorio=repositorio,\n            fabrica=fabrica,\n            contexto=contexto,\n            pagamento_id=pagamento_id,\n            valor=Decimal(str(round(valor, 2))),\n            idempotency_key=idempotency_key,\n            pagador=DadosPagadorPix(\n                nome=nome_pagador,\n                email=email_pagador,\n                documento=documento_pagador,\n            ),\n        )\n'''
    novo_criar = '''        valor_decimal = Decimal(str(round(valor, 2)))\n        cobranca = criar_cobranca_pix_por_control_plane(\n            repositorio=repositorio,\n            fabrica=fabrica,\n            contexto=contexto,\n            pagamento_id=pagamento_id,\n            valor=valor_decimal,\n            idempotency_key=idempotency_key,\n            pagador=DadosPagadorPix(\n                nome=nome_pagador,\n                email=email_pagador,\n                documento=documento_pagador,\n            ),\n        )\n\n        from infra.integracoes.pix_durabilidade import registrar_vinculo_cobranca_pix\n\n        registrar_vinculo_cobranca_pix(\n            session=db,\n            contexto=contexto,\n            pagamento_id=pagamento_id,\n            pedido_id=pedido_id,\n            valor=valor_decimal,\n            provedor=cobranca.provedor,\n            id_externo=cobranca.id_externo,\n            idempotency_key=f"{idempotency_key}:vinculo",\n            terminal_id=terminal_id,\n            assinatura_checkout=assinatura_checkout,\n        )\n        return cobranca\n'''
    texto = _replace_once(texto, antigo_criar, novo_criar, "criar")

    antigo_assinatura_criar = '''def _criar_pix_control_plane(\n    *,\n    pagamento_id: str,\n    valor: float,\n    idempotency_key: str,\n    nome_pagador: str,\n    email_pagador: str,\n    documento_pagador: str,\n):\n'''
    novo_assinatura_criar = '''def _criar_pix_control_plane(\n    *,\n    pagamento_id: str,\n    pedido_id: str,\n    valor: float,\n    idempotency_key: str,\n    nome_pagador: str,\n    email_pagador: str,\n    documento_pagador: str,\n    terminal_id: str,\n    assinatura_checkout: str,\n):\n'''
    texto = _replace_once(
        texto, antigo_assinatura_criar, novo_assinatura_criar, "assinatura_criar"
    )

    antigo_consultar = '''        return consultar_cobranca_pix_por_control_plane(\n            repositorio=repositorio,\n            fabrica=fabrica,\n            contexto=contexto,\n            provedor=provedor,\n            id_externo=id_externo,\n        )\n    finally:\n        db.close()\n\n\ndef _pix_status_confirmado(status: str) -> bool:\n'''
    novo_consultar = '''        cobranca = consultar_cobranca_pix_por_control_plane(\n            repositorio=repositorio,\n            fabrica=fabrica,\n            contexto=contexto,\n            provedor=provedor,\n            id_externo=id_externo,\n        )\n        if pagamento_id:\n            from infra.integracoes.pix_durabilidade import (\n                confirmar_cobranca_pix_consultada,\n            )\n\n            confirmar_cobranca_pix_consultada(\n                session=db,\n                contexto=contexto,\n                pagamento_id=pagamento_id,\n                cobranca=cobranca,\n            )\n        return cobranca\n    finally:\n        db.close()\n\n\ndef _recuperar_pix_control_plane(*, terminal_id: str, assinatura_checkout: str):\n    db = SessionLocal()\n    try:\n        from infra.integracoes.pix_durabilidade import recuperar_pix_aberto_por_terminal\n\n        return recuperar_pix_aberto_por_terminal(\n            session=db,\n            contexto=CURRENT_IDENTITY.contexto(origem="app.pdv.pix_recovery"),\n            terminal_id=terminal_id,\n            assinatura_checkout=assinatura_checkout,\n        )\n    finally:\n        db.close()\n\n\ndef _pix_status_confirmado(status: str) -> bool:\n'''
    texto = _replace_once(texto, antigo_consultar, novo_consultar, "consultar")
    texto = _replace_once(
        texto,
        'def _consultar_pix_control_plane(*, provedor: str, id_externo: str):\n',
        'def _consultar_pix_control_plane(\n    *, provedor: str, id_externo: str, pagamento_id: str | None = None\n):\n',
        "assinatura_consultar",
    )

    antigo_assinatura = '''                checkout_id_pix = st.session_state["pdv_checkout_id"]\n                assinatura_pix = (\n                    f"{checkout_id_pix}:{getattr(prod_pdv, 'id', '')}:"\n                    f"{qtd_pdv}:{cliente_id_pdv}:{total_final_pdv:.2f}"\n                )\n'''
    novo_assinatura = '''                checkout_id_pix = st.session_state["pdv_checkout_id"]\n                terminal_pix_pdv = os.getenv("FM_AI_TEST_TERMINAL", "pdv-default")\n                assinatura_checkout_duravel = (\n                    f"{getattr(prod_pdv, 'id', '')}:"\n                    f"{qtd_pdv}:{cliente_id_pdv}:{total_final_pdv:.2f}"\n                )\n                assinatura_pix = (\n                    f"{checkout_id_pix}:{assinatura_checkout_duravel}"\n                )\n'''
    texto = _replace_once(texto, antigo_assinatura, novo_assinatura, "assinatura_checkout")

    marcador_recuperacao = '''                if motivo_dados:\n                    st.info(motivo_dados)\n\n                tem_cobranca_pix = bool(\n                    st.session_state.get("pdv_pix_id_externo")\n                )\n'''
    bloco_recuperacao = '''                if motivo_dados:\n                    st.info(motivo_dados)\n\n                if not st.session_state.get("pdv_pix_id_externo"):\n                    try:\n                        vinculo_pix = _recuperar_pix_control_plane(\n                            terminal_id=terminal_pix_pdv,\n                            assinatura_checkout=assinatura_checkout_duravel,\n                        )\n                        if vinculo_pix is not None:\n                            st.session_state["pdv_pix_provedor"] = vinculo_pix.provedor\n                            st.session_state["pdv_pix_id_externo"] = vinculo_pix.id_externo\n                            st.session_state["pdv_pix_pagamento_id"] = vinculo_pix.pagamento_id\n                            if vinculo_pix.pagamento_id.startswith("pdv-"):\n                                st.session_state["pdv_checkout_id"] = vinculo_pix.pagamento_id[4:]\n                            consulta_recuperada = _consultar_pix_control_plane(\n                                provedor=vinculo_pix.provedor,\n                                id_externo=vinculo_pix.id_externo,\n                                pagamento_id=vinculo_pix.pagamento_id,\n                            )\n                            st.session_state["pdv_pix_status"] = consulta_recuperada.status\n                            st.session_state["pdv_pix_copia_cola"] = consulta_recuperada.pix_copia_cola\n                            st.session_state["pdv_pix_qr_url"] = consulta_recuperada.qr_code_url\n                            st.session_state["pdv_pix_qr_base64"] = consulta_recuperada.qr_code_base64\n                            st.session_state["pdv_pix_confirmado"] = _pix_status_confirmado(\n                                consulta_recuperada.status\n                            )\n                    except Exception:\n                        # Recuperação é best-effort; uma falha de consulta nunca confirma Pix.\n                        pass\n\n                tem_cobranca_pix = bool(\n                    st.session_state.get("pdv_pix_id_externo")\n                )\n'''
    texto = _replace_once(
        texto, marcador_recuperacao, bloco_recuperacao, "recuperacao_pdv"
    )

    antigo_chamada_criar = '''                            cobranca_pix = _criar_pix_control_plane(\n                                pagamento_id=f"pdv-{checkout_id_pix}",\n                                valor=float(total_final_pdv),\n                                idempotency_key=f"pdv-pix-{checkout_id_pix}",\n                                nome_pagador=nome_pagador,\n                                email_pagador=email_pagador,\n                                documento_pagador=documento_pagador,\n                            )\n'''
    novo_chamada_criar = '''                            pagamento_id_pix = f"pdv-{checkout_id_pix}"\n                            cobranca_pix = _criar_pix_control_plane(\n                                pagamento_id=pagamento_id_pix,\n                                pedido_id=checkout_id_pix,\n                                valor=float(total_final_pdv),\n                                idempotency_key=f"pdv-pix-{checkout_id_pix}",\n                                nome_pagador=nome_pagador,\n                                email_pagador=email_pagador,\n                                documento_pagador=documento_pagador,\n                                terminal_id=terminal_pix_pdv,\n                                assinatura_checkout=assinatura_checkout_duravel,\n                            )\n                            st.session_state["pdv_pix_pagamento_id"] = pagamento_id_pix\n'''
    texto = _replace_once(texto, antigo_chamada_criar, novo_chamada_criar, "chamada_criar")

    antigo_chamada_consulta = '''                                consulta_pix = _consultar_pix_control_plane(\n                                    provedor=str(\n                                        st.session_state["pdv_pix_provedor"]\n                                    ),\n                                    id_externo=str(\n                                        st.session_state["pdv_pix_id_externo"]\n                                    ),\n                                )\n'''
    novo_chamada_consulta = '''                                consulta_pix = _consultar_pix_control_plane(\n                                    provedor=str(\n                                        st.session_state["pdv_pix_provedor"]\n                                    ),\n                                    id_externo=str(\n                                        st.session_state["pdv_pix_id_externo"]\n                                    ),\n                                    pagamento_id=str(\n                                        st.session_state.get(\n                                            "pdv_pix_pagamento_id",\n                                            f"pdv-{st.session_state['pdv_checkout_id']}",\n                                        )\n                                    ),\n                                )\n'''
    texto = _replace_once(
        texto, antigo_chamada_consulta, novo_chamada_consulta, "chamada_consulta"
    )

    texto = _replace_once(
        texto,
        '''                        "pdv_pix_confirmado",\n                    ):\n''',
        '''                        "pdv_pix_confirmado",\n                        "pdv_pix_pagamento_id",\n                    ):\n''',
        "limpeza_estado",
    )

    return texto


def main() -> None:
    original = APP.read_text(encoding="utf-8")
    atualizado = aplicar(original)
    if atualizado == original:
        print("app.py já contém o wiring durável do Pix; nenhuma alteração necessária.")
        return
    APP.write_text(atualizado, encoding="utf-8")
    print("app.py atualizado com wiring durável do Pix V1.")


if __name__ == "__main__":
    main()
