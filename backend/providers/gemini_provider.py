import logging
from typing import cast

from backend.providers.openai_provider import OpenAIProvider

logger = logging.getLogger("gemini-provider")

class GeminiProvider(OpenAIProvider):
    """
    LLM provider integration for Google Gemini models via Google's
    OpenAI-compatibility layer. Inherits all streaming, completion,
    and retry mechanics from OpenAIProvider.
    
    gemini-2.0-flash is FREE on Google AI Studio (no per-token billing).
    """
    
    def __init__(self, model_name: str, api_key: str) -> None:
        super().__init__(model_name=model_name, api_key=api_key)
        
        # Override client to point to Google GenAI endpoint if not in Mock mode
        if not self.is_mock:
            from openai import AsyncOpenAI
            self.client = AsyncOpenAI(
                api_key=api_key,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
            )

        # Override cost to $0 — gemini-flash-latest is on the FREE TIER (no billing)
        # It is Google's rolling alias that always resolves to the current recommended free Flash model.  # noqa: E501
        # Store as private attrs so we can override the parent's read-only @property
        if "gemini-flash" in model_name or "gemini-3" in model_name:
            self._input_cost = 0.0
            self._output_cost = 0.0
        else:
            self._input_cost = cast(float, None)  # noqa: F821
            self._output_cost = cast(float, None)  # noqa: F821

    @property
    def cost_per_input_token(self) -> float:
        if self._input_cost is not None:
            return self._input_cost
        return super().cost_per_input_token

    @cost_per_input_token.setter
    def cost_per_input_token(self, value: float) -> None:
        self._input_cost = value

    @property
    def cost_per_output_token(self) -> float:
        if self._output_cost is not None:
            return self._output_cost
        return super().cost_per_output_token

    @cost_per_output_token.setter
    def cost_per_output_token(self, value: float) -> None:
        self._output_cost = value
