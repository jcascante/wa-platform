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
    api_key = r.json()["api_key"]
    assert api_key

    r = client.post("/auth/register", json={"email": "a@example.com", "password": "hunter22"})
    assert r.status_code == 409

    r = client.post("/auth/login", json={"email": "a@example.com", "password": "hunter22"})
    assert r.status_code == 200
    # Only ever shown at register / rotate time — we store a hash, not the key, so login can't
    # hand it back out.
    assert "api_key" not in r.json()

    r = client.post("/auth/login", json={"email": "a@example.com", "password": "wrong"})
    assert r.status_code == 401

    # Unknown email must fail the same way as a wrong password (no user-enumeration signal).
    r = client.post("/auth/login", json={"email": "nobody@example.com", "password": "whatever"})
    assert r.status_code == 401


def test_register_rejects_short_password():
    r = client.post("/auth/register", json={"email": "short@example.com", "password": "short1"})
    assert r.status_code == 422


def test_rotate_api_key_replaces_old_one():
    r = client.post("/auth/register", json={"email": "b@example.com", "password": "hunter22"})
    old_key = r.json()["api_key"]

    r = client.post("/auth/api-key/rotate", headers={"Authorization": f"Bearer {old_key}"})
    assert r.status_code == 200, r.text
    new_key = r.json()["api_key"]
    assert new_key != old_key

    r = client.get("/me", headers={"Authorization": f"Bearer {old_key}"})
    assert r.status_code == 401

    r = client.get("/me", headers={"Authorization": f"Bearer {new_key}"})
    assert r.status_code == 200
