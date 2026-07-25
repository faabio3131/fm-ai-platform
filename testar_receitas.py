from core.database import SessionLocal, Insumo, Produto, FichaTecnica

def criar_ficha_tecnica_teste():
    db = SessionLocal()
    try:
        # 1. Verificar se o "MicaBurger Clássico" já existe no banco
        produto = db.query(Produto).filter_by(nome="MicaBurger Clássico + Fritas").first()
        if not produto:
            produto = Produto(nome="MicaBurger Clássico + Fritas", preco_venda=35.00, categoria="Combos")
            db.add(produto)
            db.commit()
            db.refresh(produto)
            print(f"🍔 Produto cadastrado: {produto.nome} | Preço de Venda: R$ {produto.preco_venda:.2f}")

            # 2. Buscar os IDs dos insumos que já foram criados na Camada 1
            carne = db.query(Insumo).filter_by(nome="Contrafilé Bovino").first()
            queijo = db.query(Insumo).filter_by(nome="Queijo Mussarela").first()
            batata = db.query(Insumo).filter_by(nome="Batata Palito Congelada").first()
            embalagem = db.query(Insumo).filter_by(nome="Embalagem Térmica G").first()

            # 3. Montar a Ficha Técnica (A Receita Oficial do Combo)
            receita = [
                FichaTecnica(produto_id=produto.id, insumo_id=carne.id, quantidade_gasta=0.180),  # 180g de carne
                FichaTecnica(produto_id=produto.id, insumo_id=queijo.id, quantidade_gasta=0.040), # 40g de queijo
                FichaTecnica(produto_id=produto.id, insumo_id=batata.id, quantidade_gasta=0.150), # 150g de batata
                FichaTecnica(produto_id=produto.id, insumo_id=embalagem.id, quantidade_gasta=1.0) # 1 embalagem
            ]
            
            db.add_all(receita)
            db.commit()
            print("📋 Ficha Técnica vinculada aos insumos com sucesso!\n")
        else:
            print("👉 O produto MicaBurger Clássico já estava cadastrado.\n")

        # 4. CALCULAR O CUSTO DA RECEITA E A MARGEM DE LUCRO (A inteligência da Camada 2)
        print("--- 📊 ANÁLISE DE CUSTO DA FICHA TÉCNICA ---")
        custo_total = 0.0
        
        for item in produto.ingredientes:
            custo_item = item.quantidade_gasta * item.insumo.custo_unitario
            custo_total += custo_item
            print(f"• {item.insumo.nome:<24} | Uso: {item.quantidade_gasta:>5} {item.insumo.unidade_medida} | Custo: R$ {custo_item:.2f}")
            
        margem_lucro = ((produto.preco_venda - custo_total) / produto.preco_venda) * 100
        lucro_bruto = produto.preco_venda - custo_total

        print("-" * 50)
        print(f"💰 CUSTO TOTAL DOS INSUMOS: R$ {custo_total:.2f}")
        print(f"🏷️  PREÇO NO CARDÁPIO:      R$ {produto.preco_venda:.2f}")
        print(f"📈 LUCRO BRUTO POR LANCHE:  R$ {lucro_bruto:.2f} (Margem: {margem_lucro:.1f}%)")
        print("-" * 50)

    except Exception as e:
        db.rollback()
        print(f"❌ Erro ao gerar ficha técnica: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    criar_ficha_tecnica_teste()