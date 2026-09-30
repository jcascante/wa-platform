import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from wa_platform.db import models  # noqa: F401
from wa_platform.db.base import Base

# Matches docker-compose.yml's local Postgres by default so `make up && make test` just works.
_PG_URL = os.environ.get(
    "TEST_POSTGRES_URL", "postgresql+psycopg://platform:platform@localhost:5432/platform"
)


@pytest.fixture
def pg_db() -> Session:
    """A real Postgres connection — some worker logic (the `postgresql.insert(...)
    .on_conflict_do_nothing()` dedupe in workers/message_processor.py) is dialect-specific and
    can't be exercised against the in-memory SQLite fixture in tests/conftest.py. Skips instead
    of failing when no Postgres is reachable (e.g. `make up` wasn't run); CI always brings one up
    — see .github/workflows/ci.yml."""
    try:
        engine = create_engine(_PG_URL)
        with engine.connect():
            pass
    except OperationalError:
        pytest.skip(f"no Postgres reachable at {_PG_URL} — run `make up` or set TEST_POSTGRES_URL")

    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.rollback()
        for table in reversed(Base.metadata.sorted_tables):
            session.execute(table.delete())
        session.commit()
        session.close()
        engine.dispose()
