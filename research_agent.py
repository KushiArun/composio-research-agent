"""
Research agent: for each app in seed.json, this script
  1. Searches the web for developer/API docs
  2. Fetches the top doc page(s)
  3. Checks whether Composio already has a toolkit for this app
  4. Asks Gemini to extract structured research fields from what it found
  5. Saves one JSON record per app

Usage:
    python research_agent.py
"""

import os
import json
import time
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from ddgs import DDGS
from groq import Groq
from composio import Composio

load_dotenv()

# ---------- CONFIG ----------
TEST_LIMIT = None
import sys
if len(sys.argv) > 1:
    try:
        TEST_LIMIT = int(sys.argv[1])
    except ValueError:
        pass
SEED_FILE = "seed.json"
OUTPUT_FILE = "results_v1.json"
SLEEP_BETWEEN_APPS = 5
GROQ_MODEL = "openai/gpt-oss-120b"

# ---------- CLIENTS ----------
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
composio_client = Composio(api_key=os.getenv("COMPOSIO_API_KEY"))


def get_composio_toolkit_slugs():
    try:
        result = composio_client.toolkits.list()
        items = getattr(result, "items", None) or []
        return set(t.slug.lower() for t in items)
    except Exception as e:
        print("  [warn] Could not fetch Composio toolkit list:", e)
        return set()


def search_docs(app_name, hint_url, max_retries=3):
    query = f"{app_name} API documentation authentication"

    for attempt in range(1, max_retries + 1):
        try:
            with DDGS(timeout=15) as ddgs:
                results = list(ddgs.text(query, max_results=5))
            if not results:
                raise ValueError("empty result set")
            urls = [r["href"] for r in results if r.get("href")]
            snippets = {r["href"]: r.get("body", "") for r in results if r.get("href")}
            if hint_url and hint_url not in urls:
                urls.insert(0, hint_url)
            return urls[:5], snippets
        except Exception as e:
            if attempt < max_retries:
                wait = 8 * attempt
                print(f"  [search retry {attempt}/{max_retries}] {app_name}: {type(e).__name__}, waiting {wait}s...")
                time.sleep(wait)
                continue
            print(f"  [warn] search failed for {app_name} after {max_retries} attempts:", e)

    return ([hint_url] if hint_url else []), {}


FAILURE_MARKERS = [
    "oops something went wrong", "access denied", "403 forbidden",
    "enable javascript", "are you a robot", "captcha", "just a moment",
    "attention required", "cloudflare",
]


def fetch_page_text(url, max_chars=6000):
    try:
        resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        text = " ".join(soup.get_text(separator=" ").split())

        lowered = text.lower()
        if len(text) < 200 or any(marker in lowered for marker in FAILURE_MARKERS):
            return None

        return text[:max_chars]
    except Exception:
        return None


EXTRACTION_PROMPT = """You are a research analyst evaluating whether an app's public API
could be turned into a tool that an AI agent can call.

App name: {app_name}
Category: {category}
Sources you have access to (raw scraped text, may be partial/messy):

{scraped_content}

Source URLs used:
{source_urls}

Based ONLY on the text above (do not use outside knowledge if it conflicts with the text),
return a single JSON object with EXACTLY these fields:

{{
  "one_liner": "one sentence describing what the app does",
  "auth_methods": ["OAuth2" | "API key" | "Basic" | "Token" | "Other" | "Unknown"],
  "access_type": "self-serve" | "gated" | "mixed" | "unknown",
  "access_detail": "one sentence explaining the self-serve/gated finding",
  "gate_type": "none" | "paid_plan" | "admin_approval" | "partnership" | "unknown",
  "api_surface_type": "REST" | "GraphQL" | "REST+GraphQL" | "SOAP" | "Other" | "unknown",
  "api_breadth": "narrow" | "moderate" | "broad" | "unknown",
  "buildability_verdict": "buildable_today" | "blocked" | "unclear",
  "blocker": "short phrase describing the blocker, or null if buildable_today",
  "confidence": "high" | "medium" | "low",
  "evidence_summary": "one sentence citing what in the source supports your answer"
}}

Return ONLY the JSON object. No markdown fences, no extra commentary.
"""


def extract_fields(app_name, category, scraped_content, source_urls, max_retries=4):
    prompt = EXTRACTION_PROMPT.format(
        app_name=app_name,
        category=category,
        scraped_content=scraped_content[:4000],
        source_urls="\n".join(source_urls),
    )

    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            response = groq_client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
            )
            raw = response.choices[0].message.content.strip()
            if raw.startswith("```"):
                raw = raw.strip("`")
                if raw.lower().startswith("json"):
                    raw = raw[4:]
            return json.loads(raw)
        except Exception as e:
            last_error = e
            is_rate_limited = "429" in str(e) or "rate_limit" in str(e).lower()
            if is_rate_limited and attempt < max_retries:
                wait = 8 * attempt
                print(f"  [retry {attempt}/{max_retries}] Groq rate limited, waiting {wait}s...")
                time.sleep(wait)
                continue
            break

    print(f"  [warn] Groq extraction failed for {app_name} after {max_retries} attempts:", last_error)
    return {
        "one_liner": None,
        "auth_methods": ["Unknown"],
        "access_type": "unknown",
        "access_detail": None,
        "gate_type": "unknown",
        "api_surface_type": "unknown",
        "api_breadth": "unknown",
        "buildability_verdict": "unclear",
        "blocker": f"extraction_failed: {last_error}",
        "confidence": "low",
        "evidence_summary": None,
    }


def research_app(app, composio_slugs):
    app_name = app["app_name"]
    category = app["category"]
    hint_url = app.get("hint_url")

    print(f"\nResearching: {app_name} ({category})")

    urls, snippets = search_docs(app_name, hint_url)
    print(f"  Sources found: {urls}")

    combined_text = ""
    fetch_failures = 0
    for url in urls[:3]:
        text = fetch_page_text(url)
        if text is None:
            fetch_failures += 1
            fallback = snippets.get(url, "")
            if fallback:
                combined_text += f"\n\n--- FROM {url} (fetch blocked, using search snippet) ---\n{fallback}"
        else:
            combined_text += f"\n\n--- FROM {url} ---\n{text}"
        if len(combined_text) > 4000:
            break

    if fetch_failures:
        print(f"  [note] {fetch_failures} page(s) blocked/failed, used search snippets as fallback")

    fields = extract_fields(app_name, category, combined_text, urls)

    slug_guess = app_name.lower().replace(" ", "").replace(".", "")
    mcp_exists = any(slug_guess in s or s in slug_guess for s in composio_slugs)

    record = {
        "id": app["id"],
        "app_name": app_name,
        "category": category,
        **fields,
        "composio_toolkit_exists": mcp_exists,
        "evidence_urls": urls,
        "fetch_blocked_count": fetch_failures,
    }
    return record


def main():
    with open(SEED_FILE, "r", encoding="utf-8") as f:
        apps = json.load(f)

    if TEST_LIMIT:
        apps = apps[:TEST_LIMIT]
        print(f"[TEST MODE] Processing only the first {TEST_LIMIT} apps.\n")

    existing = {}
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                for rec in json.load(f):
                    existing[rec["id"]] = rec
            print(f"Found existing {OUTPUT_FILE} with {len(existing)} records. Will skip already-successful ones.")
        except Exception:
            pass

    composio_slugs = get_composio_toolkit_slugs()
    print(f"Loaded {len(composio_slugs)} known Composio toolkit slugs.")

    results = list(existing.values())
    results_by_id = {r["id"]: r for r in results}

    for app in apps:
        prior = results_by_id.get(app["id"])
        is_weak = (
            not prior
            or prior.get("buildability_verdict") in ("unclear", "blocked", None)
            or prior.get("confidence") == "low"
        )
        if prior and not is_weak:
            print(f"\nSkipping {app['app_name']} (already have a good result)")
            continue

        record = research_app(app, composio_slugs)
        results_by_id[app["id"]] = record
        print(f"  -> Verdict: {record['buildability_verdict']} | Auth: {record['auth_methods']} | Access: {record['access_type']}")

        ordered = [results_by_id[a["id"]] for a in apps if a["id"] in results_by_id]
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(ordered, f, indent=2)

        time.sleep(SLEEP_BETWEEN_APPS)

    print(f"\nDone. Saved {len(results_by_id)} records to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
