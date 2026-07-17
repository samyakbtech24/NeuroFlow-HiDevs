from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from dataclasses import dataclass


@dataclass
class ChatMessage:
    """
    Represents a message sent to or received from the LLM.
    role: Can be "system", "user", or "assistant".
    content: Either a string (for simple text) or a list (for multi-modal data like images).
    """
    role: str
    content: str | list  # type: ignore

@dataclass
class GenerationResult:
    """
    Represents the structured result returned after a complete LLM generation.
    """
    content: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    cost_usd: float
    finish_reason: str

class BaseLLMProvider(ABC):
    """
    Abstract Base Class that every LLM provider must implement.
    This guarantees that the rest of the application can interact with any LLM in the same way.
    """
    
    @abstractmethod
    async def complete(self, messages: list[ChatMessage], **kwargs) -> GenerationResult:  # noqa: ANN003  # type: ignore
        """
        Send a list of chat messages to the LLM and get back the full, completed response.
        """
        pass

    @abstractmethod
    async def stream(self, messages: list[ChatMessage], **kwargs) -> AsyncGenerator[str, None]:  # noqa: ANN003  # type: ignore
        """
        Send a list of chat messages to the LLM and stream back the response text chunk-by-chunk.
        """
        pass

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """
        Convert a list of text strings into vector embeddings (dense floating point lists).
        """
        pass

    @property
    @abstractmethod
    def cost_per_input_token(self) -> float:
        """
        Returns the cost in USD per single input token.
        """
        pass

    @property
    @abstractmethod
    def cost_per_output_token(self) -> float:
        """
        Returns the cost in USD per single output token.
        """
        pass

    @property
    @abstractmethod
    def context_window(self) -> int:
        """
        Returns the maximum number of tokens this model can accept in a single request.
        """
        pass
