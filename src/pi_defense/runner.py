"""
命令行入口：提示注入防御实验运行器。

当前支持架构：
    B0 — 无额外防御基线

使用方法：
    python -m pi_defense.runner --architecture B0 --experiment-name B0-Minimal
"""

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml
from dotenv import load_dotenv

from pi_defense.canary import generate_canary, detect_canary_leak
from pi_defense.scoring import score_task
from pi_defense.schemas import ExperimentCase, RunRecord
from pi_defense.workflows.b0 import run_b0

load_dotenv()


# ── 配置加载 ──────────────────────────────────────────────


def load_config(path: str) -> dict:
    """加载 YAML 模型配置文件。"""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ── 数据加载 ──────────────────────────────────────────────


def load_cases(path: str) -> list[ExperimentCase]:
    """从 JSONL 文件加载实验样本。"""
    cases: list[ExperimentCase] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(ExperimentCase.model_validate_json(line))
    return cases


def compute_dataset_hash(path: str) -> str:
    """对 JSONL 文件内容取 SHA256 摘要（16 位短格式）。"""
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            sha.update(chunk)
    return sha.hexdigest()[:16]


# ── API Key 检查 ──────────────────────────────────────────


def _collect_providers(config: dict) -> set[str]:
    providers: set[str] = set()

    def walk(d: object) -> None:
        if isinstance(d, dict):
            if "provider" in d:
                providers.add(d["provider"])
            for val in d.values():
                walk(val)
        elif isinstance(d, list):
            for item in d:
                walk(item)

    walk(config)
    return providers


def check_api_keys(config: dict) -> None:
    providers = _collect_providers(config)
    missing: list[str] = []
    for prov in sorted(providers):
        env_key = f"{prov.upper()}_API_KEY"
        if not os.getenv(env_key):
            missing.append(env_key)
    if missing:
        print("=" * 60)
        print("  错误：以下 API Key 环境变量未设置：")
        print()
        for key in sorted(missing):
            print(f"      {key}")
        print()
        print("  请创建 .env 文件并设置上述变量，参考 .env.example。")
        print("=" * 60)
        sys.exit(1)


# ── Git commit 获取 ────────────────────────────────────────


def _get_git_commit() -> str | None:
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                stderr=subprocess.DEVNULL,
                cwd=Path(__file__).resolve().parent,
            )
            .decode()
            .strip()
        )
    except Exception:
        return None


# ── CLI ────────────────────────────────────────────────────


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="提示注入防御实验运行器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--config", default="configs/models.yaml")
    parser.add_argument("--data", default="data/smoke_cases.jsonl")
    parser.add_argument(
        "--architecture",
        default="B0",
        choices=["B0", "B1", "B2", "B3"],
    )
    parser.add_argument("--output", default="runs/b0_smoke.jsonl")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--canary-map", default=None)
    parser.add_argument(
        "--experiment-name",
        default=None,
        help="实验名称标签（如 B0-Minimal、B0-Hardened），将写入每条记录的 run_id",
    )
    parser.add_argument(
        "--system-prompt-mode",
        default="minimal",
        choices=["minimal", "hardened"],
        help="system prompt mode: minimal (no defensive wording) or hardened (5 rules)",
    )
    parser.add_argument(
        "--dataset-seed",
        type=int,
        default=None,
        help="数据集生成时的随机种子（如 42），写入每条记录作为 dataset_seed",
    )
    return parser.parse_args(argv)


# ── 主流程 ──────────────────────────────────────────────────


async def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    # 1) 加载配置
    config = load_config(args.config)
    target_cfg = config["target"]
    target_provider: str = target_cfg["provider"]
    target_model: str = target_cfg["model"]

    # 2) 检查 API Key
    check_api_keys(config)

    # 3) 加载样本
    cases = load_cases(args.data)
    if args.limit is not None:
        cases = cases[: args.limit]

    # 4) 计算数据集哈希
    dataset_hash = compute_dataset_hash(args.data)

    # 5) 加载金丝雀映射（如果有）
    canary_map: dict[str, str] = {}
    if args.canary_map:
        with open(args.canary_map, "r", encoding="utf-8") as f:
            canary_map = json.load(f)

    # 6) 获取 git commit
    git_commit = _get_git_commit()

    # 7) 准备运行 ID 和输出路径
    exp_tag = args.experiment_name or args.architecture
    run_stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_id = f"{exp_tag}_{run_stamp}_{uuid.uuid4().hex[:8]}"

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"架构：{args.architecture}")
    print(f"实验名称：{exp_tag}")
    print(f"提示词模式：{args.system_prompt_mode}")
    print(f"目标模型：{target_model} ({target_provider})")
    print(f"样本数：{len(cases)}")
    print(f"数据集哈希：{dataset_hash}")
    print(f"Git commit：{git_commit}")
    print()

    records: list[RunRecord] = []
    all_leaked = 0
    all_errors = 0
    refusal_count = 0
    hijacked_count = 0

    # 8) 逐条处理
    for i, case in enumerate(cases):
        if case.case_id in canary_map:
            canary = canary_map[case.case_id]
        else:
            canary = generate_canary(case.case_id)

        print(f"[{i + 1}/{len(cases)}] {case.case_id}  kind={case.kind}", end="")

        try:
            result = await run_b0(
                case=case,
                canary=canary,
                target_provider=target_provider,
                target_model=target_model,
                system_prompt_mode=args.system_prompt_mode,
            )

            leaked, leak_variant = detect_canary_leak(result["content"], canary)

            score = score_task(
                target_output=result["content"],
                expected_answer=case.expected_answer,
            )

            record = RunRecord(
                run_id=run_id,
                case_id=case.case_id,
                base_case_id=case.base_case_id,
                architecture=args.architecture,
                kind=case.kind,
                attack_family=case.attack_family,
                configured_model=target_model,
                actual_model=result.get("actual_model"),
                target_output=result["content"],
                leaked=leaked,
                leak_variant=leak_variant,
                task_correct_auto=score["task_correct_auto"],
                task_correct_manual=score["task_correct_manual"],
                task_correct=score["task_correct_auto"],
                failure_category=score["failure_category"],
                over_refusal=score["over_refusal"],
                task_hijacked=score["task_hijacked"],
                latency_ms=result.get("latency_ms"),
                input_tokens=result.get("input_tokens"),
                output_tokens=result.get("output_tokens"),
                system_prompt_mode=args.system_prompt_mode,
                system_prompt_hash=result.get("_system_prompt_hash"),
                dataset_seed=args.dataset_seed,
                dataset_hash=dataset_hash,
                temperature=0.0,
                max_tokens=256,
                git_commit=git_commit,
            )

            if leaked:
                all_leaked += 1
            if score["over_refusal"]:
                refusal_count += 1
            if score["task_hijacked"]:
                hijacked_count += 1

        except Exception as e:
            record = RunRecord(
                run_id=run_id,
                case_id=case.case_id,
                base_case_id=case.base_case_id,
                architecture=args.architecture,
                kind=case.kind,
                attack_family=case.attack_family,
                configured_model=target_model,
                target_output="",
                leaked=False,
                latency_ms=None,
                input_tokens=None,
                output_tokens=None,
                error=f"{type(e).__name__}: {e}",
                system_prompt_mode=args.system_prompt_mode,
                dataset_seed=args.dataset_seed,
                dataset_hash=dataset_hash,
                temperature=0.0,
                max_tokens=256,
                git_commit=git_commit,
            )
            all_errors += 1

        with output_path.open("a", encoding="utf-8") as out:
            out.write(record.model_dump_json() + "\n")

        records.append(record)
        status_parts = []
        if record.error:
            status_parts.append(f"  ERROR: {type(record.error).__name__}")
        else:
            status_parts.append(f"  leaked={record.leaked}")
            status_parts.append(f"  correct={record.task_correct_auto}")
            status_parts.append(f"  {record.latency_ms:.0f}ms" if record.latency_ms else "")
            if record.failure_category and record.failure_category != "none":
                status_parts.append(f"  [{record.failure_category}]")
        print("".join(status_parts))

    # 9) 汇总
    print()
    print(f"===== 完成 =====")
    print(f"  输出文件：{args.output}")
    print(f"  总计：{len(records)} | 泄露：{all_leaked} | 错误：{all_errors}")
    print(f"  过度拒绝：{refusal_count} | 任务劫持：{hijacked_count}")
    if args.experiment_name:
        print(f"  实验名称：{args.experiment_name}")


if __name__ == "__main__":
    asyncio.run(main())