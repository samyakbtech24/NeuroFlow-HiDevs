import logging
import os
import time
from collections.abc import AsyncGenerator

import redis.asyncio as aioredis

from backend.config import settings
from backend.providers.anthropic_provider import AnthropicProvider
from backend.providers.base import ChatMessage, GenerationResult
from backend.providers.gemini_provider import GeminiProvider
from backend.providers.openai_provider import OpenAIProvider
from backend.providers.router import ModelRouter, RoutingCriteria
from backend.resilience.circuit_breaker import CircuitBreaker
from backend.resilience.rate_limiter import rate_limiter
from backend.resilience.timeout_manager import timeout_manager

logger = logging.getLogger("neuroflow-client")

# Attempt to configure OpenTelemetry Tracing
try:
    from opentelemetry import trace
    tracer = trace.get_tracer("neuroflow-client")
except ImportError:
    tracer = None
    logger.warning("OpenTelemetry trace library not available. Provider call tracing is disabled.")

class NeuroFlowClient:
    """
    Singleton wrapper client for NeuroFlow LLM operations.
    Handles dynamic model routing, metrics logging to Redis, and OpenTelemetry tracing.
    """
    _instance = None

    def __new__(cls, *args, **kwargs):  # noqa: ANN002, ANN003, ANN204  # type: ignore
        if not cls._instance:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False  # type: ignore
        return cls._instance

    def __init__(self, redis_url: str | None = None) -> None:
        if self._initialized:  # type: ignore
            return
            
        self.redis_url = redis_url or settings.redis_url
        self.router = ModelRouter(self.redis_url)
        
        # Load API keys from environment variables (fallback to "mock" for free runs)
        self.openai_key = os.getenv("OPENAI_API_KEY", "mock")
        self.anthropic_key = os.getenv("ANTHROPIC_API_KEY", "mock")
        self.gemini_key = os.getenv("GEMINI_API_KEY", "mock")
        
        # Cache for provider instances (e.g. {"openai": {"gpt-4o-mini": <instance>}})
        self.providers = {  # type: ignore
            "openai": {},
            "anthropic": {},
            "gemini": {}
        }
        self._initialized = True

    def _get_provider(self, provider_name: str, model_name: str):  # noqa: ANN202  # type: ignore
        """
        Retrieves an existing provider instance or creates a new one.
        """
        if provider_name == "openai":
            if model_name not in self.providers["openai"]:
                self.providers["openai"][model_name] = OpenAIProvider(
                    model_name=model_name,
                    api_key=self.openai_key
                )
            return self.providers["openai"][model_name]
            
        elif provider_name == "anthropic":
            if model_name not in self.providers["anthropic"]:
                self.providers["anthropic"][model_name] = AnthropicProvider(
                    model_name=model_name,
                    api_key=self.anthropic_key
                )
            return self.providers["anthropic"][model_name]
            
        elif provider_name == "gemini":
            if model_name not in self.providers["gemini"]:
                self.providers["gemini"][model_name] = GeminiProvider(
                    model_name=model_name,
                    api_key=self.gemini_key
                )
            return self.providers["gemini"][model_name]
            
        else:
            raise ValueError(f"Unsupported provider: {provider_name}")

    async def _track_metrics(self, model_name: str, cost_usd: float) -> None:
        """
        Increments call counts and costs for a model in Redis.
        """
        try:
            client = aioredis.from_url(self.redis_url, socket_timeout=2.0)
            # Increment call count
            await client.incr(f"metrics:model:{model_name}:calls")
            # Increment cumulative cost
            await client.incrbyfloat(f"metrics:model:{model_name}:cost_usd", cost_usd)
            await client.aclose()
        except Exception as e:
            logger.error(f"Error tracking metrics in Redis: {e}")

    async def chat(self, messages: list[ChatMessage], routing_criteria: RoutingCriteria) -> GenerationResult:  # noqa: E501
        """
        Routes the chat request to the best model, executes it, logs cost to Redis, and registers tracing.
        """  # noqa: E501
        # 1. Select provider and model using routing rules
        model_config = await self.router.route(routing_criteria)
        provider_name = model_config["provider"]
        model_id = model_config["model_id"]
        
        # 2. Retrieve appropriate provider instance
        provider = self._get_provider(provider_name, model_id)
        
        # 3. Apply Resilience Layers (Rate Limiting, Circuit Breaker, Timeouts)
        
        # Check Token Bucket Limits (NeuroFlow global rate limit)
        if provider_name == "openai":
            await rate_limiter.check_token_bucket("openai", max_tokens=3000, refill_rate_per_sec=50.0)  # noqa: E501
        elif provider_name == "anthropic":
            await rate_limiter.check_token_bucket("anthropic", max_tokens=1000, refill_rate_per_sec=20.0)  # noqa: E501
        
        task_type = routing_criteria.task_type
        if task_type == "rag_generation":
            task_type = "chat_completion"  # Map to our standard timeout dictionary key
            
        async with CircuitBreaker(provider_name):
            coro = provider.complete(messages)
            
            if tracer:
                with tracer.start_as_current_span("neuroflow_chat") as span:
                    span.set_attribute("model", model_id)
                    
                    result = await timeout_manager.run_with_timeout(task_type, coro)
                    
                    span.set_attribute("input_tokens", result.input_tokens)
                    span.set_attribute("output_tokens", result.output_tokens)
                    span.set_attribute("cost_usd", result.cost_usd)
                    span.set_attribute("latency_ms", result.latency_ms)
            else:
                result = await timeout_manager.run_with_timeout(task_type, coro)
            
        # 4. Log call statistics to Redis asynchronously
        await self._track_metrics(model_id, result.cost_usd)
        
        return result  # type: ignore

    async def stream(self, messages: list[ChatMessage], routing_criteria: RoutingCriteria) -> AsyncGenerator[str, None]:  # noqa: E501
        """
        Routes the stream request to the best model and returns its token generator stream.
        """
        # 1. Select provider and model using routing rules
        model_config = await self.router.route(routing_criteria)
        provider_name = model_config["provider"]
        model_id = model_config["model_id"]
        
        # 2. Retrieve appropriate provider instance
        provider = self._get_provider(provider_name, model_id)
        
        # 3. Apply Resilience Layers
        if provider_name == "openai":
            await rate_limiter.check_token_bucket("openai", max_tokens=3000, refill_rate_per_sec=50.0)  # noqa: E501
        elif provider_name == "anthropic":
            await rate_limiter.check_token_bucket("anthropic", max_tokens=1000, refill_rate_per_sec=20.0)  # noqa: E501
            
        async with CircuitBreaker(provider_name):
            async for token in provider.stream(messages):
                yield token

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """
        Routes and executes embedding requests.
        """
        # 1. Select provider and model (uses default embedding routing criteria)
        criteria = RoutingCriteria(task_type="embedding")
        model_config = await self.router.route(criteria)
        provider_name = model_config["provider"]
        model_id = model_config["model_id"]
        
        # 2. Retrieve appropriate provider instance
        provider = self._get_provider(provider_name, model_id)
        
        start_time = time.time()
        
        # 3. Apply Resilience Layers
        if provider_name == "openai":
            await rate_limiter.check_token_bucket("openai", max_tokens=3000, refill_rate_per_sec=50.0)  # noqa: E501
            
        async with CircuitBreaker(provider_name):
            coro = provider.embed(texts)
            
            if tracer:
                with tracer.start_as_current_span("neuroflow_embed") as span:
                    span.set_attribute("model", model_id)
                    span.set_attribute("text_count", len(texts))
                    
                    embeddings = await timeout_manager.run_with_timeout("embedding", coro)
                    
                    latency_ms = (time.time() - start_time) * 1000
                    span.set_attribute("latency_ms", latency_ms)
            else:
                embeddings = await timeout_manager.run_with_timeout("embedding", coro)
            
        # 4. Estimate cost for embedding tracking
        # Assume text-embedding-3-small pricing ($0.02 per million tokens)
        total_chars = sum(len(text) for text in texts)
        estimated_tokens = max(1, total_chars // 4)
        cost_usd = (estimated_tokens * 0.02) / 1_000_000.0
        
        # 5. Log statistics to Redis
        await self._track_metrics(model_id, cost_usd)
        
        return embeddings  # type: ignore
