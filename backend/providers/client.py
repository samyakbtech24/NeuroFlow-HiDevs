import logging
import os
import time
from typing import List, Optional, AsyncGenerator
import redis.asyncio as aioredis

from backend.config import settings
from backend.providers.base import ChatMessage, GenerationResult
from backend.providers.openai_provider import OpenAIProvider
from backend.providers.anthropic_provider import AnthropicProvider
from backend.providers.router import ModelRouter, RoutingCriteria

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

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(NeuroFlowClient, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, redis_url: Optional[str] = None):
        if self._initialized:
            return
            
        self.redis_url = redis_url or settings.redis_url
        self.router = ModelRouter(self.redis_url)
        
        # Load API keys from environment variables (fallback to "mock" for free runs)
        self.openai_key = os.getenv("OPENAI_API_KEY", "mock")
        self.anthropic_key = os.getenv("ANTHROPIC_API_KEY", "mock")
        
        # Cache for provider instances (e.g. {"openai": {"gpt-4o-mini": <instance>}})
        self.providers = {
            "openai": {},
            "anthropic": {}
        }
        self._initialized = True

    def _get_provider(self, provider_name: str, model_name: str):
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
            
        else:
            raise ValueError(f"Unsupported provider: {provider_name}")

    async def _track_metrics(self, model_name: str, cost_usd: float):
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

    async def chat(self, messages: List[ChatMessage], routing_criteria: RoutingCriteria) -> GenerationResult:
        """
        Routes the chat request to the best model, executes it, logs cost to Redis, and registers tracing.
        """
        # 1. Select provider and model using routing rules
        model_config = await self.router.route(routing_criteria)
        provider_name = model_config["provider"]
        model_id = model_config["model_id"]
        
        # 2. Retrieve appropriate provider instance
        provider = self._get_provider(provider_name, model_id)
        
        # 3. Call model with OpenTelemetry tracing if available
        if tracer:
            with tracer.start_as_current_span("neuroflow_chat") as span:
                span.set_attribute("model", model_id)
                
                result = await provider.complete(messages)
                
                span.set_attribute("input_tokens", result.input_tokens)
                span.set_attribute("output_tokens", result.output_tokens)
                span.set_attribute("cost_usd", result.cost_usd)
                span.set_attribute("latency_ms", result.latency_ms)
        else:
            result = await provider.complete(messages)
            
        # 4. Log call statistics to Redis asynchronously
        await self._track_metrics(model_id, result.cost_usd)
        
        return result

    async def stream(self, messages: List[ChatMessage], routing_criteria: RoutingCriteria) -> AsyncGenerator[str, None]:
        """
        Routes the stream request to the best model and returns its token generator stream.
        """
        # 1. Select provider and model using routing rules
        model_config = await self.router.route(routing_criteria)
        provider_name = model_config["provider"]
        model_id = model_config["model_id"]
        
        # 2. Retrieve appropriate provider instance
        provider = self._get_provider(provider_name, model_id)
        
        # 3. Stream tokens
        async for token in provider.stream(messages):
            yield token

    async def embed(self, texts: List[str]) -> List[List[float]]:
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
        # 3. Get embeddings with OpenTelemetry tracing if available
        if tracer:
            with tracer.start_as_current_span("neuroflow_embed") as span:
                span.set_attribute("model", model_id)
                span.set_attribute("text_count", len(texts))
                
                embeddings = await provider.embed(texts)
                
                latency_ms = (time.time() - start_time) * 1000
                span.set_attribute("latency_ms", latency_ms)
        else:
            embeddings = await provider.embed(texts)
            latency_ms = (time.time() - start_time) * 1000
            
        # 4. Estimate cost for embedding tracking
        # Assume text-embedding-3-small pricing ($0.02 per million tokens)
        total_chars = sum(len(text) for text in texts)
        estimated_tokens = max(1, total_chars // 4)
        cost_usd = (estimated_tokens * 0.02) / 1_000_000.0
        
        # 5. Log statistics to Redis
        await self._track_metrics(model_id, cost_usd)
        
        return embeddings
