from pydantic import Field
from pydantic_settings import BaseSettings


class RedisSettings(BaseSettings):
    host: str = Field(..., alias="REDIS_HOST")
    port: int = Field(..., alias="REDIS_PORT")
    password: str = Field(..., alias="REDIS_PASSWORD")


class AppSettings(BaseSettings):
    project_name: str = "Highload monitored service"
    log_level: str = Field(..., alias="LOG_LEVEL")

    redis: RedisSettings = RedisSettings()


settings = AppSettings()
