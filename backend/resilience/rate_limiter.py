import time
import uuid
import logging
import redis.asyncio as aioredis
from fastapi import HTTPException
from backend.config import settings

logger = logging.getLogger("rate_limiter")

class RateLimitExceeded(Exception):
    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded. Try again in {retry_after} seconds.")

# Lua script for atomic Token Bucket logic
TOKEN_BUCKET_LUA = """
local tokens_key = KEYS[1]
local timestamp_key = KEYS[2]
local max_tokens = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local requested = tonumber(ARGV[4])

local current_tokens = redis.call('get', tokens_key)
local last_update = redis.call('get', timestamp_key)

if current_tokens == false then
    current_tokens = max_tokens
    last_update = now
else
    current_tokens = tonumber(current_tokens)
    last_update = tonumber(last_update)
end

local time_passed = now - last_update
local new_tokens = math.floor(time_passed * refill_rate)

if new_tokens > 0 then
    current_tokens = math.min(max_tokens, current_tokens + new_tokens)
    last_update = now
end

if current_tokens >= requested then
    current_tokens = current_tokens - requested
    redis.call('set', tokens_key, current_tokens)
    redis.call('set', timestamp_key, last_update)
    return 1
else
    if new_tokens > 0 then
        redis.call('set', tokens_key, current_tokens)
        redis.call('set', timestamp_key, last_update)
    end
    return 0
end
"""

class RateLimiter:
    def __init__(self):
        self.redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        
    async def check_token_bucket(self, key: str, max_tokens: int, refill_rate_per_sec: float, requested: int = 1):
        """
        Token bucket algorithm. 
        """
        now = time.time()
        tokens_key = f"rpb:{key}:tokens"
        timestamp_key = f"rpb:{key}:last_update"
        
        allowed = await self.redis.eval(
            TOKEN_BUCKET_LUA,
            2,
            tokens_key,
            timestamp_key,
            max_tokens,
            refill_rate_per_sec,
            now,
            requested
        )
        
        if not allowed:
            # Calculate retry after based on how long it takes to get 'requested' tokens
            retry_after = max(1, int(requested / refill_rate_per_sec))
            logger.warning(f"Token bucket empty for {key}. Denying request.")
            raise RateLimitExceeded(retry_after)
            
    async def check_sliding_window(self, key: str, limit: int, window_seconds: int):
        """
        Sliding window using a Redis Sorted Set.
        """
        now = time.time()
        window_start = now - window_seconds
        redis_key = f"sliding:{key}"
        
        # Start a pipeline to do this atomically
        pipe = self.redis.pipeline()
        
        # 1. Remove old requests outside the window
        pipe.zremrangebyscore(redis_key, "-inf", window_start)
        
        # 2. Count current requests in the window
        pipe.zcard(redis_key)
        
        # 3. Add the current request (with a unique UUID member to avoid overwrites)
        # We only add it if we are under the limit, but we don't know the count yet in a pipe.
        # So we add it unconditionally, then check, then remove if it breached.
        req_id = str(uuid.uuid4())
        pipe.zadd(redis_key, {req_id: now})
        
        # 4. Set expiry to clean up memory
        pipe.expire(redis_key, window_seconds)
        
        results = await pipe.execute()
        current_count = results[1] # Result of zcard before our addition
        
        if current_count >= limit:
            # We exceeded the limit, so remove the token we just added
            await self.redis.zrem(redis_key, req_id)
            # Find out when the oldest token expires
            oldest_tokens = await self.redis.zrange(redis_key, 0, 0, withscores=True)
            if oldest_tokens:
                oldest_timestamp = oldest_tokens[0][1]
                retry_after = max(1, int((oldest_timestamp + window_seconds) - now))
            else:
                retry_after = 1
                
            raise HTTPException(
                status_code=429,
                detail="Too Many Requests",
                headers={"Retry-After": str(retry_after)}
            )
            
rate_limiter = RateLimiter()
