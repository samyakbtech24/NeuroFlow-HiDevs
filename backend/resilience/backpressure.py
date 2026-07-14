import logging
from fastapi import HTTPException
import redis.asyncio as aioredis
from backend.config import settings

logger = logging.getLogger("backpressure")

async def check_ingestion_backpressure():
    """
    Checks the current depth of the ingestion queue.
    If > 100: Raises 503 Service Unavailable to reject the request.
    If > 50: Returns a warning dictionary to merge into the 202 response.
    Otherwise: Returns a normal OK status.
    """
    redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    depth = await redis.llen("queue:ingest")
    
    if depth > 100:
        logger.error(f"Ingestion queue full! Depth: {depth}. Rejecting request.")
        # We raise an HTTPException which the router will catch, or we can configure a custom handler.
        # To match the exact JSON structure in the instructions, we can use a custom exception, 
        # but for simplicity we'll pass the dict as the detail.
        raise HTTPException(
            status_code=503,
            detail={
                "error": "ingestion_queue_full",
                "queue_depth": depth,
                "retry_after": 30
            }
        )
    
    if depth > 50:
        logger.warning(f"Ingestion queue high! Depth: {depth}.")
        return {
            "warning": "high_queue_depth",
            "estimated_wait_minutes": depth  # Simple heuristic: 1 minute per item
        }
        
    return None
