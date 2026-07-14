import time
import logging
import redis.asyncio as aioredis
from backend.config import settings

logger = logging.getLogger("circuit_breaker")

class CircuitOpenError(Exception):
    pass

class CircuitBreaker:
    def __init__(self, name: str, failure_threshold: int = 5, recovery_timeout: int = 60, half_open_max_calls: int = 3):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self.redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        
        # Redis Keys
        self.state_key = f"circuit:{name}:state"
        self.failure_key = f"circuit:{name}:failure_count"
        self.opened_at_key = f"circuit:{name}:opened_at"
        self.half_open_calls_key = f"circuit:{name}:half_open_calls"
        
    async def __aenter__(self):
        state = await self.redis.get(self.state_key) or "closed"
        
        if state == "open":
            opened_at_str = await self.redis.get(self.opened_at_key)
            if opened_at_str:
                opened_at = float(opened_at_str)
                if time.time() - opened_at > self.recovery_timeout:
                    # Timeout has expired, switch to half-open to test
                    await self.redis.set(self.state_key, "half_open")
                    await self.redis.set(self.half_open_calls_key, 1)
                    return self
                else:
                    raise CircuitOpenError(f"Circuit {self.name} is OPEN. Failing fast.")
            else:
                # Fallback if state is open but timestamp is missing
                await self.redis.set(self.state_key, "closed")
                state = "closed"
                
        if state == "half_open":
            calls = await self.redis.incr(self.half_open_calls_key)
            if calls > self.half_open_max_calls:
                raise CircuitOpenError(f"Circuit {self.name} is HALF-OPEN. Too many test attempts.")
                
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            # Call Succeeded
            state = await self.redis.get(self.state_key)
            if state == "half_open":
                # If any succeed -> closed
                logger.info(f"CircuitBreaker [{self.name}]: Test call succeeded. Closing circuit.")
                await self.redis.set(self.state_key, "closed")
                await self.redis.set(self.failure_key, 0)
            elif state == "closed" or state is None:
                # Reset failure count on success
                await self.redis.set(self.failure_key, 0)
        else:
            # Call Failed
            state = await self.redis.get(self.state_key) or "closed"
            if state == "half_open":
                # If any fail while half-open -> trip open again immediately
                logger.warning(f"CircuitBreaker [{self.name}]: Test call failed. Re-opening circuit.")
                await self.redis.set(self.state_key, "open")
                await self.redis.set(self.opened_at_key, time.time())
            else:
                # Normal failure counting
                failures = await self.redis.incr(self.failure_key)
                if failures >= self.failure_threshold:
                    logger.error(f"CircuitBreaker [{self.name}]: Failure threshold reached ({failures}). Tripping OPEN!")
                    await self.redis.set(self.state_key, "open")
                    await self.redis.set(self.opened_at_key, time.time())
        
        # Do not swallow exceptions
        return False
