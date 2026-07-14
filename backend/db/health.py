import time
import logging
import asyncpg
import redis.asyncio as aioredis
import httpx
from backend.db.pool import get_pool
from backend.config import settings

logger = logging.getLogger(__name__)

async def check_postgres() -> dict:
    """
    Verifies database connection and returns status with latency.
    """
    start = time.time()
    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            val = await conn.fetchval("SELECT 1")
            if val == 1:
                latency = int((time.time() - start) * 1000)
                return {"status": "ok", "latency_ms": latency}
            return {"status": "error"}
    except Exception as e:
        logger.error(f"Postgres health check failed: {e}")
        return {"status": "error"}

async def check_redis() -> dict:
    """
    Verifies Redis connection and returns status with latency.
    """
    start = time.time()
    client = None
    try:
        client = aioredis.from_url(settings.redis_url, socket_timeout=2.0)
        pong = await client.ping()
        if pong is True:
            latency = int((time.time() - start) * 1000)
            return {"status": "ok", "latency_ms": latency}
        return {"status": "error"}
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        return {"status": "error"}
    finally:
        if client is not None:
            await client.aclose()

async def check_mlflow() -> dict:
    """
    Verifies MLflow service connection and returns status with latency.
    """
    start = time.time()
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(
                f"{settings.mlflow_tracking_uri}/", 
                headers={"Host": "localhost"}
            )
            if response.status_code < 500:
                latency = int((time.time() - start) * 1000)
                return {"status": "ok", "latency_ms": latency}
            return {"status": "error"}
    except Exception as e:
        logger.error(f"MLflow health check failed: {e}")
        return {"status": "error"}
