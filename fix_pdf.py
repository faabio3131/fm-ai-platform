import re

with open("app.py", "r", encoding="utf-8") as f:
  code = f.read()

# 1. Garante que a importacao do types seja adicionada no inicio se nao existir
if "from google.genai import types" not in code:
  code = "from google.genai import types\n" + code

# 2. Substitui qualquer formato de dicionario {'mime_type': ..., 'data': ...} pelo Part.from_bytes
padrao_dict = r"\{\s*['\"]mime_type['\"]\s*:\s*mime\s*,\s*['\"]data['\"]\s*:\s*bytes_data\s*\}"
substituicao = "types.Part.from_bytes(data=bytes_data, mime_type=mime)"

novo_code, subs = re.subn(padrao_dict, substituicao, code)

if subs > 0:
  with open("app.py", "w", encoding="utf-8") as f:
    f.write(novo_code)
  print(f"✅ Sucesso! Corrigido {subs} local(is) no arquivo 'app.py'.")
else:
  print("⚠️ Não foi encontrada a estrutura antiga. Verifique o arquivo app.py.")