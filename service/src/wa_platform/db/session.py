from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from wa_platform.core.config import Settings, get_settings


def make_engine(settings: Settings):
    return create_engine(settings.database_url, pool_pre_ping=True)


_engine = None
_SessionLocal: sessionmaker | None = None


def _init(settings: Settings) -> sessionmaker:
    global _engine, _SessionLocal
    if _SessionLocal is None:
        _engine = make_engine(settings)
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    return _SessionLocal


def get_db() -> Iterator[Session]:
    session_factory = _init(get_settings())
    db = session_factory()
    try:
        yield db
    finally:
        db.close()


def get_session_factory(settings: Settings) -> sessionmaker:
    """Lazily builds and caches the engine/sessionmaker (once per cold start). Used directly by
    the worker Lambda handler, which manages its own Session per SQS record instead of going
    through FastAPI's per-request get_db() — calling make_engine() per invocation instead (as it
    used to) would open a fresh connection pool on every warm invocation and never close the old
    one."""
    return _init(settings)
