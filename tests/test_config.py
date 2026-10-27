import pytest
from pydantic import ValidationError

from app.config import Settings

PROD = dict(environment="production", database_url="postgresql://u:p@h/db", cors_origins="https://app.example.com")


def make(**kw):
    return Settings(_env_file=None, **kw)


def test_production_requires_jwt_secret():
    with pytest.raises(ValidationError):
        make(**PROD)


def test_production_rejects_short_placeholder_and_revoked_secrets():
    with pytest.raises(ValidationError):
        make(jwt_secret="short", **PROD)
    with pytest.raises(ValidationError):
        make(jwt_secret="replace-with-a-long-random-secret-before-deployment", **PROD)


def test_production_rejects_the_leaked_secret(monkeypatch):
    import hashlib
    import app.config as cfg
    leaked = "x" * 40
    monkeypatch.setattr(cfg, "REVOKED_SECRET_SHA256", {hashlib.sha256(leaked.encode()).hexdigest()})
    with pytest.raises(ValidationError):
        make(jwt_secret=leaked, **PROD)


def test_production_accepts_strong_secret():
    assert make(jwt_secret="a" * 48, **PROD).jwt_secret == "a" * 48


def test_development_gets_ephemeral_random_secret():
    a, b = make(), make()
    assert a.jwt_secret and b.jwt_secret and a.jwt_secret != b.jwt_secret
