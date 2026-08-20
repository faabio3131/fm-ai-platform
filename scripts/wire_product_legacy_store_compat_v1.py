"""Troca o wiring estático de ``loja_id`` pelo helper que reflete o schema real."""

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
    texto = _replace_once(
        texto,
        '    loja_id = Column(String(64), nullable=True, index=True)\n',
        '',
        "remove_mapeamento_loja_estatico",
    )

    texto = _replace_once(
        texto,
        '''                novo_prod = Produto(\n                    loja_id=CURRENT_IDENTITY.unidade_id,\n                    nome=nome_produto,\n                    categoria=categoria,\n                    preco_venda=preco_venda_final,\n                    custo_total_cmv=cmv_total_calculado,\n                )\n                db_session.add(novo_prod)\n                db_session.commit()\n\n                for item in st.session_state.itens_ficha_tecnica:\n                    nova_ft = FichaTecnica(\n                        produto_id=novo_prod.id,\n''',
        '''                from infra.legacy_product_scope import inserir_produto_legado\n\n                novo_prod_id = inserir_produto_legado(\n                    db_session,\n                    unidade_id=CURRENT_IDENTITY.unidade_id,\n                    valores={\n                        "nome": nome_produto,\n                        "categoria": categoria,\n                        "preco_venda": preco_venda_final,\n                        "custo_total_cmv": cmv_total_calculado,\n                    },\n                )\n                db_session.commit()\n\n                for item in st.session_state.itens_ficha_tecnica:\n                    nova_ft = FichaTecnica(\n                        produto_id=novo_prod_id,\n''',
        "cadastro_manual_refletido",
    )

    texto = _replace_once(
        texto,
        '''                        novo_prod = Produto(\n                            loja_id=CURRENT_IDENTITY.unidade_id,\n                            nome=prod.get("nome"),\n                            categoria=prod.get("categoria", "Geral"),\n                            preco_venda=float(prod.get("preco", 0)),\n                            custo_total_cmv=cmv_est,\n                            descricao_bruta=prod.get("ingredientes", ""),\n                        )\n                        db_session.add(novo_prod)\n                        qtd_cadastrados += 1\n''',
        '''                        from infra.legacy_product_scope import inserir_produto_legado\n\n                        inserir_produto_legado(\n                            db_session,\n                            unidade_id=CURRENT_IDENTITY.unidade_id,\n                            valores={\n                                "nome": prod.get("nome"),\n                                "categoria": prod.get("categoria", "Geral"),\n                                "preco_venda": float(prod.get("preco", 0)),\n                                "custo_total_cmv": cmv_est,\n                                "descricao_bruta": prod.get("ingredientes", ""),\n                            },\n                        )\n                        qtd_cadastrados += 1\n''',
        "importacao_gemini_refletida",
    )
    return texto


def main() -> None:
    original = APP.read_text(encoding="utf-8")
    atualizado = aplicar(original)
    if atualizado == original:
        print("app.py já usa compatibilidade refletida de loja; nenhuma alteração necessária.")
        return
    APP.write_text(atualizado, encoding="utf-8")
    print("app.py atualizado para respeitar o tipo real de produtos.loja_id.")


if __name__ == "__main__":
    main()
