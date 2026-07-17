import asyncio
import logging
import time
from collections.abc import AsyncGenerator

import openai

from backend.providers.base import BaseLLMProvider, ChatMessage, GenerationResult

logger = logging.getLogger("openai-provider")

# Hardcoded price table per model (in USD per million tokens)
PRICING = {
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60}
}

class OpenAIProvider(BaseLLMProvider):
    def __init__(self, model_name: str = "gpt-4o-mini", api_key: str = "mock") -> None:
        self.model_name = model_name
        self.api_key = api_key
        
        # Check if we should run in Mock/Offline mode
        self.is_mock = not api_key or api_key == "mock"
        if not self.is_mock:
            self.client = openai.AsyncOpenAI(api_key=api_key)
        else:
            self.client = None
            logger.info(f"OpenAIProvider ({model_name}) is initialized in Mock/Offline mode.")

    @property
    def cost_per_input_token(self) -> float:
        # Convert price per million to price per single token
        pricing = PRICING.get(self.model_name, {"input": 0.15})
        return pricing["input"] / 1_000_000.0

    @property
    def cost_per_output_token(self) -> float:
        pricing = PRICING.get(self.model_name, {"output": 0.60})
        return pricing["output"] / 1_000_000.0

    @property
    def context_window(self) -> int:
        # Standard context window for gpt-4o family models is 128k
        return 128000

    async def _execute_with_retry(self, func, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202  # type: ignore
        """
        Executes a method and handles rate limit errors with exponential backoff.
        Retries up to 3 times (4 total attempts).
        """
        for attempt in range(4):
            try:
                return await func(*args, **kwargs)
            except openai.RateLimitError as e:
                if attempt == 3:
                    raise e
                
                # Exponential backoff: 15s, 30s, 60s — respects free tier 60s cooldown
                retry_after = 15 * (2 ** attempt)
                
                # If retry-after header is available, use it instead (more precise)
                if hasattr(e, "response") and e.response is not None:
                    headers = e.response.headers
                    if "retry-after" in headers:
                        try:
                            retry_after = float(headers["retry-after"])
                        except ValueError:
                            pass
                
                logger.warning(f"Rate limit hit. Retrying in {retry_after:.0f}s... (Attempt {attempt + 1}/3)")  # noqa: E501
                await asyncio.sleep(retry_after)

    async def complete(self, messages: list[ChatMessage], **kwargs) -> GenerationResult:  # noqa: ANN003  # type: ignore
        start_time = time.time()
        
        # 1. Mock Mode
        if self.is_mock:
            await asyncio.sleep(0.1)  # Simulate network latency
            mock_content = f"Based on the provided documents [Source 1], this is a simulated complete response from OpenAI model {self.model_name}."  # noqa: E501
            
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
                finish_reason="stop"
            )
            
        # 2. Real API Mode
        formatted_messages = [{"role": m.role, "content": m.content} for m in messages]
        response = await self._execute_with_retry(  # type: ignore
            self.client.chat.completions.create,
            model=self.model_name,
            messages=formatted_messages,
            **kwargs
        )
        
        latency_ms = (time.time() - start_time) * 1000
        input_tokens = response.usage.prompt_tokens
        output_tokens = response.usage.completion_tokens
        cost = (input_tokens * self.cost_per_input_token) + (output_tokens * self.cost_per_output_token)  # noqa: E501
        
        return GenerationResult(
            content=response.choices[0].message.content,
            model=self.model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            cost_usd=cost,
            finish_reason=response.choices[0].finish_reason or "stop"
        )

    async def stream(self, messages: list[ChatMessage], **kwargs) -> AsyncGenerator[str, None]:  # type: ignore[override]  # noqa: ANN003
        # 1. Mock Mode
        if self.is_mock:
            mock_content = f"Based on the database records [Source 1], this is a simulated stream response from OpenAI model {self.model_name}."  # noqa: E501
            for word in mock_content.split():
                await asyncio.sleep(0.05)  # Simulate streaming interval
                yield word + " "
            return
            
        # 2. Real API Mode
        formatted_messages = [{"role": m.role, "content": m.content} for m in messages]
        response_stream = await self._execute_with_retry(  # type: ignore
            self.client.chat.completions.create,
            model=self.model_name,
            messages=formatted_messages,
            stream=True,
            **kwargs
        )
        
        async for chunk in response_stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def embed(self, texts: list[str]) -> list[list[float]]:
        # 1. Mock Mode
        if self.is_mock:
            # Return list of 1536-dimensional mock vectors
            return [[0.1] * 1536 for _ in texts]
            
        # 2. Real API Mode
        batch_size = 100
        embeddings = []
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i + batch_size]
            response = await self._execute_with_retry(  # type: ignore
                self.client.embeddings.create,
                model="text-embedding-3-small",
                input=batch_texts
            )
            for data in response.data:
                embeddings.append(data.embedding)
        return embeddings
