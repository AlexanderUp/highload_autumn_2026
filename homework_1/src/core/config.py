from pydantic import Field
from pydantic_settings import BaseSettings


class ProjectSettings(BaseSettings):
    name: str = "Highload monitored service"
    log_level: str = Field(..., alias="LOG_LEVEL")


class RedisSettings(BaseSettings):
    host: str = Field(..., alias="REDIS_HOST")
    port: int = Field(..., alias="REDIS_PORT")
    password: str = Field(..., alias="REDIS_PASSWORD")


class AppSettings(BaseSettings):
    project: ProjectSettings = ProjectSettings()
    redis: RedisSettings = RedisSettings()

    pod_id: int = Field(..., alias="POD_ID")
    datacenter: str = Field(..., alias="DATACENTER")


settings = AppSettings()
