import asyncio
import json
from pathlib import Path

from src.pi_defense.canary import (
    generate_canary,
    detect_canary_leak,
)
from src.pi_defense.schemas import ExperimentCase
from src.pi_defense.workflows.b0 import run_b0


TARGET_PROVIDER = "siliconflow"
TARGET_MODEL = "<替换成你查询到的真实模型ID>"


def load_cases(path: str):
    cases = []

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                cases.append(
                    ExperimentCase.model_validate_json(line)
                )

    return cases


async def main():
    cases = load_cases("data/smoke_cases.jsonl")

    output_path = Path("runs/b0_smoke.jsonl")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as out:
        for case in cases:
            canary = generate_canary(case.case_id)

            result = await run_b0(
                case=case,
                canary=canary,
                target_provider=TARGET_PROVIDER,
                target_model=TARGET_MODEL,
            )

            leaked, leak_variant = detect_canary_leak(
                result["content"],
                canary,
            )

            record = {
                "case_id": case.case_id,
                "architecture": "B0",
                "kind": case.kind,
                "attack_family": case.attack_family,
                "configured_model": TARGET_MODEL,
                "actual_model": result["actual_model"],
                "target_output": result["content"],
                "leaked": leaked,
                "leak_variant": leak_variant,
                "latency_ms": result["latency_ms"],
                "input_tokens": result["input_tokens"],
                "output_tokens": result["output_tokens"],
            }

            print(json.dumps(record, ensure_ascii=False))

            out.write(
                json.dumps(record, ensure_ascii=False) + "\n"
            )


if __name__ == "__main__":
    asyncio.run(main())
