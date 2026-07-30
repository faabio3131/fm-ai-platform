import os

# Define uma chave fictícia apenas para o terminal liberar a importação dos módulos
os.environ["GEMINI_API_KEY"] = "dummy_key_for_script"

from main import Insumo, SessionLocal

db = SessionLocal()
item = db.query(Insumo).filter(Insumo.nome.ilike("%cheddar fatiado%")).first()

if item:
  print(f"Encontrado: {item.nome} | Unidade antiga: {item.unidade_medida}")
  item.unidade_medida = "kg"
  db.commit()
  print("✅ Sucesso: Unidade do cheddar atualizada para 'kg'!")
else:
  print("❌ Item 'cheddar fatiado' não foi encontrado no banco de dados.")

db.close()