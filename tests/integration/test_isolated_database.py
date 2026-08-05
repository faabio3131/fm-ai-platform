from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from test_mode import reset_database, seed_database


def test_seed_and_reset_isolated_database(monkeypatch, tmp_path):
    monkeypatch.setenv("FM_AI_TEST_MODE", "1")
    import app
    db_url = f"sqlite:///{tmp_path / 'isolated.sqlite3'}"
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine)
    reset_database(engine, app.Base)
    models = {name: getattr(app, name) for name in ["Usuario", "Cliente", "Produto", "Insumo", "FichaTecnica", "Venda", "ConfiguracaoMeta", "ContatoGerencial"]}
    seed_database(Session, models)
    db = Session()
    try:
        assert db.query(app.Usuario).filter_by(email="admin.test@fm.ai").count() == 1
        assert db.query(app.Produto).count() >= 1
        assert db.query(app.Venda).count() == 1
    finally:
        db.close()
    reset_database(engine, app.Base)
    db = Session()
    try:
        assert db.query(app.Produto).count() == 0
    finally:
        db.close()
