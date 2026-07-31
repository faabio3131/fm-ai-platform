import re

with open("app.py", "r", encoding="utf-8") as f:
  conteudo = f.read()

nova_funcao = """def render_cadastro_ficha_tecnica(db_session, Insumo, Produto, FichaTecnica, client=None, GENAI_DISPONIVEL=False):
    st.subheader("👨‍🍳 Engenharia de Cardápio & Ficha Técnica Granular")
    
    modo = st.radio(
        "Escolha como deseja cadastrar:",
        ["✍️ Cadastro Manual", "🤖 Importação Automática via IA (Foto/PDF/Texto)"],
        horizontal=True
    )
    
    st.markdown("---")
    
    if modo == "✍️ Cadastro Manual":
        col_nome, col_cat = st.columns([2, 1])
        with col_nome:
            nome_produto = st.text_input("Nome do Produto / Prato", placeholder="Ex: Mica Royal Truffle Bacon")
        with col_cat:
            categoria = st.selectbox("Categoria", ["Hambúrgueres", "Porções", "Bebidas", "Sobremesas"])
            
        st.write("### 🥗 Composição da Ficha Técnica (Insumos do Almoxarifado)")
        insumos_disponiveis = db_session.query(Insumo).all()
        
        if not insumos_disponiveis:
            st.warning("⚠️ Nenhum insumo encontrado no Almoxarifado. Cadastre os insumos primeiro!")
            return
            
        if "itens_ficha_tecnica" not in st.session_state:
            st.session_state.itens_ficha_tecnica = []
            
        c1, c2, c3 = st.columns([3, 2, 1])
        with c1:
            insumo_selecionado = st.selectbox(
                "Selecione o Insumo",
                options=insumos_disponiveis,
                format_func=lambda x: f"{x.nome} (R$ {x.custo_unitario:.2f} / {x.unidade_medida})",
                key="sel_insumo"
            )
        with c2:
            label_qtd = "Quantidade em GRAMAS (g)" if insumo_selecionado.unidade_medida == "kg" else f"Quantidade ({insumo_selecionado.unidade_medida})"
            qtd_usada = st.number_input(label_qtd, min_value=0.1, value=100.0, step=10.0, key="num_qtd")
            
        with c3:
            st.write(" ")
            st.write(" ")
            if st.button("➕ Adicionar", use_container_width=True):
                custo_item = (qtd_usada / 1000.0) * insumo_selecionado.custo_unitario if insumo_selecionado.unidade_medida == "kg" else qtd_usada * insumo_selecionado.custo_unitario
                st.session_state.itens_ficha_tecnica.append({
                    "insumo_id": insumo_selecionado.id,
                    "nome": insumo_selecionado.nome,
                    "quantidade": qtd_usada,
                    "unidade": "g" if insumo_selecionado.unidade_medida == "kg" else insumo_selecionado.unidade_medida,
                    "custo_calculado": custo_item
                })
                st.rerun()
                
        cmv_total_calculado = 0.0
        if st.session_state.itens_ficha_tecnica:
            st.write("#### 📜 Receita Montada:")
            tabela_dados = []
            for item in st.session_state.itens_ficha_tecnica:
                cmv_total_calculado += item["custo_calculado"]
                tabela_dados.append({
                    "Item": item["nome"],
                    "Qtd na Receita": f"{item['quantidade']} {item['unidade']}",
                    "Custo Residual (R$)": f"R$ {item['custo_calculado']:.2f}"
                })
            st.table(tabela_dados)
            
            if st.button("🗑️ Limpar Receita"):
                st.session_state.itens_ficha_tecnica = []
                st.rerun()
                
        st.markdown("---")
        st.write("### 💰 Precificação Inteligente & Margem de Lucro Pretendida")
        col_cmv, col_margem, col_preco, col_lucro = st.columns(4)
        
        with col_cmv:
            st.metric("Custo de Produção (CMV)", f"R$ {cmv_total_calculado:.2f}")
            
        with col_margem:
            margem_pretendida = st.number_input("Margem Desejada (%)", min_value=5.0, max_value=300.0, value=60.0, step=5.0)
            
        preco_sugerido = (cmv_total_calculado / (1 - (margem_pretendida / 100.0))) if margem_pretendida < 100 else (cmv_total_calculado * (1 + (margem_pretendida / 100.0)))
        
        with col_preco:
            preco_venda_final = st.number_input("Preço de Venda Final (R$)", min_value=0.0, value=float(round(preco_sugerido, 2)), step=0.50)
            
        with col_lucro:
            margem_real = ((preco_venda_final - cmv_total_calculado) / preco_venda_final * 100) if preco_venda_final > 0 else 0
            st.metric("Lucro Bruto / Lanche", f"R$ {(preco_venda_final - cmv_total_calculado):.2f}", delta=f"{margem_real:.1f}% Margem Real")
            
        if st.button("💾 Salvar Produto & Ficha Técnica", type="primary"):
            if not nome_produto:
                st.error("❌ Digite o nome do produto.")
            elif not st.session_state.itens_ficha_tecnica:
                st.error("❌ Adicione pelo menos 1 insumo à ficha técnica.")
            else:
                novo_prod = Produto(
                    nome=nome_produto,
                    categoria=categoria,
                    preco=preco_venda_final,
                    custo_cmv=cmv_total_calculado,
                    margem_lucro=margem_real
                )
                db_session.add(novo_prod)
                db_session.commit()
                
                for item in st.session_state.itens_ficha_tecnica:
                    nova_ft = FichaTecnica(
                        produto_id=novo_prod.id,
                        insumo_id=item["insumo_id"],
                        quantidade_necessaria=item["quantidade"]
                    )
                    db_session.add(nova_ft)
                db_session.commit()
                
                st.success(f"✅ **{nome_produto}** cadastrado com sucesso!")
                st.session_state.itens_ficha_tecnica = []
                st.rerun()

    else:
        st.write("### 📄 Upload de Cardápio Real (Foto, PDF ou Colar Texto) via Gemini")
        st.caption("Carregue o arquivo com seu cardápio oficial que a IA extrairá todos os produtos e cadastrará no banco.")
        
        opcao_fonte = st.radio("Origem do arquivo:", ["📁 Upload de Arquivo (Imagem/PDF)", "📝 Colar Texto do Cardápio"], horizontal=True)
        
        texto_cardapio = ""
        arquivo_upload = None
        
        if opcao_fonte == "📁 Upload de Arquivo (Imagem/PDF)":
            arquivo_upload = st.file_uploader("Arraste a foto do cardápio ou PDF aqui", type=["png", "jpg", "jpeg", "pdf"])
        else:
            texto_cardapio = st.text_area("Cole aqui o texto do seu cardápio com nomes e preços:", height=150)
            
        if st.button("🚀 Processar Cardápio com IA", type="primary"):
            if not GENAI_DISPONIVEL or not client:
                st.error("❌ Integração com Google GenAI/Gemini não configurada no servidor.")
                return
                
            if not arquivo_upload and not texto_cardapio.strip():
                st.error("❌ Por favor, envie um arquivo ou cole o texto do cardápio.")
                return
                
            with st.spinner("🤖 O Gemini está analisando o cardápio real..."):
                try:
                    prompt = \"\"\"
                    Você é um especialista em ERP gastronômico. Analise o cardápio fornecido e extraia todos os produtos/itens cadastráveis.
                    Retorne EXATAMENTE um JSON no seguinte formato (sem formatação markdown ```json, apenas a string json pura):
                    [
                        {
                            "nome": "Nome do Lanche",
                            "categoria": "Hambúrgueres",
                            "preco": 39.90,
                            "ingredientes": "Descrição ou ingredientes brutos"
                        }
                    ]
                    \"\"\"
                    
                    if arquivo_upload:
                        bytes_data = arquivo_upload.getvalue()
                        mime = arquivo_upload.type
                        contents = [{'mime_type': mime, 'data': bytes_data}, prompt]
                        response = client.models.generate_content(model="gemini-2.5-flash", contents=contents)
                    else:
                        response = client.models.generate_content(model="gemini-2.5-flash", contents=f"{prompt}\\n\\n{texto_cardapio}")
                        
                    texto_limpo = response.text.strip().replace("```json", "").replace("```", "")
                    produtos_extraidos = json.loads(texto_limpo)
                    
                    qtd_cadastrados = 0
                    for prod in produtos_extraidos:
                        cmv_est = round(float(prod.get("preco", 0)) * 0.32, 2)
                        novo_prod = Produto(
                            nome=prod.get("nome"),
                            categoria=prod.get("categoria", "Geral"),
                            preco=float(prod.get("preco", 0)),
                            custo_cmv=cmv_est,
                            margem_lucro=68.0,
                            descricao_bruta=prod.get("ingredientes", "")
                        )
                        db_session.add(novo_prod)
                        qtd_cadastrados += 1
                        
                    db_session.commit()
                    st.success(f"🎉 Sucesso! **{qtd_cadastrados} produtos** foram extraídos pelo Gemini e salvos diretamente no cardápio!")
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"❌ Erro ao processar cardápio com IA: {e}")"""

padrao = r"def render_cadastro_ficha_tecnica\(.*?\):(.*?)(?=def executar_forecasting_e_alertar)"
conteudo_corrigido = re.sub(
    padrao, nova_funcao + "\n\n\n", conteudo, flags=re.DOTALL
)

with open("app.py", "w", encoding="utf-8") as f:
  f.write(conteudo_corrigido)

print("✅ 'app.py' corrigido com sucesso!")