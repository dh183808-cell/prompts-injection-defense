"""Final comparison: all 7 experiments + B3 v2 adjudicator analysis."""
import json

FILES = [
    ("B0-Minimal",   "runs/b0_minimal.jsonl",   "minimal"),
    ("B0-Hardened",  "runs/b0_hardened.jsonl",  "hardened"),
    ("B1-Nex",       "runs/b1_nex.jsonl",       "minimal"),
    ("B1-DeepSeek",  "runs/b1.jsonl",           "minimal"),
    ("B2",           "runs/b2.jsonl",           "minimal"),
    ("B3-v1",        "runs/b3.jsonl",           "minimal"),
    ("B3-v2(fixed)", "runs/b3_v2.jsonl",        "minimal"),
]

def load(p):
    with open(p) as f:
        return [json.loads(l) for l in f if l.strip()]

rows = []
for name, path, mode in FILES:
    recs = load(path)
    a = [r for r in recs if r["kind"] in ("direct","indirect")]
    b = [r for r in recs if r["kind"] == "benign"]
    n = len(a) or 1
    lk = sum(1 for r in a if r["leaked"])
    ct = sum(1 for r in a if not r["leaked"] and r.get("task_correct_auto") is True)
    ov = sum(1 for r in recs if r.get("over_refusal"))
    hj = sum(1 for r in recs if r.get("task_hijacked"))
    er = sum(1 for r in recs if r.get("error"))
    rows.append((name, len(a), len(b), lk, f"{lk/n*100:.1f}%", f"{ct/n*100:.1f}%", ov, hj, er, mode))

print("=" * 108)
print(f"{'Experiment':<20} {'Attack':>6} {'Benign':>6} {'Leaked':>7} {'CLR':>10} {'STCR':>10} {'Refusal':>7} {'Hijack':>7} {'Err':>5} {'PromptMode':>12}")
print("-" * 108)
for r in rows:
    print(f"{r[0]:<20} {r[1]:>6} {r[2]:>6} {r[3]:>7} {r[4]:>10} {r[5]:>10} {r[6]:>7} {r[7]:>7} {r[8]:>5} {r[9]:>12}")
print("=" * 108)

# B3 v2 adjudicator deep-dive
print()
b3 = load("runs/b3_v2.jsonl")
attack = [r for r in b3 if r["kind"] in ("direct","indirect")]
n = len(attack) or 1
confirmed = sum(1 for r in attack if r.get("adjudicator_confirmed"))
denied = sum(1 for r in attack if r.get("or_triggered") and not r.get("adjudicator_confirmed"))
confirmed_blocked = sum(1 for r in attack if r.get("adjudicator_confirmed") and not r["leaked"])
confirmed_leaked = sum(1 for r in attack if r.get("adjudicator_confirmed") and r["leaked"])
denied_blocked = sum(1 for r in attack if r.get("or_triggered") and not r.get("adjudicator_confirmed") and not r["leaked"])
denied_leaked = sum(1 for r in attack if r.get("or_triggered") and not r.get("adjudicator_confirmed") and r["leaked"])

print(f"=== B3-v2 Adjudicator Analysis ({len(b3)} total, {len(attack)} attack) ===")
print()
print(f"  Attack samples:           {len(attack)}")
print(f"  OR triggered:             {confirmed + denied}/{len(attack)} = {(confirmed+denied)/n*100:.1f}%")
print(f"  Adjudicator confirmed:    {confirmed} = {confirmed/n*100:.1f}%")
print(f"  Adjudicator denied:       {denied} = {denied/n*100:.1f}%")
print()
if confirmed:
    print(f"  Of {confirmed} confirmed:")
    print(f"    Blocked (no leak):      {confirmed_blocked} ({confirmed_blocked/confirmed*100:.1f}%)")
    print(f"    Still leaked:           {confirmed_leaked} ({confirmed_leaked/confirmed*100:.1f}%)")
if denied:
    print(f"  Of {denied} denied (overruled detectors):")
    print(f"    Actually no leak:       {denied_blocked} ({denied_blocked/denied*100:.1f}%)")
    print(f"    Leaked (wrong denial):  {denied_leaked} ({denied_leaked/denied*100:.1f}%)")