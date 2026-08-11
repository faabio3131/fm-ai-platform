from pathlib import Path

path = Path("app.py")
texto = path.read_text(encoding="utf-8")

importo_alvo = "from core.salao.ui_streamlit import render_salao\n"
importo_novo = importo_alvo + "from core.mica.ui_streamlit import render_mica_v1\n"
if "from core.mica.ui_streamlit import render_mica_v1" not in texto:
    if importo_alvo not in texto:
        raise SystemExit("import anchor not found")
    texto = texto.replace(importo_alvo, importo_novo, 1)

inicio = '# ==============================================================================\n# ABA 6: BOT CLIENTE (ASSISTENTE VIRTUAL "MICA I.A.")\n# ==============================================================================\n'
fim = "# Contrato técnico de prontidão dos testes browser-driven. Ele é emitido apenas\n"
if inicio not in texto or fim not in texto:
    raise SystemExit("Mica block anchors not found")

antes, restante = texto.split(inicio, 1)
_, depois = restante.split(fim, 1)
novo_bloco = '''# ==============================================================================\n# ABA 6: MICA I.A. V1 — FLUXO SEGURO\n# ==============================================================================\nwith aba6:\n    render_mica_v1(\n        session_factory=SessionLocal,\n        produto_cls=Produto,\n        generate_content=generate_content,\n    )\n\n'''
texto = antes + novo_bloco + fim + depois
path.write_text(texto, encoding="utf-8")
