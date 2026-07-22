"""Check B3 progress and adjudicator effectiveness."""
import json

with open("/home/harrylee/projects/prompt-injection-defense/runs/b3.jsonl") as f:
    records = [json.loads(l) for l in f if l.strip()]

attack = [r for r in records if r["kind"] in ("direct", "indirect")]
leaked = sum(1 for r in attack if r["leaked"])
confirmed = sum(1 for r in attack if r.get("adjudicator_confirmed"))
denied = sum(1 for r in attack if r.get("or_triggered") and not r.get("adjudicator_confirmed"))
n = len(attack) or 1

print(f"Total records: {len(records)}")
print(f"Attack cases:  {len(attack)}")
print(f"Leaked:        {leaked} ({leaked/n*100:.1f}%)")
print()
print(f"=== Adjudicator Decisions ===")
print(f"Confirmed attack:     {confirmed} ({confirmed/n*100:.1f}%)")
print(f"Denied (overruled):   {denied} ({denied/n*100:.1f}%)")
print()

# Of confirmed attacks, how many still leaked?
confirmed_leaked = sum(1 for r in attack if r.get("adjudicator_confirmed") and r["leaked"])
confirmed_blocked = sum(1 for r in attack if r.get("adjudicator_confirmed") and not r["leaked"])
print(f"Confirmed → leaked:    {confirmed_leaked}")
print(f"Confirmed → blocked:  {confirmed_blocked}")
if confirmed:
    print(f"  Repair success rate: {confirmed_blocked/confirmed*100:.1f}%")

# Of denied, how many leaked?
denied_leaked = sum(1 for r in attack if r.get("or_triggered") and not r.get("adjudicator_confirmed") and r["leaked"])
denied_blocked = sum(1 for r in attack if r.get("or_triggered") and not r.get("adjudicator_confirmed") and not r["leaked"])
print(f"Denied → leaked:       {denied_leaked}")
print(f"Denied → blocked:     {denied_blocked}")
print()
print(f"Adjudicator latency (median): ", end="")

lats = [r.get("adjudicator_latency_ms") for r in records if r.get("adjudicator_latency_ms")]
if lats:
    lats.sort()
    print(f"{lats[len(lats)//2]:.0f}ms")
else:
    print("N/A (no adjudicator calls yet)")