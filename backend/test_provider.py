import asyncio
import json
import logging
import os
import sys
import time

# Ensure backend directory is in python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import openai
import redis.asyncio as aioredis
from backend.providers.base import ChatMessage
from backend.providers.openai_provider import OpenAIProvider
from backend.providers.anthropic_provider import AnthropicProvider
from backend.providers.router import ModelRouter, RoutingCriteria
from backend.providers.client import NeuroFlowClient

# Configure logging to stdout
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("test-provider")

async def test_streaming_and_embeddings():
    print("\n--- 1. Testing Streaming and Embeddings (Mock Mode) ---")
    
    # Instantiate providers in mock mode
    openai_prov = OpenAIProvider(model_name="gpt-4o-mini", api_key="mock")
    anthropic_prov = AnthropicProvider(model_name="claude-3-5-sonnet", api_key="mock")
    
    messages = [ChatMessage(role="user", content="Say one word")]
    
    print("\nTesting OpenAI Streaming:")
    print("Tokens streamed: ", end="")
    async for token in openai_prov.stream(messages):
        print(token, end="", flush=True)
    print()
    
    print("\nTesting Anthropic Streaming:")
    print("Tokens streamed: ", end="")
    async for token in anthropic_prov.stream(messages):
        print(token, end="", flush=True)
    print()

    print("\nTesting OpenAI Embedding:")
    embeddings = await openai_prov.embed(["hello world"])
    print(f"Generated {len(embeddings)} embedding(s) of length {len(embeddings[0])}")

async def test_rate_limiting_retry():
    print("\n--- 2. Testing Rate Limiting Retry Logic (Exponential Backoff) ---")
    
    import httpx
    
    # Initialize real mode provider with fake credentials for override testing
    prov = OpenAIProvider(model_name="gpt-4o-mini", api_key="fake-test-key")
    
    attempts = 0
    
    async def mock_chat_create(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            # Construct a simulated 429 response with a custom retry-after header
            request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
            response = httpx.Response(429, request=request, headers={"retry-after": "1"})
            print(f"[Mock Server] Attempt {attempts}: Raising 429 RateLimitError (suggesting 1s wait)")
            raise openai.RateLimitError("Rate limit exceeded mock", response=response, body=None)
        
        # Successful mock response on the 3rd attempt
        class Usage:
            prompt_tokens = 10
            completion_tokens = 5
        class Choice:
            class Message:
                content = "Success after retries!"
            message = Message()
            finish_reason = "stop"
        class ResponseObj:
            choices = [Choice()]
            usage = Usage()
            
        print(f"[Mock Server] Attempt {attempts}: Success!")
        return ResponseObj()

    # Inject the mock method directly into the client
    prov.client.chat.completions.create = mock_chat_create
    
    messages = [ChatMessage(role="user", content="Test rate limits")]
    start_time = time.time()
    result = await prov.complete(messages)
    duration = time.time() - start_time
    
    print(f"Result: {result.content}")
    print(f"Total attempts: {attempts} (Expected 3)")
    print(f"Total test duration: {duration:.2f}s (Expected slightly > 2s due to 1s backoff + latency)")
    assert attempts == 3, "Rate limiting retry logic did not retry the expected number of times."
    assert result.content == "Success after retries!"

async def test_router_rules(redis_url: str):
    print("\n--- 3. Testing Model Router Rules ---")
    
    # 1. Register model configs in Redis to test rules dynamically
    try:
        client = aioredis.from_url(redis_url, socket_timeout=2.0)
        # Store model configs under key 'router:models'
        models = [
            {
                "model_id": "gpt-4o-mini",
                "provider": "openai",
                "input_cost_per_million": 0.15,
                "output_cost_per_million": 0.60,
                "context_window": 16000,  # Smaller context to test >100k filtering
                "supports_vision": True,
                "supports_task_types": ["rag_generation", "classification", "embedding"],
                "is_fine_tuned": False,
                "fine_tuned_for_task": None
            },
            {
                "model_id": "claude-3-5-sonnet",
                "provider": "anthropic",
                "input_cost_per_million": 3.00,
                "output_cost_per_million": 15.00,
                "context_window": 200000,
                "supports_vision": True,
                "supports_task_types": ["rag_generation", "evaluation", "embedding"],
                "is_fine_tuned": False,
                "fine_tuned_for_task": None
            },
            {
                "model_id": "fine-tuned-rag-model",
                "provider": "openai",
                "input_cost_per_million": 0.50,
                "output_cost_per_million": 2.00,
                "context_window": 8192,
                "supports_vision": False,
                "supports_task_types": ["rag_generation", "embedding"],
                "is_fine_tuned": True,
                "fine_tuned_for_task": "rag_generation"
            }
        ]
        await client.set("router:models", json.dumps(models))
        await client.aclose()
        print("Model configuration written to Redis.")
    except Exception as e:
        print(f"Skipping Redis write (Redis might be offline): {e}")
        return

    router = ModelRouter(redis_url)

    # Test Rule 1: Vision Model
    res1 = await router.route(RoutingCriteria(task_type="rag_generation", require_vision=True))
    print(f"Rule 1 (Vision=True) routed to: {res1['model_id']} (Expected: cheapest vision-capable)")
    
    # Test Rule 2: Long Context (>100k)
    res2 = await router.route(RoutingCriteria(task_type="rag_generation", require_long_context=True))
    print(f"Rule 2 (Long Context=True) routed to: {res2['model_id']} (Expected: claude-3-5-sonnet)")

    # Test Rule 3: Prefer Fine-tuned
    res3 = await router.route(RoutingCriteria(task_type="rag_generation", prefer_fine_tuned=True))
    print(f"Rule 3 (Prefer Fine-tuned=True) routed to: {res3['model_id']} (Expected: fine-tuned-rag-model)")

    # Test Rule 4: Evaluation ignores Fine-tuned
    res4 = await router.route(RoutingCriteria(task_type="evaluation", prefer_fine_tuned=True))
    print(f"Rule 4 (task_type=evaluation, prefer_fine_tuned=True) routed to: {res4['model_id']} (Expected: claude-3-5-sonnet)")

    # Test Rule 5: Max cost limits
    res5 = await router.route(RoutingCriteria(task_type="rag_generation", max_cost_per_call=0.001))
    print(f"Rule 5 (max_cost=0.001) routed to: {res5['model_id']} (Expected: gpt-4o-mini)")

async def test_client_wrapper_and_redis_counters(redis_url: str):
    print("\n--- 4. Testing Client Wrapper and Redis cost counters ---")
    
    try:
        # Clear existing counters
        client = aioredis.from_url(redis_url, socket_timeout=2.0)
        await client.delete("metrics:model:gpt-4o-mini:calls")
        await client.delete("metrics:model:gpt-4o-mini:cost_usd")
        await client.aclose()
    except Exception as e:
        print(f"Skipping Redis clear: {e}")
        return

    # Use singleton client wrapper
    nf_client = NeuroFlowClient(redis_url=redis_url)
    
    # Trigger a chat request
    messages = [ChatMessage(role="user", content="Compute RAG statistics")]
    criteria = RoutingCriteria(task_type="rag_generation", max_cost_per_call=0.01)
    
    print("Calling client.chat()...")
    result = await nf_client.chat(messages, criteria)
    print(f"Generated result content: {result.content}")
    print(f"Model used: {result.model}")
    print(f"Cost recorded in result: ${result.cost_usd:.8f}")

    # Read the updated metrics in Redis
    client = aioredis.from_url(redis_url, socket_timeout=2.0)
    calls = await client.get("metrics:model:gpt-4o-mini:calls")
    cost = await client.get("metrics:model:gpt-4o-mini:cost_usd")
    await client.aclose()
    
    print(f"Redis calls counter: {int(calls) if calls else 0} (Expected: 1)")
    print(f"Redis cost counter: ${float(cost):.8f} if cost else $0.00 (Expected: matches model cost)")
    
    assert int(calls) == 1, "Redis calls counter did not increment properly."

async def main():
    # Use localhost Redis when running script locally outside Docker
    # Check if REDIS_HOST env var is set, else default to localhost
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", 6379))
    redis_password = os.getenv("REDIS_PASSWORD", "redis_secure_pwd")
    redis_url = f"redis://:{redis_password}@{redis_host}:{redis_port}/0"

    await test_streaming_and_embeddings()
    await test_rate_limiting_retry()
    await test_router_rules(redis_url)
    await test_client_wrapper_and_redis_counters(redis_url)

if __name__ == "__main__":
    asyncio.run(main())
