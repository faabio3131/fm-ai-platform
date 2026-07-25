import os
from dotenv import load_dotenv
from google import genai

print("🟢 [INICIANDO GERENTE AI: TESTE DE ESTRESSE DO CARDÁPIO...] 🟢\n")

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

def processar_teste_estresse(anotacao: str, numero_teste: int):
    print(f"==================================================")
    print(f"🔥 TESTE DE ESTRESSE #{numero_teste} - TEXTO DA MICHELE:")
    print(f"'{anotacao}'")
    print(f"==================================================\n")
    
    prompt = f"""
    Você é o Gerente AI do sistema F&M AI Food, especialista em engenharia de cardápio e marketing gastronômico para o iFood e WhatsApp.
    
    A dona da cozinha digitou o seguinte item de forma extremamente rápida, com abreviações ou erros:
    "{anotacao}"
    
    Sua missão:
    1. Criar um Nome Comercial apetitoso e claro.
    2. Criar uma Descrição de Vendas irresistível (focando nos ingredientes e na experiência do cliente).
    3. Identificar a Categoria correta (Ex: Marmita Tradicional, Combos, Bebidas, Sobremesas).
    4. Extrair o Preço se houver no texto. SE NÃO HOUVER PREÇO, sugira um preço médio realista de mercado para marmitaria de qualidade (apenas números com vírgula).
    
    Responda APENAS nesse formato estruturado:
    NOME: [Nome comercial]
    CATEGORIA: [Categoria]
    PRECO: [Valor numérico]
    DESCRICAO: [Descrição criada]
    """
    
    # Usando direto o modelo que descobrimos ser o ouro da sua conta!
    response = client.models.generate_content(
        model="models/gemini-flash-latest",
        contents=prompt,
    )
    
    print("✨ --- RESULTADO COMERCIAL GERADO PELA IA --- ✨")
    print(response.text)
    print("--------------------------------------------------\n")

if __name__ == "__main__":
    # Teste 1: Prato tradicional muito abreviado e SEM PREÇO (a IA terá que sugerir um valor)
    teste_1 = "bife acebolado c arroz feijao e fritas marm G"
    
    # Teste 2: Combo digitado correndo com erros de português
    teste_2 = "strogonof de frango pt peq + coca lata zero trinta e cinco reais"
    
    print("🚀 Iniciando bateria de testes...\n")
    processar_teste_estresse(teste_1, 1)
    processar_teste_estresse(teste_2, 2)
    print("🏁 Bateria de testes finalizada com sucesso!")