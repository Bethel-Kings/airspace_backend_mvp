import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.database import Base, get_db


@pytest.fixture()
def client(monkeypatch):
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(
        bind=test_engine, autoflush=False, autocommit=False, expire_on_commit=False
    )

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    monkeypatch.setattr(main, "engine", test_engine)
    main.app.dependency_overrides[get_db] = override_get_db
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    with TestClient(main.app) as test_client:
        yield test_client
    main.app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()


def register(client, email):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "safe-password-123"},
    )
    assert response.status_code == 201
    return response.json()["access_token"]


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_auth_and_vent_requires_login(client):
    token = register(client, "person@example.com")
    unauthorized = client.post("/api/v1/vent", json={"text": "A difficult day"})
    assert unauthorized.status_code == 401
    response = client.post(
        "/api/v1/vent",
        json={"text": "A difficult day"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["stored"] is False


def test_duplicate_registration_rejected(client):
    register(client, "person@example.com")
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "PERSON@example.com", "password": "safe-password-123"},
    )
    assert response.status_code == 409


def test_checkin_cannot_be_deleted_by_another_user(client):
    token_a = register(client, "a@example.com")
    token_b = register(client, "b@example.com")
    created = client.post(
        "/api/v1/checkins",
        json={"before_score": 8, "after_score": 5, "emotion": "overwhelmed"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert created.status_code == 201
    checkin_id = created.json()["id"]
    response = client.delete(
        f"/api/v1/checkins/{checkin_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert response.status_code == 404


def test_checkin_score_validation(client):
    token = register(client, "score@example.com")
    response = client.post(
        "/api/v1/checkins",
        json={"before_score": 11},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422
