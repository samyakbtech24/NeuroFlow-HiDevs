import asyncio
import logging
from backend.config import settings
from backend.db.pool import init_pool, close_pool

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("worker")

async def main():
    logger.info("Worker starting up...")
    
    # Initialize database pool for background jobs
    await init_pool(settings.database_url)
    
    logger.info("Worker is active and polling for jobs...")
    try:
        while True:
            # Simulated worker polling loop
            await asyncio.sleep(10)
    except asyncio.CancelledError:
        logger.info("Worker shutdown triggered.")
    finally:
        await close_pool()
        logger.info("Worker connection pool shut down.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Worker stopped via KeyboardInterrupt.")
