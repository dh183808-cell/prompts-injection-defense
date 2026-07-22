#!/usr/bin/env python3
"""Compare all B0/B1 experiment results in a table."""

import json
import sys
from pathlib import Path


def load(path: str) -> list[dict]:
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]


def stats(name: str, records: list[dict]) -> dict:
    attack = [r for r in records if r["kind"] in ("direct", "indirect")]
    benign = [r for r in records if r["kind"] == "benign"]
    leaked = sum(1 for r in attack if r["leaked"])
    correct = sum(
        1 for r in attack if (not r["leaked"]) and r.get("task_correct_auto") is True
    )
    over_refusal = sum(1 for r in records if r.get("over_refusal"))
    hijacked = sum(1 for r in records if r.get("task_hijacked"))
    errors = sum(1 for r in records if r.get("error"))
    n_attack = len(attack) or 1

    return {
        "name": name,
        "attack": len(attack),
        "benign": len(benign),
        "leaked": leaked,
        "correct": correct,
        "clr": f"{leaked}/{len(attack)} = {leaked/len(attack)*100:.1f}%"
        if attack
        else "N/A",
        "stcr": f"{correct}/{len(attack)} = {correct/len(attack)*100:.1f}%"
        if attack
        else "N/A",
        "over_refusal": over_refusal,
        "task_hijacked": hijacked,
        "errors": errors,
    }


def main() -> None:
    runs_dir = Path("runs")
    experiment_files = {
        "B0-Minimal": runs_dir / "b0_minimal.jsonl",
        "B0-Hardened": runs_dir / "b0_hardened.jsonl",
        "B1 (Nex-N2-Pro)": runs_dir / "b1_nex.jsonl",
    }

    results = {}
    for name, path in experiment_files.items():
        if not path.exists():
            print(f"⚠  {name}: {path} not found, skipping")
            continue
        results[name] = stats(name, load(str(path)))

    if not results:
        print("No experiment files found.")
        sys.exit(1)

    print("=" * 88)
    print(
        f"{'实验':<32} {'攻击':>6} {'正常':>6} {'泄露':>6} {'CLR':>16} {'STCR':>16} {'拒绝':>6} {'劫持':>6} {'错误':>6}"
    )
    print("-" * 88)
    for name, s in results.items():
        print(
            f'{s["name"]:<32} {s["attack"]:>6} {s["benign"]:>6} {s["leaked"]:>6} '
            f'{s["clr"]:>16} {s["stcr"]:>16} {s["over_refusal"]:>6} {s["task_hijacked"]:>6} {s["errors"]:>6}'
        )
    print("=" * 88)


if __name__ == "__main__":
    main()