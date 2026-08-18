"""Aplica wiring idempotente de ``loja_id`` aos produtos criados pelo app V1.

O patch é deliberadamente estreito: mapeia a coluna de compatibilidade e garante que
novos produtos, tanto no cadastro manual quanto na importação Gemini, recebam a
unidade da identidade autenticada. Se o contrato esperado divergir, falha fechado.
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
    texto = _replace_once(
        texto,
        '''class Produto(Base):  # type: ignore[misc, valid-type]\n    __tablename__ = "produtos"\n    id = Column(Integer, primary_key=True, index=True)\n    nome = Column(String, index=True)\n''',
        '''class Produto(Base):  # type: ignore[misc, valid-type]\n    __tablename__ = "produtos"\n    id = Column(Integer, primary_key=True, index=True)\n    loja_id = Column(String(64), nullable=True, index=True)\n    nome = Column(String, index=True)\n''',
        "modelo_produto",
    )

    texto = _replace_once(
        texto,
        '''                novo_prod = Produto(\n                    nome=nome_produto,\n                    categoria=categoria,\n                    preco_venda=preco_venda_final,\n                    custo_total_cmv=cmv_total_calculado,\n                )\n''',
        '''                novo_prod = Produto(\n                    loja_id=CURRENT_IDENTITY.unidade_id,\n                    nome=nome_produto,\n                    categoria=categoria,\n                    preco_venda=preco_venda_final,\n                    custo_total_cmv=cmv_total_calculado,\n                )\n''',
        "cadastro_manual",
    )

    texto = _replace_once(
        texto,
        '''                        novo_prod = Produto(\n                            nome=prod.get("nome"),\n                            categoria=prod.get("categoria", "Geral"),\n                            preco_venda=float(prod.get("preco", 0)),\n                            custo_total_cmv=cmv_est,\n                            descricao_bruta=prod.get("ingredientes", ""),\n                        )\n''',
        '''                        novo_prod = Produto(\n                            loja_id=CURRENT_IDENTITY.unidade_id,\n                            nome=prod.get("nome"),\n                            categoria=prod.get("categoria", "Geral"),\n                            preco_venda=float(prod.get("preco", 0)),\n                            custo_total_cmv=cmv_est,\n                            descricao_bruta=prod.get("ingredientes", ""),\n                        )\n''',
        "importacao_gemini",
    )
    return texto


def main() -> None:
    original = APP.read_text(encoding="utf-8")
    atualizado = aplicar(original)
    if atualizado == original:
        print("app.py já contém o escopo de unidade dos produtos; nenhuma alteração necessária.")
        return
    APP.write_text(atualizado, encoding="utf-8")
    print("app.py atualizado para persistir loja_id da unidade autenticada nos produtos.")


if __name__ == "__main__":
    main()
