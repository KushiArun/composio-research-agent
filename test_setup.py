"""
Sanity check for the free stack: Composio SDK + Gemini API + DuckDuckGo search.
"""

import os
from dotenv import load_dotenv

load_dotenv()


def test_gemini():
    from google import genai

    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    response = client.models.generate_content(
        model="gemini-3.5-flash",
        contents="Reply with exactly: Gemini key works."
    )
    print("[Gemini]", response.text.strip())


def test_composio():
    from composio import Composio

    client = Composio(api_key=os.getenv("COMPOSIO_API_KEY"))
    result = client.toolkits.list()
    items = getattr(result, "items", None)
    names = [t.slug for t in items[:5]] if items else []
    print("[Composio] Connected. Sample toolkits:", names)


def test_search():
    from ddgs import DDGS

    with DDGS() as ddgs:
        results = list(ddgs.text("Salesforce developer API docs", max_results=3))
    print("[DuckDuckGo] Got", len(results), "results. First:", results[0]["href"] if results else "none")


if __name__ == "__main__":
    for name, fn in [("Gemini", test_gemini), ("Composio", test_composio), ("DuckDuckGo", test_search)]:
        print(f"\nTesting {name}...")
        try:
            fn()
        except Exception as e:
            print(f"[{name}] FAILED:", e)
