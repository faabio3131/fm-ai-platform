import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_http_so_adapta_cadastro_sem_repositorio_ou_transacao_paralela():
    source = (ROOT / "http_api/admin_empresa.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    assert not any(module.startswith("infra.") for module in imports)
    chamadas = {
        n.func.attr
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
    }
    assert {
        "obter_empresa",
        "listar_unidades",
        "atualizar_empresa",
        "atualizar_unidade",
        "criar_unidade",
    } <= chamadas
    assert (
        not {"commit", "execute", "add", "definir_unidades", "no_escopo_ativo"}
        & chamadas
    )
    assert "contexto_backoffice" in source
    assert 'ConfigDict(extra="forbid")' in source


def test_web_cadastral_nao_troca_escopo_e_reutiliza_backoffice():
    feature = ROOT / "web/src/features/backoffice/empresa"
    source = "\n".join(p.read_text(encoding="utf-8") for p in feature.rglob("*.ts*"))
    assert "select-unit" not in source
    assert "selectUnit" not in source
    assert "X-Tenant-ID" not in source and "X-Unit-ID" not in source
    assert "unidades_permitidas" not in source
    assert (ROOT / "web/src/app/admin/empresa/page.tsx").is_file()
    assert not (ROOT / "web/src/app/admin/unidades/page.tsx").exists()
    assert "AdminStepUpGuard" in (ROOT / "web/src/app/admin/layout.tsx").read_text(
        encoding="utf-8"
    )
