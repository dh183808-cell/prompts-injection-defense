#!/bin/bash
# Quick B3 v1 vs v2 comparison
cd "$(dirname "$0")/.."

echo "=== B3 v1 (old adjudicator) ==="
python3 -c "
import json
with open('runs/b3.jsonl') as f:
    r = [json.loads(l) for l in f if l.strip()]
a = [x for x in r if x['kind'] in ('direct','indirect')]
print(f'  Records: {len(r)}, Attack: {len(a)}')
print(f'  Leaked:  {sum(1 for x in a if x[\"leaked\"])}/{len(a)} = {sum(1 for x in a if x[\"leaked\"])/len(a)*100:.1f}%')
print(f'  Confirm: {sum(1 for x in a if x.get(\"adjudicator_confirmed\"))}/{len(a)} = {sum(1 for x in a if x.get(\"adjudicator_confirmed\"))/len(a)*100:.1f}%')
"

echo ""
echo "=== B3 v2 (new adjudicator) ==="
python3 -c "
import json
with open('runs/b3_v2.jsonl') as f:
    r = [json.loads(l) for l in f if l.strip()]
a = [x for x in r if x['kind'] in ('direct','indirect')]
print(f'  Records: {len(r)}, Attack: {len(a)}')
print(f'  Leaked:  {sum(1 for x in a if x[\"leaked\"])}/{len(a)} = {sum(1 for x in a if x[\"leaked\"])/len(a)*100:.1f}%')
print(f'  Confirm: {sum(1 for x in a if x.get(\"adjudicator_confirmed\"))}/{len(a)} = {sum(1 for x in a if x.get(\"adjudicator_confirmed\"))/len(a)*100:.1f}%')
# Show conservative_block counts
cb = sum(1 for x in a if x.get('adjudicator_action') == 'conservative_block')
print(f'  conservative_block: {cb}')
# Show what adjudicator_raw contains for first conservative_block case
for x in a:
    if x.get('adjudicator_action') == 'conservative_block':
        raw = x.get('adjudicator_raw', '') or ''
        print(f'  Sample adjudicator output: {raw[:200]}')
        break
"