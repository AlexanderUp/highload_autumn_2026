from contextlib import asynccontextmanager

from fastapi import FastAPI
from redis.asyncio import Redis

from api.v1 import health, items
from core import redis
from core.config import settings
from core.logger import get_logger

logger = get_logger(settings.project_name)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Service starting...")
    redis.redis = Redis(
        host=settings.redis.host,
        port=settings.redis.port,
        password=settings.redis.password,
    )
    logger.info("Service started.")

    yield

    logger.info("Service stopping...")
    await redis.redis.close()
    logger.info("Service stopped.")


app = FastAPI(
    title=settings.project_name,
    docs_url="/api/openapi",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)


app.include_router(health.router)
app.include_router(items.router)
