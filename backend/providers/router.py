import json
import logging
from dataclasses import dataclass
from typing import List, Optional
import redis.asyncio as aioredis
from backend.config import settings

logger = logging.getLogger("model-router")

@dataclass
class RoutingCriteria:
    """
    Defines the requirements for a model routing request.
    task_type: Type of task, e.g. "rag_generation", "evaluation", "embedding", "classification".
    max_cost_per_call: Optional maximum allowed cost in USD for this call.
    require_vision: Whether the model needs to support image/vision processing.
    require_long_context: Whether the model needs to support context > 32k tokens.
    latency_budget_ms: Optional budget limit for latency.
    prefer_fine_tuned: Whether to prefer a fine-tuned model if available.
    """
    task_type: str
    max_cost_per_call: Optional[float] = None
    require_vision: bool = False
    require_long_context: bool = False
    latency_budget_ms: Optional[int] = None
    prefer_fine_tuned: bool = False

# Default models configuration to fallback on if Redis is empty
DEFAULT_MODELS = [
    {
        "model_id": "gpt-4o-mini",
        "provider": "openai",
        "input_cost_per_million": 0.15,
        "output_cost_per_million": 0.60,
        "context_window": 128000,
        "supports_vision": True,
        "supports_task_types": ["rag_generation", "classification", "evaluation", "embedding"],
        "is_fine_tuned": False,
        "fine_tuned_for_task": None
    },
    {
        "model_id": "gpt-4o",
        "provider": "openai",
        "input_cost_per_million": 2.50,
        "output_cost_per_million": 10.00,
        "context_window": 128000,
        "supports_vision": True,
        "supports_task_types": ["rag_generation", "classification", "evaluation", "embedding"],
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
    }
]

class ModelRouter:
    """
    Decides which model and provider combination should handle a given LLM request.
    Reads registered models dynamically from Redis key 'router:models'.
    """
    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = redis_url or settings.redis_url

    async def _get_models(self) -> List[dict]:
        """
        Retrieves the registered models list from Redis.
        Falls back to default models if Redis key is not set or fails.
        """
        try:
            client = aioredis.from_url(self.redis_url, socket_timeout=2.0)
            data = await client.get("router:models")
            await client.aclose()
            
            if data:
                return json.loads(data)
        except Exception as e:
            logger.error(f"Error fetching models from Redis: {e}. Falling back to default models.")
            
        return DEFAULT_MODELS

    async def route(self, criteria: RoutingCriteria) -> dict:
        """
        Routes the request to the best model using the 6 routing rules:
        1. If require_vision=True -> route to vision-capable model.
        2. If require_long_context=True -> route to model with context > 100k.
        3. If prefer_fine_tuned=True and fine-tuned model matches task -> route to it.
        4. If task_type="evaluation" -> never use a fine-tuned model.
        5. If max_cost_per_call is set -> filter out models exceeding cost for an estimated call.
        6. Default: route to the cheapest model that satisfies constraints.
        """
        models = await self._get_models()
        
        # Hard constraint: Model must support the requested task type
        candidates = [m for m in models if criteria.task_type in m.get("supports_task_types", [])]

        # Rule 1: Vision Capable Check
        if criteria.require_vision:
            candidates = [m for m in candidates if m.get("supports_vision", False)]

        # Rule 2: Long Context Check (>100k context window)
        if criteria.require_long_context:
            candidates = [m for m in candidates if m.get("context_window", 0) > 100000]

        # Rules 3 & 4: Fine-tuning routing logic
        if criteria.task_type == "evaluation":
            # Never use a fine-tuned model for evaluation
            candidates = [m for m in candidates if not m.get("is_fine_tuned", False)]
        elif criteria.prefer_fine_tuned:
            # Filter for fine-tuned models matching this specific task type
            fine_tuned = [
                m for m in candidates 
                if m.get("is_fine_tuned", False) and m.get("fine_tuned_for_task") == criteria.task_type
            ]
            if fine_tuned:
                candidates = fine_tuned

        # Rule 5: Cost limits check
        # We estimate an average call cost using 2000 input tokens and 500 output tokens
        if criteria.max_cost_per_call is not None:
            filtered = []
            for m in candidates:
                input_rate = m.get("input_cost_per_million", 0.0) / 1_000_000.0
                output_rate = m.get("output_cost_per_million", 0.0) / 1_000_000.0
                estimated_cost = (2000 * input_rate) + (500 * output_rate)
                
                if estimated_cost <= criteria.max_cost_per_call:
                    filtered.append(m)
            candidates = filtered

        # Handle edge case where no candidate satisfies all criteria
        if not candidates:
            logger.warning("No registered models satisfied all routing criteria. Falling back to gpt-4o-mini.")
            for fallback in DEFAULT_MODELS:
                if fallback["model_id"] == "gpt-4o-mini":
                    return fallback
            return DEFAULT_MODELS[0]

        # Rule 6: Select the cheapest model among remaining candidates
        def get_estimated_cost(m):
            input_rate = m.get("input_cost_per_million", 0.0) / 1_000_000.0
            output_rate = m.get("output_cost_per_million", 0.0) / 1_000_000.0
            return (2000 * input_rate) + (500 * output_rate)

        candidates.sort(key=get_estimated_cost)
        return candidates[0]
