import asyncio
import logging
import redis.asyncio as aioredis
from backend.config import settings

logger = logging.getLogger("timeout_manager")

class TimeoutManager:
    TIMEOUTS = {
        "embedding": 10,              # seconds
        "chat_completion": 60,
        "reranking": 15,
        "evaluation": 120,            # evaluation is slower (multiple LLM calls)
        "file_extraction": 30,
        "url_fetch": 15
    }

    def __init__(self):
        self.redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        
    async def run_with_timeout(self, task_type: str, coro):
        """
        Executes a coroutine with a strict timeout based on its task type.
        """
        if task_type not in self.TIMEOUTS:
            raise ValueError(f"Unknown task type '{task_type}' provided to TimeoutManager.")
            
        timeout = self.TIMEOUTS[task_type]
        
        try:
            return await asyncio.wait_for(coro, timeout=timeout)
        except asyncio.TimeoutError:
            logger.error(f"Task '{task_type}' timed out after {timeout} seconds!")
            # Increment a counter in Redis for monitoring
            await self.redis.incr(f"timeouts:{task_type}")
            # Re-raise the timeout error to propagate it to the caller
            raise

timeout_manager = TimeoutManager()
