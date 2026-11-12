from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")
    database_host: str = "postgres"
    database_port: int = Field(default=5432, ge=1, le=65535)
    database_name: str = "flood"
    database_user: str = "telemetry_svc"
    database_password_file: Path = Path("/run/secrets/telemetry_db_password")
    redis_host: str = "redis"
    redis_port: int = Field(default=6379, ge=1, le=65535)
    redis_password_file: Path = Path("/run/secrets/redis_password")
    mqtt_host: str = "mosquitto"
    mqtt_port: int = Field(default=8883, ge=1, le=65535)
    mqtt_username: str = "svc-telemetry"
    mqtt_password_file: Path = Path("/run/secrets/mqtt_telemetry_password")
    mqtt_ca_file: Path = Path("/run/secrets/ca.crt")
    jwt_public_key_file: Path = Path("/run/secrets/jwt_public.pem")
    max_msgs_per_device_per_min: int = Field(default=10, ge=1)
    open_meteo_enabled: bool = True
    enforce_mfa: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    environment: Literal["dev", "prod"] = "dev"

    def database_url(self) -> URL:
        return URL.create(
            "postgresql+asyncpg",
            username=self.database_user,
            password=read_secret(self.database_password_file).get_secret_value(),
            host=self.database_host,
            port=self.database_port,
            database=self.database_name,
        )


def read_secret(path: Path) -> SecretStr:
    value = path.read_text().strip()
    if not value:
        raise ValueError("Empty secret file")
    return SecretStr(value)
