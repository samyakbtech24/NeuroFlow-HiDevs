"""Test which flash models are actually callable via chat completions."""
import os, sys
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
import openai

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

api_key = os.getenv("GEMINI_API_KEY", "")
client = openai.OpenAI(
    api_key=api_key,
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
)

# Models to probe — no 1.5 family, flash variants only
candidates = [
    "gemini-2.0-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-flash-latest",
    "gemini-flash-lite-latest",
]

print("Probing chat completions endpoint for each model...")
print("=" * 60)

for model in candidates:
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Say OK"}],
            max_tokens=5
        )
        print(f"  OK   {model:<35} -> '{resp.choices[0].message.content.strip()}'")
    except openai.NotFoundError:
        print(f"  404  {model:<35} -> deprecated/unavailable for new users")
    except openai.RateLimitError:
        print(f"  429  {model:<35} -> rate limit hit (model EXISTS but quota exhausted)")
    except Exception as e:
        print(f"  ERR  {model:<35} -> {type(e).__name__}: {str(e)[:80]}")
