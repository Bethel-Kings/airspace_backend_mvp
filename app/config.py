from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AirSpace API"
    environment: str = "development"
    database_url: str = "sqlite:///./airspace.db"
    jwt_secret: str = "AGUviUWmrpBSL2IAE_SEFbkRkGOdvyIPXvxD-UpWyTO2aI5nbK61KMT9UTzYva2N"
    jwt_expire_minutes: int = 60 * 24 * 7
    cors_origins: str = "http://localhost:3000,http://localhost:5173"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    @model_validator(mode="after")
    def validate_production_settings(self):
        if self.environment.lower() == "production":
            if not self.jwt_secret or self.jwt_secret.startswith(("CHANGE_ME", "replace-with")) or len(self.jwt_secret) < 32:
                raise ValueError("Production requires a unique JWT_SECRET of at least 32 characters.")
            if not self.database_url.startswith(("postgresql://", "postgresql+psycopg://", "postgres://")):
                raise ValueError("Production must use PostgreSQL; SQLite is for local development only.")
            if not self.cors_origins.strip():
                raise ValueError("CORS_ORIGINS must contain the frontend origin.")
        return self


settings = Settings()
