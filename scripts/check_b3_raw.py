"""检查 B3-v2 裁决器原始输出是否完整写入。"""
import json

with open("runs/b3_v2.jsonl") as f:
    records = [json.loads(l) for l in f if l.strip()]

attack = [r for r in records if r["kind"] in ("direct", "indirect")]
overruled = [r for r in attack if r.get("or_triggered") and not r.get("adjudicator_confirmed")]

print(f"总记录: {len(records)}, 攻击: {len(attack)}")
print(f"裁决器否决: {len(overruled)}")
print()

for r in overruled:
    raw = r.get("adjudicator_raw") or ""
    has_raw = len(raw.strip()) > 20
    status = "LEAKED" if r["leaked"] else "OK"
    print(f"[{status}] {r['case_id']}  has_raw={has_raw}  raw_len={len(raw.strip())}")
    if has_raw:
        print(f"  裁决输出: {raw[:200]}")
    print()