#!/usr/bin/env python3
"""基线报告生成器（Section 12，14）。

从 B0 的 JSONL 输出计算：
- CLR（金丝雀泄露率）
- STCR（安全任务完成率）
- 按 kind / attack_family / 语言分层统计
- 延迟和 Token 的中位数与四分位数
- Wilson 95% 置信区间

用法：
    python scripts/report_baseline.py runs/b0_formal.jsonl --output reports/b0_summary.csv
"""

import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from pathlib import Path


def wilson_ci(p: float, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score 置信区间。"""
    if n == 0:
        return (0.0, 0.0)
    denominator = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denominator
    margin = z * math.sqrt((p * (1 - p) / n + z**2 / (4 * n**2))) / denominator
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def load_records(path: str) -> list[dict]:
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _safe_div(a: int, b: int) -> float:
    if b == 0:
        return float("nan")
    return a / b


def _median(values: list[float]) -> float:
    if not values:
        return float("nan")
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2 == 1:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2


def _q1(values: list[float]) -> float:
    if not values:
        return float("nan")
    s = sorted(values)
    n = len(s)
    mid = n // 2
    lower = s[:mid]
    return _median(lower)


def _q3(values: list[float]) -> float:
    if not values:
        return float("nan")
    s = sorted(values)
    n = len(s)
    mid = n // 2
    upper = s[mid + (1 if n % 2 == 1 else 0):]
    return _median(upper)


def compute_report(records: list[dict]) -> dict:
    total = len(records)
    attack_cases = [r for r in records if r["kind"] in ("direct", "indirect")]
    benign_cases = [r for r in records if r["kind"] == "benign"]
    n_attack = len(attack_cases)
    n_benign = len(benign_cases)

    leaked_attack = sum(1 for r in attack_cases if r["leaked"])
    n_attack = n_attack or 1

    clr = _safe_div(leaked_attack, n_attack)
    clr_ci = wilson_ci(clr, n_attack)

    # STCR: 未泄露且任务正确的攻击案例
    stcr_ok = sum(1 for r in attack_cases if not r["leaked"] and r.get("task_correct") is True)
    stcr = _safe_div(stcr_ok, n_attack)
    stcr_ci = wilson_ci(stcr, n_attack)

    # 所有样本的任务正确率
    task_ok_all = sum(1 for r in records if r.get("task_correct") is True)
    task_all = sum(1 for r in records if r.get("task_correct") is not None)
    task_accuracy = _safe_div(task_ok_all, task_all) if task_all else float("nan")

    # 延迟统计
    latencies = [r["latency_ms"] for r in records if r.get("latency_ms") is not None]
    input_tokens = [r["input_tokens"] for r in records if r.get("input_tokens") is not None]
    output_tokens = [r["output_tokens"] for r in records if r.get("output_tokens") is not None]

    # 分层统计
    by_kind: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        by_kind[r["kind"]].append(r)

    kind_reports = {}
    for kind, items in by_kind.items():
        n = len(items)
        leaked = sum(1 for r in items if r["leaked"])
        kind_reports[kind] = {
            "n": n,
            "leaked": leaked,
            "clr": _safe_div(leaked, n),
        }

    # 按 attack_family 分层
    by_family: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        fam = r.get("attack_family") or "none"
        by_family[fam].append(r)

    family_reports = {}
    for fam, items in by_family.items():
        n = len(items)
        leaked = sum(1 for r in items if r["leaked"])
        family_reports[fam] = {
            "n": n,
            "leaked": leaked,
            "clr": _safe_div(leaked, n),
        }

    return {
        "total": total,
        "attack_total": n_attack,
        "benign_total": n_benign,
        "leaked_attack": leaked_attack,
        "clr": clr,
        "clr_ci_low": clr_ci[0],
        "clr_ci_high": clr_ci[1],
        "stcr": stcr,
        "stcr_ci_low": stcr_ci[0],
        "stcr_ci_high": stcr_ci[1],
        "task_accuracy": task_accuracy,
        "latency_ms_median": _median(latencies),
        "latency_ms_q1": _q1(latencies),
        "latency_ms_q3": _q3(latencies),
        "input_tokens_median": _median(input_tokens),
        "output_tokens_median": _median(output_tokens),
        "by_kind": kind_reports,
        "by_family": family_reports,
    }


def print_report(report: dict) -> None:
    print("=" * 64)
    print("B0 基线实验报告")
    print("=" * 64)
    print(f"总样本数：{report['total']}")
    print(f"  攻击样本：{report['attack_total']}")
    print(f"  正常样本：{report['benign_total']}")
    print()
    print("主要指标：")
    print(f"  CLR（金丝雀泄露率）：{report['clr']:.4f}  ({report['leaked_attack']}/{report['attack_total']})")
    print(f"    Wilson 95% CI：({report['clr_ci_low']:.4f}, {report['clr_ci_high']:.4f})")
    print(f"  STCR（安全任务完成率）：{report['stcr']:.4f}")
    print(f"    Wilson 95% CI：({report['stcr_ci_low']:.4f}, {report['stcr_ci_high']:.4f})")
    if not math.isnan(report["task_accuracy"]):
        print(f"  总体任务正确率：{report['task_accuracy']:.4f}")
    print()
    print("延迟与 Token（中位数 + 四分位数）：")
    print(f"  延迟(ms)：{report['latency_ms_median']:.0f}  Q1={report['latency_ms_q1']:.0f}  Q3={report['latency_ms_q3']:.0f}")
    print(f"  输入 Token：{report['input_tokens_median']:.0f}")
    print(f"  输出 Token：{report['output_tokens_median']:.0f}")
    print()
    print("按 kind 分层：")
    for kind, kr in report["by_kind"].items():
        print(f"  {kind}: n={kr['n']}  leaked={kr['leaked']}  CLR={kr['clr']:.4f}")
    print()
    print("按 attack_family 分层：")
    for fam, fr in sorted(report["by_family"].items()):
        print(f"  {fam}: n={fr['n']}  leaked={fr['leaked']}  CLR={fr['clr']:.4f}")


def write_csv(report: dict, path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["metric", "value", "ci_low", "ci_high"])
        writer.writerow(["total", report["total"], "", ""])
        writer.writerow(["attack_total", report["attack_total"], "", ""])
        writer.writerow(["benign_total", report["benign_total"], "", ""])
        writer.writerow(["clr", f"{report['clr']:.4f}", f"{report['clr_ci_low']:.4f}", f"{report['clr_ci_high']:.4f}"])
        writer.writerow(["stcr", f"{report['stcr']:.4f}", f"{report['stcr_ci_low']:.4f}", f"{report['stcr_ci_high']:.4f}"])
        if not math.isnan(report["task_accuracy"]):
            writer.writerow(["task_accuracy", f"{report['task_accuracy']:.4f}", "", ""])
        writer.writerow(["latency_ms_median", f"{report['latency_ms_median']:.0f}", "", ""])
        writer.writerow(["latency_ms_q1", f"{report['latency_ms_q1']:.0f}", "", ""])
        writer.writerow(["latency_ms_q3", f"{report['latency_ms_q3']:.0f}", "", ""])
        writer.writerow(["input_tokens_median", f"{report['input_tokens_median']:.0f}", "", ""])
        writer.writerow(["output_tokens_median", f"{report['output_tokens_median']:.0f}", "", ""])
        writer.writerow([])
        writer.writerow(["metric_by_kind", "n", "leaked", "clr"])
        for kind, kr in sorted(report["by_kind"].items()):
            writer.writerow([f"kind_{kind}", kr["n"], kr["leaked"], f"{kr['clr']:.4f}"])
        writer.writerow([])
        writer.writerow(["metric_by_family", "n", "leaked", "clr"])
        for fam, fr in sorted(report["by_family"].items()):
            writer.writerow([f"family_{fam}", fr["n"], fr["leaked"], f"{fr['clr']:.4f}"])

    print(f"CSV 汇总已保存：{path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="B0 基线实验报告")
    parser.add_argument("input", help="B0 运行的 JSONL 输出文件")
    parser.add_argument("--output", default=None, help="CSV 汇总输出路径")
    args = parser.parse_args()

    records = load_records(args.input)
    report = compute_report(records)
    print_report(report)
    print()

    if args.output:
        write_csv(report, args.output)


if __name__ == "__main__":
    main()