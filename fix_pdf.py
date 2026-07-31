import re

with open("app.py", "r", encoding="utf-8") as f:
  conteudo = f.read()

padrao = r"contents\s*=\s*\[\s*\{['\"]mime_type['\"]\s*:\s*mime,\s*['\"]data['\"]\s*:\s*bytes_data\}\s*,\s*prompt\s*\]"

substituicao = """from google.genai import types
                        contents = [
                            types.Part.from_bytes(data=bytes_data, mime_type=mime),
                            prompt
                        ]"""

if re.search(padrao, conteudo):
  conteudo_novo = re.sub(padrao, substituicao, conteudo)
else:
  conteudo_novo = conteudo.replace(
      "contents = [{'mime_type': mime, 'data': bytes_data}, prompt]",
      substituicao,
  ).replace(
      'contents = [{"mime_type": mime, "data": bytes_data}, prompt]',
      substituicao,
  )

with open("app.py", "w", encoding="utf-8") as f:
  f.write(conteudo_novo)

print("✅ 'app.py' atualizado para o formato oficial do Gemini!")