"""Check B3 v2 overruled cases."""
import json

with open('runs/b3_v2.jsonl') as f:
    records = [json.loads(l) for l in f if l.strip()]

attack = [r for r in records if r['kind'] in ('direct','indirect')]
overruled = [r for r in attack if r.get('or_triggered') and not r.get('adjudicator_confirmed')]

print(f"否决总数: {len(overruled)}")
print(f"否决且泄露: {sum(1 for r in overruled if r['leaked'])}")
print()

for r in overruled:
    raw = r.get('adjudicator_raw', '') or ''
    has = bool(raw and len(raw) > 10)
    print(f"[{'LEAKED' if r['leaked'] else 'OK'}] {r['case_id']}  has_raw={has}  len_raw={len(raw)}")
    if has:
        print(f"  裁决输出: {raw[:250]}")
    print()