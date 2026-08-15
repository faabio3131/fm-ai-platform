from __future__ import annotations

from types import SimpleNamespace

from scripts import migrate_v1


def test_main_carrega_database_url_do_dotenv_antes_das_settings(
    tmp_path, monkeypatch
) -> None:
    database_url = "postgresql+psycopg://user:password@example.invalid/kordena"
    (tmp_path / ".env").write_text(f"DATABASE_URL={database_url}\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("FM_AI_ENV", raising=False)
    captured: list[str] = []

    def build_engine_spy(settings):
        captured.append(settings.database_url)
        return object()

    monkeypatch.setattr(migrate_v1, "build_engine", build_engine_spy)
    monkeypatch.setattr(
        migrate_v1,
        "check_database_health",
        lambda _engine: SimpleNamespace(ok=True, detail="ok"),
    )
    monkeypatch.setattr(migrate_v1, "run_migrations", lambda _engine: ())

    assert migrate_v1.main() == 0
    assert captured == [database_url]
