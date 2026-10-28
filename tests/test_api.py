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


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_me_returns_profile_and_requires_token(client):
    assert client.get("/api/v1/me").status_code == 401
    token = register(client, "me@example.com")
    body = client.get("/api/v1/me", headers=auth(token)).json()
    assert body["email"] == "me@example.com"
    assert "password_hash" not in body


def test_patch_checkin_sets_after_score(client):
    token = register(client, "patch@example.com")
    created = client.post("/api/v1/checkins", json={"before_score": 3}, headers=auth(token)).json()
    assert created["after_score"] is None
    patched = client.patch(f"/api/v1/checkins/{created['id']}", json={"after_score": 6}, headers=auth(token))
    assert patched.status_code == 200
    assert patched.json()["after_score"] == 6
    assert patched.json()["before_score"] == 3


def test_patch_checkin_validation_and_ownership(client):
    a, b = register(client, "pa@example.com"), register(client, "pb@example.com")
    cid = client.post("/api/v1/checkins", json={"before_score": 4}, headers=auth(a)).json()["id"]
    assert client.patch(f"/api/v1/checkins/{cid}", json={}, headers=auth(a)).status_code == 422
    assert client.patch(f"/api/v1/checkins/{cid}", json={"before_score": 9}, headers=auth(a)).status_code == 422
    assert client.patch(f"/api/v1/checkins/{cid}", json={"after_score": 11}, headers=auth(a)).status_code == 422
    assert client.patch(f"/api/v1/checkins/{cid}", json={"after_score": 5}, headers=auth(b)).status_code == 404


def test_patch_can_clear_note(client):
    token = register(client, "clear@example.com")
    cid = client.post("/api/v1/checkins", json={"before_score": 4, "note": "hi"}, headers=auth(token)).json()["id"]
    cleared = client.patch(f"/api/v1/checkins/{cid}", json={"note": None}, headers=auth(token)).json()
    assert cleared["note"] is None


def test_checkin_note_triggers_safety_notice(client):
    token = register(client, "note@example.com")
    flagged = client.post(
        "/api/v1/checkins", json={"before_score": 2, "note": "I want to die"}, headers=auth(token)
    ).json()
    assert flagged["safety_notice"]
    plain = client.post("/api/v1/checkins", json={"before_score": 5, "note": "ok day"}, headers=auth(token)).json()
    assert plain["safety_notice"] is None


def test_checkin_timestamp_is_timezone_aware(client):
    token = register(client, "tz@example.com")
    created = client.post("/api/v1/checkins", json={"before_score": 5}, headers=auth(token)).json()
    assert created["created_at"].endswith(("Z", "+00:00"))


def test_vent_flags_curly_apostrophe_crisis(client):
    token = register(client, "vent@example.com")
    body = client.post("/api/v1/vent", json={"text": "I don\u2019t want to live"}, headers=auth(token)).json()
    assert body["safety_notice"]


def test_register_is_rate_limited(client):
    codes = [
        client.post("/api/v1/auth/register", json={"email": f"u{i}@example.com", "password": "safe-password-123"}).status_code
        for i in range(12)
    ]
    assert codes[:10] == [201] * 10
    assert codes[10] == 429
    limited = client.post("/api/v1/auth/register", json={"email": "z@example.com", "password": "safe-password-123"})
    assert "retry-after" in limited.headers


def test_login_per_email_limit_and_generic_error(client):
    register(client, "brute@example.com")
    codes = [
        client.post("/api/v1/auth/login", json={"email": "brute@example.com", "password": "wrong-password"}).status_code
        for _ in range(11)
    ]
    assert codes[:10] == [401] * 10
    assert codes[10] == 429
    unknown = client.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": "x"})
    assert unknown.status_code == 401
    assert unknown.json()["detail"] == "Invalid email or password."


def test_reframe_paths(client, monkeypatch):
    token = register(client, "ref@example.com")
    # no AI key
    monkeypatch.setattr(main.settings, "openai_api_key", None)
    r = client.post("/api/v1/reframe", json={"text": "bad day"}, headers=auth(token)).json()
    assert r["ai_status"] == "unavailable" and r["ai_enabled"] is False
    # AI key but no consent
    monkeypatch.setattr(main.settings, "openai_api_key", "sk-test")
    r = client.post("/api/v1/reframe", json={"text": "bad day"}, headers=auth(token)).json()
    assert r["ai_status"] == "consent_required" and r["consent_required"] is True and r["reflection"] is None
    # consent given, provider mocked
    async def fake(text, style):
        from app.ai import ReflectionResult
        return ReflectionResult("a reflection", "success")
    monkeypatch.setattr(main, "generate_reflection", fake)
    r = client.post("/api/v1/reframe", json={"text": "bad day", "consent_to_ai_processing": True}, headers=auth(token)).json()
    assert r["ai_status"] == "success" and r["reflection"] == "a reflection"
    # crisis text never reaches the provider
    called = []
    async def spy(text, style):
        called.append(text)
        return fake(text, style)
    monkeypatch.setattr(main, "generate_reflection", spy)
    r = client.post("/api/v1/reframe", json={"text": "I want to die", "consent_to_ai_processing": True}, headers=auth(token)).json()
    assert r["ai_status"] == "skipped_for_safety" and r["needs_human_support"] is True and not called


def test_reframe_ai_calls_are_limited_per_user(client, monkeypatch):
    token = register(client, "cost@example.com")
    monkeypatch.setattr(main.settings, "openai_api_key", "sk-test")
    async def fake(text, style):
        from app.ai import ReflectionResult
        return ReflectionResult("ok", "success")
    monkeypatch.setattr(main, "generate_reflection", fake)
    body = {"text": "bad day", "consent_to_ai_processing": True}
    codes = [client.post("/api/v1/reframe", json=body, headers=auth(token)).status_code for _ in range(31)]
    assert codes[:30] == [200] * 30 and codes[30] == 429
    # safety path stays available even when throttled
    crisis = client.post("/api/v1/reframe", json={"text": "I want to die"}, headers=auth(token))
    assert crisis.status_code == 200


def test_openapi_declares_ai_status_enum(client):
    schema = client.get("/openapi.json").json()["components"]["schemas"]["ReframeResponse"]
    assert set(schema["properties"]["ai_status"]["enum"]) == {
        "skipped_for_safety", "unavailable", "consent_required", "success", "fallback"
    }


def test_crisis_resources_endpoint_public(client):
    response = client.get("/api/v1/crisis-resources")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 5
    mani = next(r for r in data if "MANI" in r["name"])
    assert mani["phone"] == "08091116264"
    assert mani["alt_phone"] == "08111680686"
    assert mani["hours"] == "24/7"
    assert "https://mentallyaware.org" in mani["url"]


def test_crisis_resources_in_flagged_responses(client):
    token = register(client, "safety_flow@example.com")

    # Vent crisis response
    vent_res = client.post(
        "/api/v1/vent", json={"text": "I want to die"}, headers=auth(token)
    ).json()
    assert vent_res["safety_notice"] is not None
    assert vent_res["crisis_resources"] is not None
    assert len(vent_res["crisis_resources"]) == 5

    # Reframe crisis response
    reframe_res = client.post(
        "/api/v1/reframe", json={"text": "I don't want to live"}, headers=auth(token)
    ).json()
    assert reframe_res["safety_notice"] is not None
    assert reframe_res["crisis_resources"] is not None
    assert len(reframe_res["crisis_resources"]) == 5

    # Checkin crisis response
    checkin_res = client.post(
        "/api/v1/checkins", json={"before_score": 1, "note": "suicide"}, headers=auth(token)
    ).json()
    assert checkin_res["safety_notice"] is not None
    assert checkin_res["crisis_resources"] is not None
    assert len(checkin_res["crisis_resources"]) == 5


def test_cors_allows_vercel_frontend(client):
    origin = "https://air-space-frontend-nine.vercel.app"
    response = client.options(
        "/api/v1/crisis-resources",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == origin
