from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "AirSpace API"
    environment: str = "development"
    database_url: str = "sqlite:///./airspace.db"
    jwt_secret: str = "CHANGE_ME_BEFORE_DEPLOYMENT_TO_A_LONG_RANDOM_SECRET"
    jwt_expire_minutes: int = 60 * 24 * 7
    cors_origins: str = "http://localhost:3000,http://localhost:5173"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    # Raw vent text is not persisted by default.
    persist_vent_text: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
