from pathlib import Path
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from app.db import make_engine


def test_frozen_migration_up_and_down(tmp_path, monkeypatch):
    engine = make_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    monkeypatch.setattr("app.db.engine", engine)
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    command.upgrade(config, "head")
    schema = inspect(engine)
    assert {"organizations", "tickets", "outbox", "inbox", "audit", "users", "counters"} <= set(
        schema.get_table_names()
    )
    assert any(index["name"] == "uq_serving_counter" for index in schema.get_indexes("tickets"))
    assert len(schema.get_check_constraints("tickets")) == 2
    command.downgrade(config, "base")
    assert "tickets" not in inspect(engine).get_table_names()
    engine.dispose()
