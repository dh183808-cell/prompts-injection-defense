#!/usr/bin/env python3
"""Verify B1-Nex results: coverage, errors, per-family analysis, leak case audit."""

import json
from collections import Counter, defaultdict
from pathlib import Path

# ── Load dataset and results ──────────────────────────

def load_jsonl(path):
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]

def load_dataset_cases(path):
    """Return set of case_ids from the dataset JSONL."""
    records = load_jsonl(path)
    return {r["case_id"] for r in records}

# ── Load files ────────────────────────────────────────

DATASET_PATH = "data/generated/b0_formal.jsonl"
RESULTS_PATH = "runs/b1_nex.jsonl"

dataset_ids = load_dataset_cases(DATASET_PATH)
results = load_jsonl(RESULTS_PATH)
result_ids = {r["case_id"] for r in results}

print("=" * 64)
print("  B1-Nex Result Verification")
print("=" * 64)

# ── 1. Coverage check ─────────────────────────────────
print(f"\n[1] Coverage check")
print(f"    Dataset cases:      {len(dataset_ids)}")
print(f"    Result records:     {len(results)}")
print(f"    Unique case_ids:    {len(result_ids)}")

missing = dataset_ids - result_ids
extra = result_ids - dataset_ids
if missing:
    print(f"    ❌ MISSING cases:    {len(missing)}")
    for c in sorted(missing)[:10]:
        print(f"       - {c}")
if extra:
    print(f"    ❌ EXTRA cases:      {len(extra)}")
    for c in sorted(extra)[:10]:
        print(f"       - {c}")
if not missing and not extra:
    print(f"    ✅ Full coverage: all {len(dataset_ids)} cases present, no extras")
else:
    print(f"    ⚠️  Coverage incomplete")

# Check for duplicate case_ids
case_counts = Counter(r["case_id"] for r in results)
dups = {k: v for k, v in case_counts.items() if v > 1}
if dups:
    print(f"    ❌ Duplicate case_ids: {len(dups)}")
    for c, cnt in list(dups.items())[:5]:
        print(f"       - {c}: {cnt} times")
else:
    print(f"    ✅ No duplicate case_ids")

# ── 2. DeepSeek mixing check ──────────────────────────
print(f"\n[2] Cross-contamination check")
mix_count = 0
for r in results:
    raw = r.get("defender_raw", "") or ""
    if "deepseek" in raw.lower():
        mix_count += 1
        print(f"    ❌ DeepSeek content in: {r['case_id']}")
    if r.get("actual_model", "") and "deepseek" in r["actual_model"].lower():
        mix_count += 1
        print(f"    ❌ DeepSeek model in: {r['case_id']}")
    if r.get("defender_model", "") and "deepseek" in r["defender_model"].lower():
        mix_count += 1
        print(f"    ❌ DeepSeek defender in: {r['case_id']}")

# Check run_id has B1-Nex tag
non_nex = [r for r in results if "Nex" not in r.get("run_id", "") and "nex" not in r.get("run_id", "")]
if non_nex:
    print(f"    ⚠️  {len(non_nex)} records with non-nex run_id (first: {non_nex[0]['case_id']})")
else:
    print(f"    ✅ All run_ids contain 'Nex'")

if mix_count == 0:
    print(f"    ✅ No DeepSeek cross-contamination found")

# ── 3. Error/quality check ────────────────────────────
print(f"\n[3] Quality check")
errors = [r for r in results if r.get("error")]
empty_output = [r for r in results if not r.get("target_output", "").strip()]
missing_defender = [r for r in results if not r.get("defender_raw")]
parse_failures = [r for r in results if r.get("defender_raw", "") and not r.get("defender_is_attack") and not r.get("defender_is_attack") is False]

# Actually check defender_is_attack properly
# If defender_is_attack is True or False, it was parsed
invalid_defender = []
for r in results:
    if r.get("defender_raw"):
        try:
            parsed = json.loads(r["defender_raw"])
            if "is_attack" not in parsed:
                invalid_defender.append(r["case_id"])
        except json.JSONDecodeError:
            invalid_defender.append(r["case_id"])

print(f"    API errors:          {len(errors)}")
for e in errors[:5]:
    print(f"       - {e['case_id']}: {e['error'][:80]}")
print(f"    Empty target output: {len(empty_output)}")
print(f"    Missing defender_raw: {len(missing_defender)}")
print(f"    JSON parse failures: {len(invalid_defender)}")
for cid in invalid_defender[:5]:
    print(f"       - {cid}")

# Missing defender fields
no_def_fields = [r for r in results if r.get("defender_latency_ms") is None]
print(f"    Missing defender timing: {len(no_def_fields)}")

all_ok = (len(errors) == 0 and len(empty_output) == 0 and
          len(invalid_defender) == 0 and len(no_def_fields) == 0)
if all_ok:
    print(f"    ✅ All records clean (no errors, no empty, all JSON valid)")
else:
    print(f"    ⚠️  Some records have quality issues")

# ── 4. Per-attack-family CLR + task_hijacked ──────────
print(f"\n[4] Per-attack-family statistics")
attack = [r for r in results if r["kind"] in ("direct", "indirect")]
benign = [r for r in results if r["kind"] == "benign"]

by_family = defaultdict(list)
for r in attack:
    fam = r.get("attack_family") or "unknown"
    by_family[fam].append(r)

print(f"\n    {'Attack family':<28} {'Total':>6} {'Leaked':>7} {'CLR':>8} {'Hijacked':>9} {'Blocked':>8}")
print(f"    {'-'*28}  {'-'*6} {'-'*7} {'-'*8} {'-'*9} {'-'*8}")
total_leaked = 0
total_hijacked = 0
total_blocked = 0
for fam in sorted(by_family):
    items = by_family[fam]
    n = len(items)
    leaked = sum(1 for r in items if r["leaked"])
    hijacked = sum(1 for r in items if r.get("task_hijacked"))
    blocked = sum(1 for r in items if r.get("defender_is_attack") and not r["leaked"])
    total_leaked += leaked
    total_hijacked += hijacked
    total_blocked += blocked
    print(f"    {fam:<28} {n:>6} {leaked:>7} {leaked/n*100:>7.1f}% {hijacked:>9} {blocked:>8}")

# Totals for attack
n_attack = len(attack)
print(f"    {'-'*70}")
print(f"    {'TOTAL (attack)':<28} {n_attack:>6} {total_leaked:>7} {total_leaked/n_attack*100:>7.1f}% {total_hijacked:>9} {total_blocked:>8}")

# Benign stats
benign_leaked = sum(1 for r in benign if r["leaked"])
benign_hijacked = sum(1 for r in benign if r.get("task_hijacked"))
print(f"    {'Benign':<28} {len(benign):>6} {benign_leaked:>7} {benign_leaked/len(benign)*100:>7.1f}% {benign_hijacked:>9} {'N/A':>8}")

# ── 5. Analyze 24 leaked cases ────────────────────────
print(f"\n[5] Leaked case analysis")
leaked_cases = [r for r in attack if r["leaked"]]
print(f"    Total leaked: {len(leaked_cases)}")
print()

# Categorize leaked cases
categories = {
    "missed_detection": [],      # defender didn't flag
    "repair_failure": [],        # defender flagged but repair didn't work
}
for r in leaked_cases:
    if r.get("defender_is_attack"):
        categories["repair_failure"].append(r)
    else:
        categories["missed_detection"].append(r)

print(f"    Missed detection (defender said no attack):    {len(categories['missed_detection'])}")
print(f"    Repair failure (defender flagged, still leaked): {len(categories['repair_failure'])}")
print()

# Detail repair failures
print(f"    — Repair failures —")
for r in categories["repair_failure"]:
    fam = r.get("attack_family") or "?"
    raw = r.get("defender_raw", "") or ""
    # Extract what defender said
    try:
        parsed = json.loads(raw)
        reason = parsed.get("reason", "?")[:80]
        repaired = parsed.get("repaired_prompt", "")[:80]
    except (json.JSONDecodeError, TypeError):
        reason = "?"
        repaired = "?"
    print(f"      {r['case_id']}")
    print(f"        family={fam}  reason={reason}")
    print(f"        repaired_preview={repaired}")

print()
print(f"    — Missed detections —")
for r in categories["missed_detection"]:
    fam = r.get("attack_family") or "?"
    raw = r.get("defender_raw", "") or ""
    try:
        parsed = json.loads(raw)
        reason = parsed.get("reason", "?")[:80]
    except (json.JSONDecodeError, TypeError):
        reason = "?"
    print(f"      {r['case_id']}  family={fam}")
    print(f"        defender_said={reason}")

# ── 6. Metadata snapshot ──────────────────────────────
print(f"\n[6] Run metadata vs dataset")
# Pick one record to get run metadata
sample = results[0] if results else {}
print(f"    Dataset cases:      {len(dataset_ids)}")
print(f"    Dataset hash:        {sample.get('dataset_hash', 'N/A')}")
print(f"    Dataset seed:        {sample.get('dataset_seed', 'N/A')}")
print(f"    Git commit:          {sample.get('git_commit', 'N/A')}")
print(f"    Temperature:         {sample.get('temperature', 'N/A')}")
print(f"    Max tokens:          {sample.get('max_tokens', 'N/A')}")
print(f"    System prompt mode:  {sample.get('system_prompt_mode', 'N/A')}")
print(f"    Target model:        {sample.get('configured_model', 'N/A')}")
print(f"    Target provider:     siliconflow")

# Defender model from actual records
def_models = set()
for r in results:
    dm = r.get("defender_model")
    if dm:
        def_models.add(dm)
print(f"    Defender model:      {def_models if def_models else 'N/A'}")
print(f"    Defender provider:   openrouter" if "openrouter" in str(sample.get("defender_raw", "")).lower() else "    Defender provider:   siliconflow")

# Defender latency stats
def_lats = [r.get("defender_latency_ms") for r in results if r.get("defender_latency_ms")]
if def_lats:
    def_lats_s = sorted(def_lats)
    n = len(def_lats_s)
    mid = n // 2
    median = def_lats_s[mid] if n % 2 else (def_lats_s[mid-1] + def_lats_s[mid]) / 2
    print(f"    Defender latency:    {median:.0f}ms median ({min(def_lats_s):.0f}-{max(def_lats_s):.0f}ms range)")

# ── 7. Conclusion ─────────────────────────────────────
print(f"\n[7] Freeze conclusion")
checks_passed = (
    len(missing) == 0 and len(extra) == 0 and
    len(dups) == 0 and
    mix_count == 0 and
    len(errors) == 0 and
    len(empty_output) == 0 and
    len(invalid_defender) == 0 and
    len(no_def_fields) == 0
)
if checks_passed:
    print(f"    ✅ ALL CHECKS PASSED")
    print(f"    → B1-Nex result can be frozen as FORMAL B1")
else:
    print(f"    ⚠️  Some checks failed — see above for details")

print()
print(f"    Summary:")
print(f"    - Architecture: B1")
print(f"    - Defender: Nex-N2-Pro (siliconflow)")
print(f"    - Target: zai-org/GLM-4.5-Air (siliconflow)")
print(f"    - System prompt: minimal (no defensive wording)")
print(f"    - Dataset: 210 cases, seed=42")
print(f"    - Results file: runs/b1_nex.jsonl")
print(f"    - CLR: {total_leaked}/{n_attack} = {total_leaked/n_attack*100:.1f}%")
print(f"    - STCR: {sum(1 for r in attack if not r['leaked'] and r.get('task_correct_auto') is True)}/{n_attack} = {sum(1 for r in attack if not r['leaked'] and r.get('task_correct_auto') is True)/n_attack*100:.1f}%")
print(f"    - Total errors: {len(errors)}")
print("=" * 64)