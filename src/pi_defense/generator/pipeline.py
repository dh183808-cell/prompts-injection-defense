"""数据生成器 CLI — 编排直接/间接/正常样本生成（Section 10）。

用法：
    python -m pi_defense.generator \\
        --output data/generated/b0_formal.jsonl \\
        --canary-map data/generated/canary_map.json \\
        --direct-per-family 5 \\
        --indirect-per-cell 2 \\
        --benign-count 35 \\
        --languages zh en \\
        --seed 42
"""

import argparse
import json
import random
from pathlib import Path

from pi_defense.canary import generate_canary
from pi_defense.generator.base_tasks import ALL_TASKS
from pi_defense.generator.benign import generate_benign_cases
from pi_defense.generator.direct import generate_direct_cases
from pi_defense.generator.indirect import generate_indirect_cases
from pi_defense.schemas import ExperimentCase


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """解析生成器 CLI 参数。"""
    parser = argparse.ArgumentParser(
        description="提示注入防御实验 — 数据生成器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--output",
        default="data/generated/b0_formal.jsonl",
        help="输出 JSONL 路径（默认：data/generated/b0_formal.jsonl）",
    )
    parser.add_argument(
        "--canary-map",
        default=None,
        help="金丝雀映射 JSON 输出路径（默认：输出同目录下的 canary_map.json）",
    )
    parser.add_argument(
        "--direct-per-family",
        type=int,
        default=5,
        help="每种直接攻击构造的基础案例数（默认：5）",
    )
    parser.add_argument(
        "--indirect-per-cell",
        type=int,
        default=2,
        help="每个间接组合单元的案例数（默认：2）",
    )
    parser.add_argument(
        "--benign-count",
        type=int,
        default=35,
        help="正常样本总数（默认：35）",
    )
    parser.add_argument(
        "--languages",
        nargs="+",
        default=["zh", "en"],
        choices=["zh", "en"],
        help="语言列表（默认：zh en）",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="随机种子保证可重复性（默认：42）",
    )
    return parser.parse_args(argv)


def _generate_canary_map(cases: list[ExperimentCase], seed: int) -> dict[str, str]:
    """为每个 case 生成唯一金丝雀，用 seed 保证可重复性。"""
    canary_map: dict[str, str] = {}
    for case in cases:
        rng = random.Random(f"canary-{seed}-{case.case_id}")
        canary = generate_canary(case.case_id)
        canary_map[case.case_id] = canary
    return canary_map


def run(args: argparse.Namespace) -> tuple[list[ExperimentCase], dict[str, str]]:
    """执行生成并返回 (cases, canary_map)。"""
    seed = args.seed

    direct_cases = generate_direct_cases(
        base_tasks=ALL_TASKS,
        per_family=args.direct_per_family,
        languages=args.languages,
        seed=seed,
    )

    indirect_cases = generate_indirect_cases(
        base_tasks=ALL_TASKS,
        per_cell=args.indirect_per_cell,
        languages=args.languages,
        seed=seed,
    )

    benign_cases = generate_benign_cases(
        base_tasks=ALL_TASKS,
        benign_count=args.benign_count,
        languages=args.languages,
        seed=seed,
    )

    all_cases = direct_cases + indirect_cases + benign_cases
    canary_map = _generate_canary_map(all_cases, seed)
    return all_cases, canary_map


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    canary_map_path_str = args.canary_map
    if canary_map_path_str is None:
        canary_map_path_str = str(output_path.parent / "canary_map.json")
    canary_map_path = Path(canary_map_path_str)

    cases, canary_map = run(args)

    with output_path.open("w", encoding="utf-8") as f:
        for case in cases:
            f.write(case.model_dump_json(exclude_none=True) + "\n")

    with canary_map_path.open("w", encoding="utf-8") as f:
        json.dump(canary_map, f, ensure_ascii=False, indent=2)

    kinds = {}
    for c in cases:
        kinds[c.kind] = kinds.get(c.kind, 0) + 1

    print("===== 数据集生成完成 =====")
    print(f"  输出文件：{output_path}")
    print(f"  金丝雀映射：{canary_map_path}")
    for k in ["benign", "direct", "indirect"]:
        print(f"    {k}: {kinds.get(k, 0)}")
    print(f"  总计：{len(cases)}")
    print(f"  种子：{args.seed}")


if __name__ == "__main__":
    main()