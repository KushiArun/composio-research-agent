# Composio App Research Agent

An automated research pipeline that investigates 100 real-world apps and produces a
buildability verdict for each — category, auth method, self-serve vs. gated access,
API surface, and evidence — then verifies its own accuracy against live documentation.

**Live case study:** https://kushiarun.github.io/composio-research-agent/
**Full results:** [`results_v1.json`](results_v1.json) · **Verification:** [`verification_report.md`](verification_report.md)

---

## What this is

Composio turns apps into tools AI agents can call. Before building a toolkit for an app,
someone has to research it: what auth it uses, whether access is self-serve or gated,
what the API surface looks like. This project does that research across 100 apps with
an agent instead of by hand, then checks how accurate the agent actually was.

**Result:** 88/100 apps reached a confident "buildable today" verdict, 10 remain unclear,
2 are blocked — each one documented with a reason and a source link, not just a label.

## How it works

```
seed.json → search_docs() → fetch_page_text() → Composio toolkit check → LLM extraction → results_v1.json
```

For each app, `research_agent.py`:
1. **Searches** the web for developer/auth docs (DuckDuckGo, with retry on failure)
2. **Fetches** the top pages, detects bot-blocked/error pages, and falls back to search
   snippets when a page can't be read
3. **Checks Composio's own toolkit list** to flag whether an integration already exists
4. **Extracts** a structured JSON record (auth method, access type, buildability verdict,
   confidence, evidence URL) via an LLM call, using Groq's free tier
5. **Checkpoints** after every app — a re-run only retries records that came back low-confidence
   or unclear, so nothing is repeated or lost

`patterns.py` then clusters the 100 results into the headline findings (auth distribution,
self-serve rate by category, common blockers, Composio coverage gaps).

## Setup

```bash
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

pip install composio python-dotenv ddgs beautifulsoup4 requests groq
```

Create a `.env` file in the project root:
```
COMPOSIO_API_KEY=your_composio_key
GROQ_API_KEY=your_groq_key
```
- Composio key: https://composio.dev (free tier)
- Groq key: https://console.groq.com/keys (free tier)

## Running it

```bash
python research_agent.py           # researches all 100 apps, saves to results_v1.json
python research_agent.py 3         # demo mode: only researches the first N apps
python patterns.py                 # clusters results into headline findings, saves patterns_summary.json
python summarize.py                # quick verdict/confidence breakdown for a sanity check
```

### Run it live, without cloning anything

The **"Run agent live →"** button in the case study's nav bar triggers a real GitHub
Actions workflow ([`.github/workflows/demo-run.yml`](.github/workflows/demo-run.yml))
that runs `research_agent.py` against a small live subset of apps, using the actual
Composio and Groq APIs — not a mock. Anyone with repo access can trigger it from the
Actions tab and watch the real pipeline execute, then download the output as a build
artifact. This requires `COMPOSIO_API_KEY` and `GROQ_API_KEY` to be set as repo secrets
(Settings → Secrets and variables → Actions).

`research_agent.py` is safe to re-run at any point — it checkpoints after every app and
skips anything that already has a solid result, so an interrupted run or a quota limit
never loses progress.

## Where a human was needed

The agent didn't run cleanly end to end — three real infrastructure failures happened
mid-build, each one caught by reading raw logs, not by the agent noticing on its own:

1. **Gemini's free tier caps at 20 requests/day** — caused most of the first full pass to
   silently fall back to "unclear." Fixed by switching the extraction call to Groq.
2. **A Groq model was deprecated mid-build** (`llama-3.3-70b-versatile`) — caused a second
   wave of silent failures until traced through the logs and pinned to a working model.
3. **Groq's 200k-token daily quota ran out** near the end of a cleanup pass, defaulting the
   last ~9 apps (including Plaid) to low-confidence "unclear."

All three are documented in the case study page under "The Agent," with the actual log
excerpts, not a summary of them.

## Verification

A 16-app stratified sample (mixing high-confidence wins, unclear/blocked cases, and
apps with blocked page fetches) was manually cross-checked against live documentation.
Full methodology and per-app results are in [`verification_report.md`](verification_report.md).

**Headline result:** the agent's own confidence score reliably predicted correctness —
every miss in the sample was on a record the agent had already flagged as low/medium
confidence. It never confidently asserted something false.

## Repo structure

```
seed.json                  the 100 apps, categorized, with a starting docs URL each
research_agent.py          the research pipeline
patterns.py                clusters results_v1.json into headline findings
summarize.py               quick verdict/confidence counts
results_v1.json            full output — 100 apps, all fields, evidence URLs
patterns_summary.json      machine-readable pattern findings
verification_report.md     manual accuracy check against live docs
index.html                 the case study page (this is what's deployed)
```

## Honest limitations

- 10 apps remain `unclear` and 2 `blocked` — each has a specific, stated reason (undocumented
  auth in the scraped content, a phone-verification requirement, an account-manager-only key,
  etc.), not a generic failure.
- The verification pass deep-checked 5 apps against fresh, independent research and
  spot-checked 11 more against their own cited sources. A production version would run a
  second independent agent pass across all 100.