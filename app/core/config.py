from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Read from environment variables first, then from a .env file if present.
    # extra="ignore" skips variables we don't use here (e.g. POSTGRES_PASSWORD).
    # hide_input_in_errors keeps values (which include secrets) out of the
    # error message when a setting is missing or invalid.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    database_url: str
    # At least 32 characters, so a short or forgotten placeholder secret
    # stops the app at startup instead of signing guessable tokens
    jwt_secret_key: str = Field(min_length=32)
    jwt_expire_minutes: int = Field(30, ge=1)

    @field_validator("database_url")
    @classmethod
    def use_psycopg_driver(cls, url: str) -> str:
        if not url.strip():
            # e.g. an empty shell variable passed with "-e DATABASE_URL"
            raise ValueError("DATABASE_URL is empty")
        # Hosts such as Neon give URLs starting with postgresql:// (or postgres://).
        # SQLAlchemy reads that as "use psycopg2", which isn't installed, so switch
        # it to psycopg (version 3). Options such as ?sslmode=require are kept.
        for prefix in ("postgresql://", "postgres://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url.removeprefix(prefix)
        return url


settings = Settings()
