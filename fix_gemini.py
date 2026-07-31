with open("app.py", "r", encoding="utf-8") as f:
  conteudo = f.read()

# Make function automatically detect global Gemini client if not passed
antigo = "if not GENAI_DISPONIVEL or not client:"
novo = """# Busca o cliente do Gemini do escopo global caso nao tenha sido passado
        client_ativo = client or globals().get('client')
        genai_ativo = GENAI_DISPONIVEL or globals().get('GENAI_DISPONIVEL', False)
        
        if not genai_ativo or not client_ativo:"""

# Replaces response call to use client_ativo
conteudo = conteudo.replace(
    "response = client.models.generate_content(",
    "response = client_ativo.models.generate_content(",
)

if antigo in conteudo:
  conteudo = conteudo.replace(antigo, novo, 1)

# Garante que a chamada dentro do with aba1 tambem passe os parametros
call_antiga = "render_cadastro_ficha_tecnica(db_session=db_aba1, Insumo=Insumo, Produto=Produto, FichaTecnica=FichaTecnica)"
call_nova = "render_cadastro_ficha_tecnica(db_session=db_aba1, Insumo=Insumo, Produto=Produto, FichaTecnica=FichaTecnica, client=client, GENAI_DISPONIVEL=GENAI_DISPONIVEL)"

if call_antiga in conteudo:
  conteudo = conteudo.replace(call_antiga, call_nova)

with open("app.py", "w", encoding="utf-8") as f:
  f.write(conteudo)

print("✅ Conexão com o Gemini corrigida com sucesso na Aba 1!")