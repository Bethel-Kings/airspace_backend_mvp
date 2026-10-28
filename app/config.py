import hashlib
import secrets

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# SHA-256 of a JWT secret that was once committed to this repo's history.
# Production refuses to start with it, even if someone sets it by mistake.
REVOKED_SECRET_SHA256 = {"738db47142e785cbd37db7ca0c9a26089fcce784674fc501b8fa067e8f2fe8e9"}


class Settings(BaseSettings):
    app_name: str = "AirSpace API"
    environment: str = "development"
    database_url: str = "sqlite:///./airspace.db"
    # No default on purpose. In development an ephemeral secret is generated
    # (tokens stop working on restart). Production must set JWT_SECRET.
    jwt_secret: str | None = None
    jwt_expire_minutes: int = 60 * 24 * 7
    cors_origins: str = "http://localhost:3000,http://localhost:5173,https://air-space-frontend-nine.vercel.app"
    # Chat / reflection / reframe run on DeepSeek (OpenAI-compatible API).
    deepseek_api_key: str | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    # "deepseek-chat" / "deepseek-reasoner" were retired on 2026-07-24; use the V4 names.
    deepseek_model: str = "deepseek-v4-flash"
    # DeepSeek has no speech-to-text API, so voice vent transcription uses ElevenLabs Scribe.
    # Optional; without this key, voice vent reports "unavailable" and the client falls back to on-device speech recognition.
    elevenlabs_api_key: str | None = None
    elevenlabs_base_url: str = "https://api.elevenlabs.io"
    elevenlabs_stt_model: str = "scribe_v2"
    max_audio_bytes: int = 10 * 1024 * 1024  # keep uploads small to cap cost and memory
    # Verified local support contacts appended to the crisis message
    # (can be a JSON array of CrisisResource objects, or plain text contacts).
    crisis_resources: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    @property
    def ai_enabled(self) -> bool:
        """Text AI (reframe, chat, voice replies) is available."""
        return bool(self.deepseek_api_key)

    @property
    def transcription_enabled(self) -> bool:
        """Server-side speech-to-text (voice vent) is available."""
        return bool(self.elevenlabs_api_key)

    @model_validator(mode="after")
    def validate_settings(self):
        is_prod = self.environment.lower() == "production"
        secret = self.jwt_secret
        if is_prod:
            if (
                not secret
                or secret.startswith(("CHANGE_ME", "replace-with"))
                or len(secret) < 32
                or hashlib.sha256(secret.encode()).hexdigest() in REVOKED_SECRET_SHA256
            ):
                raise ValueError("Production requires a unique JWT_SECRET of at least 32 characters.")
            if not self.database_url.startswith(("postgresql://", "postgresql+psycopg://", "postgres://")):
                raise ValueError("Production must use PostgreSQL; SQLite is for local development only.")
            if not self.cors_origins.strip():
                raise ValueError("CORS_ORIGINS must contain the frontend origin.")
        elif not secret:
            self.jwt_secret = secrets.token_urlsafe(48)
        return self


settings = Settings()
