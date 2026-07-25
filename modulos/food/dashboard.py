import subprocess
import sys
import time
import socket
import streamlit as st
import requests

# ==========================================
# --- MOTOR DE ARRANQUE NA PORTA 9000 ---
# ==========================================
@st.cache_resource
def iniciar_backend_fastapi():
    try:
        subprocess.run(["pkill", "-f", "uvicorn"], check=False)
        time.sleep(1)
    except Exception:
        pass

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    porta_livre = sock.connect_ex(('127.0.0.1', 9000)) != 0
    sock.close()
    
    if porta_livre:
        subprocess.Popen([sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "9000"])
        time.sleep(3)

iniciar_backend_fastapi()
# ==========================================

st.set_page_config(
    page_title="F&M AI FOOD - ERP Gastronômico",
    page_icon="🍔",
    layout="wide"
)

API_URL = "http://127.0.0.1:9000"

if "token" not in st.session_state:
    st.session_state["token"] = None

st.title("🍔 F&M AI FOOD — Painel de Gestão & PDV")
st.markdown("---")

# ==========================================
# --- BARRA LATERAL: LOGIN E CADASTRO ---
# ==========================================
with st.sidebar:
    st.header("🔒 Acesso Corporativo")
    
    if not st.session_state["token"]:
        st.info("Faça login com sua conta da Mica Burguer para liberar as ferramentas do ERP.")
        email = st.text_input("E-mail corporativo", value="admin@micaburger.com")
        senha = st.text_input("Senha", value="123456", type="password")
        
        col_btn1, col_btn2 = st.columns(2)
        
        with col_btn1:
            if st.button("Entrar", type="primary", use_container_width=True):
                try:
                    res = requests.post(
                        f"{API_URL}/auth/login",
                        data={"username": email, "password": senha, "grant_type": "password"}
                    )
                    if res.status_code == 200:
                        st.session_state["token"] = res.json()["access_token"]
                        st.success("✅ Conectado à nuvem AWS!")
                        st.rerun()
                    else:
                        st.error("❌ E-mail ou senha incorretos. Tente clicar em 'Criar Conta' para consertar a senha.")
                except Exception as e:
                    st.error(f"⚠️ Erro de conexão com o servidor ({e})")
                    
        with col_btn2:
            if st.button("✨ Criar Conta", use_container_width=True):
                try:
                    res = requests.post(
                        f"{API_URL}/auth/cadastrar",
                        json={"email": email, "senha": senha}
                    )
                    if res.status_code in [200, 201]:
                        st.success(f"🎉 {res.json().get('mensagem', 'Conta pronta!')} Clique em 'Entrar'.")
                    else:
                        st.error(f"Erro do Banco: {res.text}")
                except Exception as e:
                    st.error(f"Erro: {e}")
    else:
        st.success("🟢 Conectado na Nuvem AWS")
        st.write("**Loja Ativa:** Mica Burguer & Restaurante")
        if st.button("Sair (Logout)", use_container_width=True):
            st.session_state["token"] = None
            st.rerun()

# ==========================================
# --- ÁREA PRINCIPAL DO ERP (ABAS) ---
# ==========================================
if not st.session_state["token"]:
    st.warning("👈 Por favor, realize o login na barra lateral esquerda para liberar o cardápio e o caixa.")
else:
    aba_cardapio, aba_pdv = st.tabs(["🤖 Engenharia de Cardápio com I.A.", "🛒 Frente de Caixa (PDV & Estoque)"])

    with aba_cardapio:
        st.subheader("✨ Criador Gourmet Automatizado")
        st.write("Digite os dados simples e deixe a Inteligência Artificial gerar a descrição persuasiva e calcular a margem de lucro.")
        
        with st.form("form_novo_produto"):
            col1, col2 = st.columns(2)
            with col1:
                nome_prod = st.text_input("Nome do Prato / Lanche", value="Bacon Beast Triple Smash")
                categoria_prod = st.selectbox("Categoria", ["Burgers", "Bebidas", "Acompanhamentos", "Sobremesas"])
            with col2:
                preco_prod = st.number_input("Preço de Venda (R$)", value=39.90, step=1.0)
            
            desc_bruta = st.text_area("Descrição Bruta / Lista de Ingredientes", value="Três hambúrgueres de 90g, triplo bacon crocante, triplo queijo cheddar, cebola caramelizada na cerveja preta e maionese defumada no pão brioche.")
            
            btn_gerar_ia = st.form_submit_button("🚀 Processar e Cadastrar no Banco", type="primary")
            
            if btn_gerar_ia:
                headers = {"Authorization": f"Bearer {st.session_state['token']}"}
                payload = {
                    "nome": nome_prod,
                    "categoria": categoria_prod,
                    "descricao_bruta": desc_bruta,
                    "preco_venda": preco_prod
                }
                try:
                    res = requests.post(f"{API_URL}/produtos/cadastrar-com-ia", json=payload, headers=headers)
                    if res.status_code == 200:
                        dados_ia = res.json()
                        st.success(f"🎉 Produto #{dados_ia['id']} salvo no banco de dados com sucesso!")
                        
                        c1, c2, c3 = st.columns(3)
                        c1.metric("Preço Final", f"R$ {dados_ia['preco_venda']:.2f}")
                        c2.metric("Custo Teórico (CMV)", f"R$ {dados_ia['custo_total_cmv']:.2f}")
                        c3.metric("Margem Real", dados_ia["margem_exibicao"])
                        
                        st.info(f"**Descrição Gourmet Otimizada pela I.A.:**\n\n{dados_ia['descricao_ai']}")
                    else:
                        st.error(f"Erro ao salvar: {res.text}")
                except Exception as e:
                    st.error(f"Erro na requisição: {e}")

    with aba_pdv:
        st.subheader("🍟 Frente de Caixa e Baixa Automática de Insumos")
        st.write("Registre pedidos em tempo real e assista ao sistema descontando os ingredientes na nuvem.")
        
        col_pdv_esq, col_pdv_dir = st.columns([1, 2])
        
        with col_pdv_esq:
            st.markdown("### 📝 Registrar Pedido")
            id_venda = st.number_input("ID do Produto no Banco", min_value=1, value=1, step=1)
            qtd_venda = st.number_input("Quantidade Vendida", min_value=1, value=2, step=1)
            
            btn_vender = st.button("💳 Finalizar Venda e Emitir Cupom", type="primary", use_container_width=True)
            
        with col_pdv_dir:
            st.markdown("### 🧾 Cupom & Status do Estoque")
            if btn_vender:
                headers = {"Authorization": f"Bearer {st.session_state['token']}"}
                try:
                    res = requests.post(
                        f"{API_URL}/produtos/{id_venda}/vender?quantidade={qtd_venda}",
                        headers=headers
                    )
                    if res.status_code == 200:
                        dados_venda = res.json()
                        st.success(f"✅ {dados_venda['mensagem']}")
                        
                        st.write(f"**Item:** {dados_venda['produto_vendido']} | **Qtd:** {dados_venda['quantidade']}x")
                        st.write(f"### 💰 Total a Pagar: R$ {dados_venda['valor_total']:.2f}")
                        
                        st.markdown("#### 📉 Relatório de Baixa Automática de Insumos:")
                        for item in dados_venda["baixas_estoque"]:
                            st.warning(f"🔻 **-{item['quantidade_descontada']} {item['unidade']}** descontados de `{item['insumo']}`")
                    else:
                        st.error("❌ Produto não encontrado ou erro no processamento do pedido.")
                except Exception as e:
                    st.error(f"Erro ao conectar com o PDV: {e}")