from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    upload_dir: Path = Field(default=Path("./uploads"), validation_alias="UPLOAD_DIR")
    port: int = Field(default=8080, validation_alias="PORT")
    secret_key: str = Field(default="change-me-in-production", validation_alias="SECRET_KEY")
    token_max_age_seconds: int = Field(default=86400, validation_alias="TOKEN_MAX_AGE")
    pin_hash: str = Field(default="", validation_alias="PIN_HASH")
    pin_salt: str = Field(default="", validation_alias="PIN_SALT")
    max_upload_mb: int = Field(default=500, validation_alias="MAX_UPLOAD_MB")

    # Optional: for initial setup, script hashes it and outputs PIN_HASH + PIN_SALT
    pin: str | None = Field(default=None, validation_alias="PIN")

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    def get_upload_dir_resolved(self) -> Path:
        """Return absolute path; caller should create dir if missing."""
        return self.upload_dir.resolve()


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
