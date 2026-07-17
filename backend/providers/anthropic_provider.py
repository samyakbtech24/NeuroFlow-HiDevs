import asyncio
import logging
import time
from collections.abc import AsyncGenerator

import anthropic

from backend.providers.base import BaseLLMProvider, ChatMessage, GenerationResult

logger = logging.getLogger("anthropic-provider")

# Hardcoded price table per model (in USD per million tokens)
PRICING = {
    "claude-3-5-sonnet": {"input": 3.00, "output": 15.00},
    "claude-3-5-haiku": {"input": 0.25, "output": 1.25}
}

class AnthropicProvider(BaseLLMProvider):
    def __init__(self, model_name: str = "claude-3-5-sonnet", api_key: str = "mock") -> None:
        self.model_name = model_name
        self.api_key = api_key
        
        # Check if we should run in Mock/Offline mode
        self.is_mock = not api_key or api_key == "mock"
        if not self.is_mock:
            self.client = anthropic.AsyncAnthropic(api_key=api_key)
        else:
            self.client = None
            logger.info(f"AnthropicProvider ({model_name}) is initialized in Mock/Offline mode.")

    @property
    def cost_per_input_token(self) -> float:
        pricing = PRICING.get(self.model_name, {"input": 3.00})
        return pricing["input"] / 1_000_000.0

    @property
    def cost_per_output_token(self) -> float:
        pricing = PRICING.get(self.model_name, {"output": 15.00})
        return pricing["output"] / 1_000_000.0

    @property
    def context_window(self) -> int:
        # Standard context window for Claude 3/3.5 models is 200k
        return 200000

    async def _execute_with_retry(self, func, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202  # type: ignore
        """
        Executes a method and handles rate limit errors with exponential backoff.
        Retries up to 3 times (4 total attempts).
        """
        for attempt in range(4):
            try:
                return await func(*args, **kwargs)
            except anthropic.RateLimitError as e:
                if attempt == 3:
                    raise e
                
                # Default exponential backoff (2s, 4s, 8s)
                retry_after = 2 ** (attempt + 1)
                
                # If retry-after header is available in response headers, use it
                if hasattr(e, "response") and e.response is not None:
                    headers = e.response.headers
                    if "retry-after" in headers:
                        try:
                            retry_after = float(headers["retry-after"])
                        except ValueError:
                            pass
                
                logger.warning(f"Anthropic rate limit hit. Retrying in {retry_after} seconds... (Attempt {attempt + 1}/3)")  # noqa: E501
                await asyncio.sleep(retry_after)

    def _extract_system_and_messages(self, messages: list[ChatMessage]):  # noqa: ANN202  # type: ignore
        """
        Extracts system prompt and maps user/assistant messages to Anthropic format.
        System prompts are sent as a top-level parameter in the Anthropic API.
        """
        system_prompts = []
        anthropic_messages = []
        
        for m in messages:
            if m.role == "system":
                system_prompts.append(str(m.content))
            else:
                anthropic_messages.append({"role": m.role, "content": m.content})
                
        system_text = "\n\n".join(system_prompts) if system_prompts else None
        return system_text, anthropic_messages

    async def complete(self, messages: list[ChatMessage], **kwargs) -> GenerationResult:  # noqa: ANN003  # type: ignore
        start_time = time.time()
        
        # 1. Mock Mode
        if self.is_mock:
            await asyncio.sleep(0.1)  # Simulate network latency
            mock_content = f"Based on the provided documents [Source 1], this is a simulated complete response from Anthropic model {self.model_name}."  # noqa: E501
            
            prompt_len = sum(len(str(m.content)) for m in messages)
            input_tokens = max(1, prompt_len // 4)
            output_tokens = max(1, len(mock_content) // 4)
            latency_ms = (time.time() - start_time) * 1000
            cost = (input_tokens * self.cost_per_input_token) + (output_tokens * self.cost_per_output_token)  # noqa: E501
            
            return GenerationResult(
                content=mock_content,
                model=self.model_name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=latency_ms,
                cost_usd=cost,
                finish_reason="end_turn"
            )
            
        # 2. Real API Mode
        system_text, anthropic_messages = self._extract_system_and_messages(messages)
        
        params = {
            "model": self.model_name,
            "messages": anthropic_messages,
            "max_tokens": kwargs.pop("max_tokens", 4096)
        }
        if system_text:
            params["system"] = system_text
        
        # Add remaining kwargs
        params.update(kwargs)
        
        response = await self._execute_with_retry(  # type: ignore
            self.client.messages.create,
            **params
        )
        
        latency_ms = (time.time() - start_time) * 1000
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        cost = (input_tokens * self.cost_per_input_token) + (output_tokens * self.cost_per_output_token)  # noqa: E501
        
        # Extract text content from Anthropic response block
        response_text = ""
        if response.content:
            response_text = response.content[0].text
            
        return GenerationResult(
            content=response_text,
            model=self.model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            cost_usd=cost,
            finish_reason=response.stop_reason or "end_turn"
        )

    async def stream(self, messages: list[ChatMessage], **kwargs) -> AsyncGenerator[str, None]:  # type: ignore[override]  # noqa: ANN003
        # 1. Mock Mode
        if self.is_mock:
            mock_content = f"Based on the database records [Source 1], this is a simulated stream response from Anthropic model {self.model_name}."  # noqa: E501
            for word in mock_content.split():
                await asyncio.sleep(0.05)  # Simulate streaming interval
                yield word + " "
            return
            
        # 2. Real API Mode
        system_text, anthropic_messages = self._extract_system_and_messages(messages)
        
        params = {
            "model": self.model_name,
            "messages": anthropic_messages,
            "max_tokens": kwargs.pop("max_tokens", 4096)
        }
        if system_text:
            params["system"] = system_text
            
        params.update(kwargs)
        
        # Anthropic stream() client usage
        async with self.client.messages.stream(**params) as stream:
            async for chunk in stream.text_stream:
                yield chunk

    async def embed(self, texts: list[str]) -> list[list[float]]:
        # Anthropic does not have a native text embedding API model.
        # We return a mock/dummy embedding array of 1536 dimensions as standard fallback.
        return [[0.1] * 1536 for _ in texts]
