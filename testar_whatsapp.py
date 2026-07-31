import os
import requests
import streamlit as st

# Tenta carregar do secrets do Streamlit ou variáveis locais
TOKEN = "1081719844449962|fXJCTTKAQOhSuM9vRNgUd4bQc60"
# Substitua pelo seu Phone Number ID do painel da Meta
PHONE_NUMBER_ID = "SEU_PHONE_NUMBER_ID_AQUI" 

NUMERO_DESTINO = "5511913547276"

url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

payload = {
    "messaging_product": "whatsapp",
    "to": NUMERO_DESTINO,
    "type": "text",
    "text": {
        "body": "🚀 *F&M AI FOOD*\n\nTeste de integração do WhatsApp realizado com sucesso!"
    }
}

response = requests.post(url, json=payload, headers=headers)

if response.status_code in [200, 201]:
    print("✅ Mensagem enviada com sucesso no WhatsApp!")
else:
    print(f"❌ Erro ao enviar ({response.status_code}):", response.text)