import json
import logging
from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse
import redis.asyncio as aioredis
from backend.config import settings

logger = logging.getLogger("evaluations-api")
router = APIRouter(prefix="/evaluations", tags=["evaluations"])

@router.get("/stream")
async def stream_evaluations(request: Request):
    """
    Real-time SSE feed of evaluation results from Redis pub/sub.
    """
    async def event_generator():
        redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
        pubsub = redis_client.pubsub()
        await pubsub.subscribe("evaluations:new")
        logger.info("SSE client subscribed to evaluations:new")
        
        try:
            while True:
                if await request.is_disconnected():
                    break
                
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message:
                    yield {"data": message["data"]}
        finally:
            await pubsub.unsubscribe("evaluations:new")
            await redis_client.aclose()
            logger.info("SSE client disconnected from evaluations:new")

    return EventSourceResponse(event_generator())
