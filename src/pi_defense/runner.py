"""
命令行入口：提示注入防御实验运行器。

当前支持架构：
    B0 — 无额外防御基线

使用方法：
    python -m pi_defense.runner --architecture B0 --config configs/models.yaml --data data/smoke_cases.jsonl --output runs/b0_smoke.jsonl
"""

import argparse
import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml
from dotenv import load_dotenv

from pi_defense.canary import generate_canary, detect_canary_leak
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


# ── API Key 检查 ──────────────────────────────────────────


def _collect_providers(config: dict) -> set[str]:
    """从配置中递归收集所有需要 API Key 的 provider 名称。"""
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
    """检查所有必需的 API Key 环境变量是否存在。

    缺失时打印提示并退出程序，不打印密钥实际内容。
    """
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


# ── 任务正确性判断 ────────────────────────────────────────


def check_task_correctness(
    target_output: str,
    expected_answer: str | None,
) -> bool | None:
    """最基础的任务正确性判断。

    去除首尾空格并忽略大小写后比较。不使用大模型评判。
    当 expected_answer 为 None 时返回 None（表示不适用）。
    """
    if expected_answer is None:
        return None
    return target_output.strip().lower() == expected_answer.strip().lower()


# ── CLI ────────────────────────────────────────────────────


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(
        description="提示注入防御实验 — B0 无额外防御基线",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--config",
        default="configs/models.yaml",
        help="模型配置文件路径（默认：configs/models.yaml）",
    )
    parser.add_argument(
        "--data",
        default="data/smoke_cases.jsonl",
        help="测试样本 JSONL 文件路径（默认：data/smoke_cases.jsonl）",
    )
    parser.add_argument(
        "--architecture",
        default="B0",
        choices=["B0"],
        help="实验架构（本轮仅支持 B0）",
    )
    parser.add_argument(
        "--output",
        default="runs/b0_smoke.jsonl",
        help="输出 JSONL 路径（默认：runs/b0_smoke.jsonl）",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="仅处理前 N 条样本（默认：全部处理）",
    )
    parser.add_argument(
        "--canary-map",
        default=None,
        help="金丝雀映射 JSON 路径（默认：无，即时生成）",
    )
    parser.add_argument(
        "--system-prompt-mode",
        default="bare",
        choices=["bare", "hardened"],
        help="系统提示词模式：bare（纯基线，无防御指令）或 hardened（5 条安全规则）（默认：bare）",
    )
    return parser.parse_args(argv)


# ── 主流程 ──────────────────────────────────────────────────


async def main(argv: list[str] | None = None) -> None:
    """主入口：加载配置、数据，运行 B0 架构，保存结果。"""
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

    print(f"架构：{args.architecture}")
    print(f"目标模型：{target_model} ({target_provider})")
    print(f"样本数：{len(cases)}")
    print()

    # 4) 加载金丝雀映射（如果有）
    canary_map: dict[str, str] = {}
    if args.canary_map:
        with open(args.canary_map, "r", encoding="utf-8") as f:
            canary_map = json.load(f)

    # 5) 准备运行 ID 和输出路径
    run_stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_id = f"b0_{run_stamp}_{uuid.uuid4().hex[:8]}"

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    records: list[RunRecord] = []
    all_leaked = 0
    all_errors = 0

    # 6) 逐条处理
    for i, case in enumerate(cases):
        # 优先从映射读取金丝雀，回退到即时生成
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

            leaked, leak_variant = detect_canary_leak(
                result["content"],
                canary,
            )

            task_correct = check_task_correctness(
                result["content"],
                case.expected_answer,
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
                task_correct=task_correct,
                latency_ms=result.get("latency_ms"),
                input_tokens=result.get("input_tokens"),
                output_tokens=result.get("output_tokens"),
            )

            status = f"  leaked={leaked}  correct={task_correct}  {result.get('latency_ms', 0):.0f}ms"
            if leaked:
                all_leaked += 1
        except Exception as e:
            record = RunRecord(
                run_id=run_id,
                case_id=case.case_id,
                base_case_id=case.base_case_id,
                architecture=args.architecture,
                kind=case.kind,
                attack_family=case.attack_family,
                configured_model=target_model,
                actual_model=None,
                target_output="",
                leaked=False,
                leak_variant=None,
                task_correct=None,
                latency_ms=None,
                input_tokens=None,
                output_tokens=None,
                error=f"{type(e).__name__}: {e}",
            )
            all_errors += 1
            status = f"  ERROR: {type(e).__name__}"

        with output_path.open("a", encoding="utf-8") as out:
            out.write(record.model_dump_json() + "\n")

        records.append(record)
        print(status)

    # 6) 汇总
    print()
    print(f"===== 完成 =====")
    print(f"  输出文件：{args.output}")
    print(f"  总计：{len(records)} | 泄露：{all_leaked} | 错误：{all_errors}")


if __name__ == "__main__":
    asyncio.run(main())