from datetime import datetime
import os
from core.database import (
    Base,
    FichaTecnica,
    Insumo,
    Produto,
    SessionLocal,
    Venda,
    engine,
)
from dotenv import load_dotenv
import pandas as pd
import streamlit as st

# --- 1. CONFIGURAÇÃO DO AMBIENTE E BANCO DE DADOS ---
load_dotenv()
os.makedirs(
    "imagens", exist_ok=True
)  # Garante que a pasta de imagens exista no disco
Base.metadata.create_all(
    bind=engine
)  # Assegura que o schema relacional esteja sincronizado

# Configuração da página Streamlit
st.set_page_config(
    page_title="F&M AI FOOD — ERP Gastronômico", page_icon="🍔", layout="wide"
)

# Tenta carregar o SDK da Inteligência Artificial do Google
GENAI_DISPONIVEL = False
try:
    import google.generativeai as genai

    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        genai.configure(api_key=api_key)
        GENAI_DISPONIVEL = True
except ImportError:
    pass


# Função auxiliar para obter sessão do banco de dados
def get_db():
    db = SessionLocal()
    try:
        return db
    finally:
        db.close()


# --- 2. BARRA LATERAL (SIDEBAR CORPORATIVA) ---
with st.sidebar:
    st.image(
        "https://cdn-icons-png.flaticon.com/512/3075/3075977.png", width=80
    )
    st.title("F&M AI FOOD")
    st.caption("Professional Gastronomy ERP & AI")
    st.markdown("---")

    st.subheader("🔐 Acesso Corporativo")
    st.success("Conectado como:\n**admin@micaburguer.com**")
    st.info("🏪 **Loja Ativa:**\nMica Burguer & Restaurante")

    if GENAI_DISPONIVEL:
        st.markdown("🟢 **Google GenAI SDK Conectado**")
    else:
        st.markdown("⚠️ **Modo Offline / Sem Chave API**")

    st.markdown("---")
    if st.button("🚪 Sair (Logout)", use_container_width=True):
        st.warning("Encerrando sessão corporativa...")


# --- 3. CABEÇALHO PRINCIPAL ---
st.title("🍔 F&M AI FOOD — Painel de Gestão & PDV")
st.markdown("---")

# Navegação por Abas
aba1, aba2, aba3, aba4, aba5 = st.tabs(
    [
        "🤖 Engenharia de Cardápio com I.A.",
        "📢 Campanhas & Automação Social",
        "🛒 Frente de Caixa (PDV)",
        "📦 Estoque de Insumos",
        "📊 Dashboard Financeiro",
    ]
)

# ==============================================================================
# ABA 1: ENGENHARIA DE CARDÁPIO COM I.A. (GERADOR GOURMET + FOTOS IMAGEN 3)
# ==============================================================================
with aba1:
    st.header("✨ Criação Inteligente de Pratos e Cardápio")
    st.write(
        "Cadastre novos itens com legendas conversivas e fotos de alta gastronomia geradas por IA."
    )

    with st.form("form_cardapio_ia"):
        col1, col2 = st.columns(2)
        with col1:
            nome_prato = st.text_input(
                "🍔 Nome do Prato / Lanche",
                placeholder="Ex: Mica Royal Truffle Bacon",
            )
            categoria = st.selectbox(
                "📂 Categoria",
                [
                    "Burgers Gourmet",
                    "Combos",
                    "Porções & Entradas",
                    "Sobremesas",
                    "Bebidas",
                ],
            )
            ingredientes_base = st.text_area(
                "📝 Ingredientes Principais",
                placeholder="Ex: Dois burgers smash 100g de costela angus, queijo provolone derretido, bacon artesanal em tiras, maionese trufada no pão brioche.",
            )
        with col2:
            preco_venda = st.number_input(
                "💲 Preço de Venda (R$)",
                min_value=0.0,
                value=38.90,
                step=0.50,
                format="%.2f",
            )
            custo_cmv = st.number_input(
                "📉 Custo Teórico dos Insumos / CMV (R$)",
                min_value=0.0,
                value=14.50,
                step=0.50,
                format="%.2f",
            )

            # Cálculo visual de margem
            if preco_venda > 0:
                margem_calc = ((preco_venda - custo_cmv) / preco_venda) * 100
                st.info(f"📈 **Margem de Lucro Bruta Prevista:** {margem_calc:.1f}%")
            else:
                margem_calc = 0.0

        btn_gerar_ia = st.form_submit_button(
            "🚀 Processar Texto & Imagem com Google I.A.", type="primary"
        )

    if btn_gerar_ia:
        if not nome_prato or not ingredientes_base:
            st.error(
                "⚠️ Por favor, preencha o Nome do Prato e os Ingredientes Principais!"
            )
        else:
            db = get_db()
            descricao_gerada = f"Experimente o magnífico {nome_prato}! Preparado com maestria utilizando {ingredientes_base.lower()}. Uma verdadeira experiência gourmet da Mica Burguer!"
            caminho_imagem_salva = None

            # Tentativa de geração com Google I.A. (Gemini + Imagen 3)
            if GENAI_DISPONIVEL:
                with st.spinner(
                    "🤖 A Inteligência Artificial está escrevendo a legenda gourmet e renderizando a fotografia publicitária..."
                ):
                    try:
                        # 1. Gerar Texto Gourmet com Gemini 1.5 Flash
                        model_text = genai.GenerativeModel("gemini-1.5-flash")
                        prompt_texto = f"Escreva uma descrição publicitária curta, altamente persuasiva, gourmet e apetitosa para um cardápio de restaurante para o prato: '{nome_prato}'. Ingredientes: {ingredientes_base}. Use emojis e gatilhos mentais gastronômicos."
                        resp_texto = model_text.generate_content(prompt_texto)
                        if resp_texto and resp_texto.text:
                            descricao_gerada = resp_texto.text.strip()

                        # 2. Gerar Fotografia com Imagen 3
                        try:
                            from google.generativeai import ImageGenerationModel

                            model_img = ImageGenerationModel(
                                "imagen-3.0-generate-002"
                            )
                            prompt_img = f"Professional studio food photography of a gourmet burger named {nome_prato}, containing {ingredientes_base}. 4k resolution, cinematic lighting, appetizing presentation, dark moody background, restaurant advertisement style."
                            images = model_img.generate_images(
                                prompt=prompt_img,
                                number_of_images=1,
                                aspect_ratio="1:1",
                            )

                            if images and len(images) > 0:
                                nome_arquivo = f"img_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
                                caminho_imagem_salva = os.path.join(
                                    "imagens", nome_arquivo
                                )
                                images[0].save(
                                    location=caminho_imagem_salva,
                                    include_generation_parameters=False,
                                )
                        except Exception as e_img:
                            st.warning(
                                f"⚠️ A IA do Google encontrou uma limitação ao renderizar a imagem (Motivo: {e_img}). O texto gourmet foi gerado com sucesso e o produto será salvo sem anexo visual."
                            )

                    except Exception as e_ia:
                        st.warning(
                            f"⚠️ Operando em Modo de Reserva: A IA do Google encontrou um bloqueio ({e_ia}). Usando texto padrão blindado."
                        )

            # 3. Salvar Produto no Banco de Dados SQLite
            try:
                novo_produto = Produto(
                    nome=nome_prato,
                    categoria=categoria,
                    preco_venda=preco_venda,
                    custo_unitario=custo_cmv,
                    margem_lucro=margem_calc,
                    imagem_path=caminho_imagem_salva,
                )
                db.add(novo_produto)
                db.commit()
                st.success(
                    f"🎉 Produto **{nome_prato}** cadastrado e gravado no banco de dados com sucesso!"
                )

                st.subheader("✍️ Descrição Gourmet Otimizada:")
                st.info(descricao_gerada)

                if caminho_imagem_salva and os.path.exists(
                    caminho_imagem_salva
                ):
                    st.subheader("📸 Fotografia Publicitária Gerada:")
                    st.image(
                        caminho_imagem_salva,
                        width=350,
                        caption=f"Fotografia Oficial: {nome_prato}",
                    )
            except Exception as e_db:
                db.rollback()
                st.error(f"❌ Erro ao gravar prato no banco de dados: {e_db}")

    st.markdown("---")
    st.subheader("🖼️ Galeria de Fotos dos Produtos Cadastrados")
    db = get_db()
    produtos_cadastrados = db.query(Produto).all()

    if produtos_cadastrados:
        cols = st.columns(4)
        for idx, prod in enumerate(produtos_cadastrados):
            with cols[idx % 4]:
                if prod.imagem_path and os.path.exists(prod.imagem_path):
                    st.image(prod.imagem_path, use_container_width=True)
                else:
                    st.image(
                        "https://cdn-icons-png.flaticon.com/512/3075/3075977.png",
                        use_container_width=True,
                    )
                st.markdown(f"**{prod.nome}**")
                st.caption(f"R$ {prod.preco_venda:.2f} | {prod.categoria}")
    else:
        st.info("Nenhum produto cadastrado no banco de dados até o momento.")


# ==============================================================================
# ABA 2: CAMPANHAS & AUTOMAÇÃO SOCIAL (GERADOR DE POSTS E MARKETING)
# ==============================================================================
with aba2:
    st.header("📢 Gerador de Campanhas & Automação de Marketing")
    st.write(
        "Crie postagens conversivas para o Instagram e WhatsApp reaproveitando as fotos oficiais do seu cardápio."
    )

    db = get_db()
    produtos = db.query(Produto).all()

    if not produtos:
        st.warning(
            "⚠️ Cadastre pelo menos um produto na Aba 1 para criar campanhas promocionais."
        )
    else:
        col_camp1, col_camp2 = st.columns(2)
        with col_camp1:
            prato_selecionado = st.selectbox(
                "🎯 Selecione o Prato em Destaque",
                produtos,
                format_func=lambda p: f"{p.nome} — R$ {p.preco_venda:.2f}",
            )
            tipo_promo = st.selectbox(
                "🔥 Objetivo da Campanha",
                [
                    "Happy Hour & Desconto",
                    "Lançamento Exclusivo",
                    "Especial de Fim de Semana",
                    "Apetite Noturno / Fome da Madrugada",
                ],
            )
            canal_social = st.selectbox(
                "📲 Canal de Destino",
                ["Instagram Feed & Stories", "WhatsApp VIP / Lista", "Facebook"],
            )

            btn_gerar_post = st.button(
                "⚡ Gerar Campanha com I.A.", type="primary"
            )

        with col_camp2:
            if btn_gerar_post:
                texto_promo = f"🚨 ATENÇÃO GOURMET! 🚨\n\nChegou a hora de provar o inigualável **{prato_selecionado.nome}** na Mica Burguer! Por apenas R$ {prato_selecionado.preco_venda:.2f}, você vive uma experiência de sabor inesquecível.\n\n👇 Peça agora pelo link na bio ou no nosso WhatsApp!"

                if GENAI_DISPONIVEL:
                    with st.spinner(
                        "🧠 Escrevendo copy publicitária focada em conversão..."
                    ):
                        try:
                            model_social = genai.GenerativeModel(
                                "gemini-1.5-flash"
                            )
                            prompt_social = f"Escreva uma postagem de marketing persuasiva e vibrante para o {canal_social} sobre o hambúrguer/prato: '{prato_selecionado.nome}' que custa R$ {prato_selecionado.preco_venda:.2f}. Objetivo da campanha: {tipo_promo}. Inclua emojis, gatilho de urgência e uma chamada para ação clara."
                            res_social = model_social.generate_content(
                                prompt_social
                            )
                            if res_social and res_social.text:
                                texto_promo = res_social.text.strip()
                        except Exception as e_soc:
                            st.warning(f"Usando copy padrão de reserva ({e_soc}).")

                st.subheader("📱 Legenda Pronta para Postagem:")
                st.code(texto_promo, language="markdown")

                if prato_selecionado.imagem_path and os.path.exists(
                    prato_selecionado.imagem_path
                ):
                    st.image(
                        prato_selecionado.imagem_path,
                        width=300,
                        caption=f"Foto Oficial: {prato_selecionado.nome} (Pronta para Anexar)",
                    )
                else:
                    st.info(
                        "ℹ️ Este produto não possui imagem salva em disco. Utilize uma foto do seu acervo no celular."
                    )


# ==============================================================================
# ABA 3: FRENTE DE CAIXA (PDV) COM BAIXA INTELIGENTE DA FASE 2
# ==============================================================================
with aba3:
    st.header("🛒 Frente de Caixa — PDV & Baixa em Tempo Real")
    st.write(
        "Registre os pedidos do balcão e veja a baixa de estoque acontecer por gramagem via Ficha Técnica (Fase 2)."
    )

    db = get_db()
    lista_pratos = db.query(Produto).all()

    if not lista_pratos:
        st.warning(
            "⚠️ Cadastre produtos no cardápio para habilitar as vendas no Frente de Caixa."
        )
    else:
        col_pdv1, col_pdv2 = st.columns([1, 2])

        with col_pdv1:
            st.subheader("🍔 Lançar Pedido")
            produto_selecionado = st.selectbox(
                "Prato / Lanche",
                lista_pratos,
                format_func=lambda x: f"{x.nome} (R$ {x.preco_venda:.2f})",
            )
            quantidade = st.number_input(
                "Quantidade Vendida", min_value=1, value=1, step=1
            )

            valor_unit = produto_selecionado.preco_venda
            valor_total = valor_unit * quantidade

            st.markdown("---")
            st.markdown(f"**Preço Unitário:** R$ {valor_unit:.2f}")
            st.markdown(f"### 💰 Total do Pedido: R$ {valor_total:.2f}")

            # --- BOTÃO DE CONFIRMAÇÃO DO PEDIDO (FASE 2: BAIXA POR FICHA TÉCNICA) ---
            if st.button(
                "✅ Confirmar Pedido & Baixar Estoque",
                type="primary",
                use_container_width=True,
            ):
                try:
                    # 1. Registrar a venda financeira na tabela Venda
                    nova_venda = Venda(
                        produto_id=produto_selecionado.id,
                        quantidade=quantidade,
                        valor_total=valor_total,
                        custo_total=(produto_selecionado.custo_unitario or 0.0)
                        * quantidade,
                        data_venda=datetime.now(),
                    )
                    db.add(nova_venda)

                    # 2. INTELIGÊNCIA DA FASE 2: Baixar estoque pela Ficha Técnica (Receita)
                    relatorio_baixa = []

                    if (
                        produto_selecionado.ingredientes
                    ):  # Verifica se o prato tem receita relacional
                        for item_receita in produto_selecionado.ingredientes:
                            insumo = item_receita.insumo
                            # Multiplica a gramagem/unidade gasta pela quantidade de pratos vendidos
                            consumo_real = (
                                item_receita.quantidade_gasta * quantidade
                            )

                            # Baixa no estoque com trava para não permitir saldo negativo no banco
                            insumo.quantidade_atual = max(
                                0.0, insumo.quantidade_atual - consumo_real
                            )

                            relatorio_baixa.append(
                                f"• **{insumo.nome}**: -{consumo_real:.3f} {insumo.unidade_medida}"
                            )
                    else:
                        st.warning(
                            "⚠️ Este produto ainda não possui uma Ficha Técnica vinculada. A venda foi registrada, mas o estoque não foi deduzido por gramagem."
                        )

                    # 3. Salvar todas as alterações (Financeiro + Almoxarifado) simultaneamente
                    db.commit()

                    st.success(
                        f"🎉 Pedido de **{quantidade}x {produto_selecionado.nome}** registrado com sucesso!"
                    )

                    if relatorio_baixa:
                        st.info(
                            "📉 **Baixa de Estoque Executada pela Ficha Técnica:**\n\n"
                            + "\n".join(relatorio_baixa)
                        )

                except Exception as e:
                    db.rollback()
                    st.error(f"❌ Erro ao processar venda no PDV: {e}")

        with col_pdv2:
            st.subheader("📋 Últimas Vendas Registradas no Dia")
            vendas_dia = (
                db.query(Venda).order_by(Venda.data_venda.desc()).limit(10).all()
            )

            if vendas_dia:
                dados_vendas = []
                for v in vendas_dia:
                    dados_vendas.append(
                        {
                            "Horário": v.data_venda.strftime("%H:%M:%S")
                            if v.data_venda
                            else "--:--",
                            "Prato / Lanche": v.produto.nome
                            if v.produto
                            else "Item Excluído",
                            "Qtd": v.quantidade,
                            "Valor Total (R$)": f"R$ {v.valor_total:.2f}",
                            "Custo CMV (R$)": f"R$ {v.custo_total:.2f}",
                        }
                    )
                df_vendas = pd.DataFrame(dados_vendas)
                st.dataframe(df_vendas, use_container_width=True, hide_index=True)
            else:
                st.info("Nenhuma transação foi processada no caixa hoje.")


# ==============================================================================
# ABA 4: ESTOQUE DE INSUMOS & ALMOXARIFADO
# ==============================================================================
with aba4:
    st.header("📦 Gestão Inteligente de Insumos & Estoque")
    st.write(
        "Acompanhe o saldo dos ingredientes em tempo real e verifique alertas automáticos de reposição."
    )

    db = get_db()
    insumos = db.query(Insumo).all()

    if insumos:
        dados_estoque = []
        for i in insumos:
            status_alerta = (
                "🔴 Alerta de Reposição"
                if i.quantidade_atual <= i.alerta_minimo
                else "🟢 Normal"
            )
            dados_estoque.append(
                {
                    "ID": i.id,
                    "Insumo / Ingrediente": i.nome,
                    "Saldo Atual": f"{i.quantidade_atual:.2f} {i.unidade_medida}",
                    "Alerta Mínimo": f"{i.alerta_minimo:.2f} {i.unidade_medida}",
                    "Custo Unitário (R$)": f"R$ {i.custo_unitario:.2f}",
                    "Status do Estoque": status_alerta,
                }
            )
        df_estoque = pd.DataFrame(dados_estoque)
        st.dataframe(df_estoque, use_container_width=True, hide_index=True)
    else:
        st.info("Nenhum insumo cadastrado na base de dados até o momento.")

    st.markdown("---")
    with st.expander("➕ Cadastrar ou Atualizar Saldo de Insumo Manualmente"):
        with st.form("form_novo_insumo"):
            col_ins1, col_ins2, col_ins3 = st.columns(3)
            with col_ins1:
                nome_ins = st.text_input(
                    "Nome do Ingrediente", placeholder="Ex: Bacon Artesanal"
                )
                unidade = st.selectbox(
                    "Unidade de Medida",
                    ["g", "kg", "un", "fatias", "ml", "L"],
                )
            with col_ins2:
                qtd_inicial = st.number_input(
                    "Quantidade Inicial / Saldo",
                    min_value=0.0,
                    value=500.0,
                    step=10.0,
                )
                alerta_min = st.number_input(
                    "Alerta de Estoque Mínimo",
                    min_value=0.0,
                    value=50.0,
                    step=5.0,
                )
            with col_ins3:
                custo_ins = st.number_input(
                    "Custo Unitário (R$)",
                    min_value=0.0,
                    value=0.05,
                    step=0.01,
                    format="%.4f",
                )

            btn_add_insumo = st.form_submit_button(
                "💾 Salvar Insumo no Banco", type="primary"
            )
            if btn_add_insumo and nome_ins:
                db = get_db()
                try:
                    ins_existente = (
                        db.query(Insumo).filter_by(nome=nome_ins).first()
                    )
                    if ins_existente:
                        ins_existente.quantidade_atual += qtd_inicial
                        ins_existente.custo_unitario = custo_ins
                        st.success(
                            f"📈 Saldo de **{nome_ins}** atualizado com sucesso!"
                        )
                    else:
                        novo_ins = Insumo(
                            nome=nome_ins,
                            quantidade_atual=qtd_inicial,
                            unidade_medida=unidade,
                            alerta_minimo=alerta_min,
                            custo_unitario=custo_ins,
                        )
                        db.add(novo_ins)
                        st.success(
                            f"🎉 Insumo **{nome_ins}** cadastrado com sucesso!"
                        )
                    db.commit()
                    st.rerun()
                except Exception as e_ins:
                    db.rollback()
                    st.error(f"❌ Erro ao salvar insumo: {e_ins}")


# ==============================================================================
# ABA 5: DASHBOARD FINANCEIRO & GRÁFICOS GERENCIAIS
# ==============================================================================
with aba5:
    st.header("📊 Dashboard Financeiro & BI Gastronômico")
    st.write(
        "Análise de desempenho, lucro bruto e margens operacionais da Mica Burguer em tempo real."
    )

    db = get_db()
    todas_vendas = db.query(Venda).all()

    if not todas_vendas:
        st.info(
            "ℹ️ Realize vendas na Aba 3 (Frente de Caixa) para visualizar os gráficos e métricas de faturamento aqui."
        )
    else:
        fat_total = sum(v.valor_total for v in todas_vendas)
        custo_tot = sum(v.custo_total for v in todas_vendas)
        lucro_bruto = fat_total - custo_tot
        margem_geral = (
            (lucro_bruto / fat_total * 100) if fat_total > 0 else 0.0
        )

        # Cards de Indicadores Principais (KPIs)
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        kpi1.metric("💵 Faturamento Acumulado", f"R$ {fat_total:,.2f}")
        kpi2.metric("📉 Custo Total dos Insumos (CMV)", f"R$ {custo_tot:,.2f}")
        kpi3.metric("📈 Lucro Bruto", f"R$ {lucro_bruto:,.2f}")
        kpi4.metric("📊 Margem de Lucro Geral", f"{margem_geral:.1f}%")

        st.markdown("---")

        # Gráficos de Faturamento
        col_graf1, col_graf2 = st.columns(2)
        with col_graf1:
            st.subheader("🍔 Desempenho de Vendas por Produto")
            df_graf = pd.DataFrame(
                [
                    {
                        "Produto": v.produto.nome
                        if v.produto
                        else "Deletado",
                        "Total Vendido (R$)": v.valor_total,
                        "Quantidade": v.quantidade,
                    }
                    for v in todas_vendas
                ]
            )
            df_agrupado = (
                df_graf.groupby("Produto")["Total Vendido (R$)"]
                .sum()
                .reset_index()
            )
            st.bar_chart(
                df_agrupado,
                x="Produto",
                y="Total Vendido (R$)",
                use_container_width=True,
            )

        with col_graf2:
            st.subheader("📈 Relação Faturamento vs. Custo (CMV)")
            df_cmv = pd.DataFrame(
                {
                    "Categoria": [
                        "Faturamento Bruto",
                        "Custo dos Insumos (CMV)",
                        "Lucro Bruto",
                    ],
                    "Valor (R$)": [fat_total, custo_tot, lucro_bruto],
                }
            )
            st.bar_chart(
                df_cmv,
                x="Categoria",
                y="Valor (R$)",
                color=["#1E3A8A"],
                use_container_width=True,
            )