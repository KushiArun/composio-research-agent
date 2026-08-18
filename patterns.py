"""
Pattern analysis: reads results_v1.json and produces the headline
insights for the case study - auth distribution, self-serve vs gated
by category, most common blockers, easy wins vs outreach-needed.

Usage:
    python patterns.py
"""

import json
from collections import Counter, defaultdict

with open("results_v1.json", "r", encoding="utf-8") as f:
    results = json.load(f)

total = len(results)
print(f"=== PATTERN ANALYSIS ({total} apps) ===\n")

# ---------- 1. Auth method dominance ----------
auth_counter = Counter()
for r in results:
    for a in r.get("auth_methods", []):
        if a != "Unknown":
            auth_counter[a] += 1

print("--- Auth method dominance (excl. Unknown) ---")
known_auth_total = sum(auth_counter.values())
for method, count in auth_counter.most_common():
    pct = 100 * count / known_auth_total if known_auth_total else 0
    print(f"  {method}: {count} ({pct:.0f}% of labeled auth mentions)")
print()

# ---------- 2. Self-serve vs gated, overall and by category ----------
access_counter = Counter(r.get("access_type", "unknown") for r in results)
print("--- Access type (overall) ---")
for k, v in access_counter.most_common():
    print(f"  {k}: {v} ({100*v/total:.0f}%)")
print()

by_category = defaultdict(lambda: Counter())
for r in results:
    by_category[r["category"]][r.get("access_type", "unknown")] += 1

print("--- Self-serve % by category (highest first) ---")
category_selfserve_pct = []
for cat, counts in by_category.items():
    cat_total = sum(counts.values())
    selfserve = counts.get("self-serve", 0)
    pct = 100 * selfserve / cat_total if cat_total else 0
    category_selfserve_pct.append((cat, pct, selfserve, cat_total))

category_selfserve_pct.sort(key=lambda x: -x[1])
for cat, pct, selfserve, cat_total in category_selfserve_pct:
    print(f"  {cat}: {pct:.0f}% self-serve ({selfserve}/{cat_total})")
print()

# ---------- 3. Most common blockers ----------
blockers = [r.get("blocker") for r in results if r.get("blocker")]
print(f"--- Blockers found ({len(blockers)} apps with a stated blocker) ---")
# Group blockers by rough theme via keyword matching
themes = Counter()
for b in blockers:
    b_lower = b.lower()
    if "auth" in b_lower and ("not specified" in b_lower or "not described" in b_lower or "missing" in b_lower):
        themes["Auth method undocumented in scraped content"] += 1
    elif "admin" in b_lower or "manually" in b_lower or "account manager" in b_lower:
        themes["Requires manual/admin-issued credential"] += 1
    elif "phone" in b_lower or "2fa" in b_lower or "verification code" in b_lower:
        themes["Requires phone/2FA verification (not agent-automatable)"] += 1
    elif "contact" in b_lower or "sales" in b_lower or "partnership" in b_lower:
        themes["Requires sales/partnership contact"] += 1
    elif "extraction_failed" in b_lower or "quota" in b_lower or "rate" in b_lower:
        themes["Agent infrastructure failure (quota/rate-limit)"] += 1
    elif "documentation" in b_lower or "lack of" in b_lower or "no public" in b_lower:
        themes["Insufficient public documentation found"] += 1
    else:
        themes["Other/unclassified"] += 1

for theme, count in themes.most_common():
    print(f"  {theme}: {count}")
print()

# ---------- 4. Easy wins vs needs outreach ----------
easy_wins = [r for r in results if r.get("buildability_verdict") == "buildable_today"
             and r.get("access_type") == "self-serve" and r.get("confidence") == "high"]
needs_outreach = [r for r in results if r.get("gate_type") in ("admin_approval", "partnership")
                  or (r.get("access_type") == "gated")]

print(f"--- Easy wins: self-serve + high confidence + buildable_today ({len(easy_wins)}) ---")
for r in easy_wins[:15]:
    print(f"  - {r['app_name']} ({r['category']})")
if len(easy_wins) > 15:
    print(f"  ... and {len(easy_wins) - 15} more")
print()

print(f"--- Needs outreach: gated / admin_approval / partnership ({len(needs_outreach)}) ---")
for r in needs_outreach[:15]:
    print(f"  - {r['app_name']} ({r['category']}) — gate: {r.get('gate_type')}")
if len(needs_outreach) > 15:
    print(f"  ... and {len(needs_outreach) - 15} more")
print()

# ---------- 5. Composio coverage gap ----------
has_toolkit = sum(1 for r in results if r.get("composio_toolkit_exists"))
buildable_no_toolkit = [r for r in results
                         if r.get("buildability_verdict") == "buildable_today"
                         and not r.get("composio_toolkit_exists")]
print(f"--- Composio coverage ---")
print(f"  Apps with an existing Composio toolkit: {has_toolkit}/{total}")
print(f"  Buildable apps with NO existing Composio toolkit (opportunity list): {len(buildable_no_toolkit)}")
for r in buildable_no_toolkit[:15]:
    print(f"  - {r['app_name']} ({r['category']})")
if len(buildable_no_toolkit) > 15:
    print(f"  ... and {len(buildable_no_toolkit) - 15} more")

# ---------- Save a machine-readable summary too ----------
summary = {
    "total_apps": total,
    "auth_distribution": dict(auth_counter),
    "access_type_distribution": dict(access_counter),
    "self_serve_pct_by_category": {cat: round(pct, 1) for cat, pct, _, _ in category_selfserve_pct},
    "blocker_themes": dict(themes),
    "easy_wins_count": len(easy_wins),
    "easy_wins": [r["app_name"] for r in easy_wins],
    "needs_outreach_count": len(needs_outreach),
    "needs_outreach": [r["app_name"] for r in needs_outreach],
    "composio_toolkit_coverage": has_toolkit,
    "buildable_no_toolkit_opportunity": [r["app_name"] for r in buildable_no_toolkit],
}
with open("patterns_summary.json", "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=2)

print("\n\nSaved machine-readable version to patterns_summary.json")