import asyncio
import logging

import asyncpg

logger = logging.getLogger(__name__)

# Single global reference to the connection pool
_pool: asyncpg.Pool | None = None

async def init_pool(dsn: str, min_size: int = 5, max_size: int = 20) -> asyncpg.Pool:
    """
    Initializes a global asyncpg connection pool once.
    Includes a retry loop to wait for PostgreSQL server to be ready.
    """
    global _pool
    if _pool is not None:
        logger.warning("Database pool is already initialized.")
        return _pool

    logger.info("Initializing database connection pool...")
    retries = 15
    delay = 2.0
    for attempt in range(1, retries + 1):
        try:
            _pool = await asyncpg.create_pool(
                dsn=dsn,
                min_size=min_size,
                max_size=max_size,
                command_timeout=60.0
            )
            logger.info("Database pool initialized successfully.")
            return _pool
        except Exception as e:
            if attempt == retries:
                logger.error(f"Failed to initialize database pool after {retries} attempts: {e}")
                raise
            logger.warning(f"Database connection attempt {attempt}/{retries} failed. Retrying in {delay}s...")  # noqa: E501
            await asyncio.sleep(delay)


async def close_pool() -> None:
    """
    Closes the global connection pool.
    """
    global _pool
    if _pool is None:
        logger.warning("Database pool is not initialized or already closed.")
        return

    logger.info("Closing database connection pool...")
    await _pool.close()
    _pool = None
    logger.info("Database pool closed successfully.")

def get_pool() -> asyncpg.Pool:
    """
    Returns the active global database connection pool.
    Raises RuntimeError if it has not been initialized.
    """
    if _pool is None:
        raise RuntimeError("Database pool is not initialized. Ensure init_pool was called at startup.")  # noqa: E501
    return _pool
