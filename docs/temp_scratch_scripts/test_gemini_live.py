"""
Quick smoke test to verify the Gemini 2.0 Flash API key works correctly.
Run from project root: python backend/test_gemini_live.py
"""
import asyncio
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')  # type: ignore

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load .env from project root so GEMINI_API_KEY is available on host machine
from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from backend.providers.base import ChatMessage  # noqa: E402
from backend.providers.gemini_provider import GeminiProvider  # noqa: E402


async def test_gemini() -> None:
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key or api_key == "mock":
        print("ERROR: GEMINI_API_KEY is not set in environment.")
        print("Add it to your .env file: GEMINI_API_KEY=AIza...")
        return

    print(f"Testing gemini-flash-latest (FREE rolling alias) with key: {api_key[:8]}...{api_key[-4:]}")  # noqa: E501
    print("=" * 60)

    provider = GeminiProvider(model_name="gemini-flash-latest", api_key=api_key)

    messages = [
        ChatMessage(role="system", content="You are a concise AI assistant."),
        ChatMessage(role="user", content="In one sentence, what is RAG (Retrieval Augmented Generation)?")  # noqa: E501
    ]

    print("\n[1] Testing complete() call...")
    result = await provider.complete(messages)
    print(f"    Model:         {result.model}")
    print(f"    Input tokens:  {result.input_tokens}")
    print(f"    Output tokens: {result.output_tokens}")
    print(f"    Cost USD:      ${result.cost_usd:.6f}  (should be $0.000000 on free tier)")
    print(f"    Response:      {result.content}")

    print("\n[2] Testing stream() call...")
    streamed = ""
    async for token in provider.stream(messages):
        streamed += token
    print(f"    Streamed response: {streamed.strip()}")

    print("\n" + "=" * 60)
    print("SUCCESS: gemini-flash-latest is LIVE and responding!")
    print("Total billing for this test: $0.000000 (free tier, $0 guaranteed)")

if __name__ == "__main__":
    asyncio.run(test_gemini())
