import asyncio
import logging
import uuid
from typing import Never

from backend.resilience.circuit_breaker import CircuitBreaker, CircuitOpenError
from backend.resilience.rate_limiter import RateLimitExceeded, rate_limiter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test-resilience")

async def test_circuit_breaker() -> None:
    logger.info("--- Testing Circuit Breaker ---")
    breaker_name = f"test_provider_{uuid.uuid4().hex[:6]}"
    
    # Mock a function that always fails
    async def failing_api_call() -> Never:
        raise ValueError("Simulated Provider Error")
        
    # Trip the breaker by failing exactly 5 times
    for i in range(5):
        try:
            async with CircuitBreaker(breaker_name, failure_threshold=5):
                await failing_api_call()
        except ValueError:
            logger.info(f"Call {i+1} failed as expected.")
            
    # The 6th call should immediately raise CircuitOpenError before even trying the API
    logger.info("Attempting 6th call. This should be blocked by the Circuit Breaker.")
    try:
        async with CircuitBreaker(breaker_name, failure_threshold=5):
            await failing_api_call()
        assert False, "Circuit Breaker failed to open!"
    except CircuitOpenError:
        logger.info("Success: Circuit Breaker properly OPENED on the 6th call!")
        
async def test_token_bucket() -> None:
    logger.info("--- Testing Token Bucket (Rate Limiter) ---")
    bucket_key = f"test_pipeline_{uuid.uuid4().hex[:6]}"
    
    # Simulate a pipeline with 60 RPM (Replenishes at 1 token per second)
    max_tokens = 60
    refill_rate = 1.0 
    
    # Send 60 rapid requests. They should all succeed because the bucket starts full.
    success_count = 0
    for _ in range(60):
        await rate_limiter.check_token_bucket(bucket_key, max_tokens, refill_rate)
        success_count += 1
    logger.info(f"Sent {success_count} requests successfully.")
    
    # Send the 61st request immediately. It should fail because refill is only 1/sec.
    try:
        await rate_limiter.check_token_bucket(bucket_key, max_tokens, refill_rate)
        assert False, "Token bucket allowed request beyond its maximum capacity!"
    except RateLimitExceeded as e:
        logger.info(f"Success: Token bucket accurately blocked the 61st request with a 429! (Retry after {e.retry_after}s)")  # noqa: E501

async def main() -> None:
    await test_circuit_breaker()
    await test_token_bucket()
    
if __name__ == "__main__":
    asyncio.run(main())
