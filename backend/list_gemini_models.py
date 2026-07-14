"""Lists all available Gemini models via the OpenAI compatibility endpoint."""
import os, asyncio
from dotenv import load_dotenv
import openai

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

api_key = os.getenv("GEMINI_API_KEY", "")
client = openai.OpenAI(
    api_key=api_key,
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
)

models = client.models.list()
print("\nAvailable models on your Gemini API key:")
print("=" * 50)
for m in sorted(models.data, key=lambda x: x.id):
    print(f"  {m.id}")
