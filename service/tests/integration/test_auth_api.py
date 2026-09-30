from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from wa_platform.api.app import app
from wa_platform.db import models  # noqa: F401
from wa_platform.db.base import Base
from wa_platform.db.session import get_db


def _override_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)

    def _get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    return _get_db


app.dependency_overrides[get_db] = _override_db()
client = TestClient(app)


def test_register_then_login():
    r = client.post("/auth/register", json={"email": "a@example.com", "password": "hunter22"})
    assert r.status_code == 200, r.text
    assert r.json()["api_key"]

    r = client.post("/auth/register", json={"email": "a@example.com", "password": "hunter22"})
    assert r.status_code == 409

    r = client.post("/auth/login", json={"email": "a@example.com", "password": "hunter22"})
    assert r.status_code == 200

    r = client.post("/auth/login", json={"email": "a@example.com", "password": "wrong"})
    assert r.status_code == 401
