"""
Quick summary of results_v1.json: verdict breakdown, confidence levels,
auth method distribution, and a list of apps that likely need a re-run.

Usage:
    python summarize.py
"""

import json
from collections import Counter

with open("results_v1.json", "r", encoding="utf-8") as f:
    results = json.load(f)

print(f"Total records: {len(results)}\n")

verdicts = Counter(r.get("buildability_verdict", "MISSING") for r in results)
print("=== Buildability verdicts ===")
for k, v in verdicts.most_common():
    print(f"  {k}: {v}")

confidence = Counter(r.get("confidence", "MISSING") for r in results)
print("\n=== Confidence levels ===")
for k, v in confidence.most_common():
    print(f"  {k}: {v}")

access = Counter(r.get("access_type", "MISSING") for r in results)
print("\n=== Access type ===")
for k, v in access.most_common():
    print(f"  {k}: {v}")

auth_counter = Counter()
for r in results:
    for a in r.get("auth_methods", []):
        auth_counter[a] += 1
print("\n=== Auth methods (apps can have multiple) ===")
for k, v in auth_counter.most_common():
    print(f"  {k}: {v}")

# Apps likely needing a re-run: unclear verdict OR low confidence OR Unknown auth
needs_rerun = [
    r["app_name"] for r in results
    if r.get("buildability_verdict") in ("unclear", "blocked", None)
    or r.get("confidence") == "low"
    or r.get("auth_methods") == ["Unknown"]
]
print(f"\n=== Apps that likely need a re-run ({len(needs_rerun)}) ===")
for name in needs_rerun:
    print(f"  - {name}")