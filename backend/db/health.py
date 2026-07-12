import logging
import asyncpg
import redis.asyncio as aioredis
import httpx
from backend.db.pool import get_pool
from backend.config import settings

logger = logging.getLogger(__name__)

async def check_postgres() -> bool:
    """
    Verifies database connection by checking if the pool is active
    and successfully executing a simple query ('SELECT 1').
    """
    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            val = await conn.fetchval("SELECT 1")
            return val == 1
    except Exception as e:
        logger.error(f"Postgres health check failed: {e}")
        return False

async def check_redis() -> bool:
    """
    Verifies Redis connection by creating a temporary connection client,
    pinging the server, and verifying the pong response.
    """
    client = None
    try:
        client = aioredis.from_url(settings.redis_url, socket_timeout=2.0)
        pong = await client.ping()
        return pong is True
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        return False
    finally:
        if client is not None:
            await client.aclose()

async def check_mlflow() -> bool:
    """
    Verifies MLflow service connection by making an HTTP GET request
    to the configured MLflow tracking URI.
    """
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            # Send Host: localhost to satisfy MLflow security filters
            response = await client.get(
                f"{settings.mlflow_tracking_uri}/", 
                headers={"Host": "localhost"}
            )
            # Status < 500 confirms the server is reachable and active
            return response.status_code < 500
    except Exception as e:
        logger.error(f"MLflow health check failed: {e}")
        return False

