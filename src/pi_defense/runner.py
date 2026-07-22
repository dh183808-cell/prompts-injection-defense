"""
Command-line entry point for prompt injection defense experiments.

Supported architectures:
  B0 — no defense (baseline)
  B1 — single strong model detect + repair
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
from pi_defense.workflows.b1 import run_b1

load_dotenv()


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_cases(path: str) -> list[ExperimentCase]:
    cases: list[ExperimentCase] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(ExperimentCase.model_validate_json(line))
    return cases


def compute_dataset_hash(path: str) -> str:
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            sha.update(chunk)
    return sha.hexdigest()[:16]


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
        print("  Error: the following API Keys are not set:")
        print()
        for key in sorted(missing):
            print(f"      {key}")
        print()
        print("  Create a .env file with these variables.")
        print("=" * 60)
        sys.exit(1)


def _get_git_commit() -> str | None:
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                stderr=subprocess.DEVNULL,
                cwd=Path(__file__).resolve().parent,
            ).decode().strip()
        )
    except Exception:
        return None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prompt injection defense experiment runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--config", default="configs/models.yaml")
    parser.add_argument("--data", default="data/smoke_cases.jsonl")
    parser.add_argument("--architecture", default="B0", choices=["B0", "B1", "B2", "B3"])
    parser.add_argument("--output", default="runs/b0_smoke.jsonl")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--canary-map", default=None)
    parser.add_argument("--experiment-name", default=None,
                        help="Tag written into each run_id")
    parser.add_argument("--system-prompt-mode", default="minimal",
                        choices=["minimal", "hardened"],
                        help="minimal or hardened system prompt")
    parser.add_argument("--dataset-seed", type=int, default=None,
                        help="Random seed used to generate the dataset")
    return parser.parse_args(argv)


async def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    # 1) Load config
    config = load_config(args.config)
    target_cfg = config["target"]
    target_provider: str = target_cfg["provider"]
    target_model: str = target_cfg["model"]

    defender_provider = ""
    defender_model = ""
    if args.architecture == "B1":
        defender_cfg = config.get("strong_defender", {})
        defender_provider = defender_cfg.get("provider", "")
        defender_model = defender_cfg.get("model", "")

    # 2) Check API keys
    check_api_keys(config)

    # 3) Load cases
    cases = load_cases(args.data)
    if args.limit is not None:
        cases = cases[: args.limit]

    # 4) Dataset hash
    dataset_hash = compute_dataset_hash(args.data)

    # 5) Canary map
    canary_map: dict[str, str] = {}
    if args.canary_map:
        with open(args.canary_map, "r", encoding="utf-8") as f:
            canary_map = json.load(f)

    # 6) Git commit
    git_commit = _get_git_commit()

    # 7) Run ID
    exp_tag = args.experiment_name or args.architecture
    run_stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_id = f"{exp_tag}_{run_stamp}_{uuid.uuid4().hex[:8]}"

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Architecture: {args.architecture}")
    print(f"Experiment:   {exp_tag}")
    print(f"Prompt mode:  {args.system_prompt_mode}")
    print(f"Target:       {target_model} ({target_provider})")
    if args.architecture == "B1":
        print(f"Defender:     {defender_model} ({defender_provider})")
    print(f"Samples:      {len(cases)}")
    print(f"Dataset hash: {dataset_hash}")
    print(f"Git commit:   {git_commit}")
    print()

    records: list[RunRecord] = []
    all_leaked = 0
    all_errors = 0
    all_adjudicated_attack = 0

    # 8) Process each case
    for i, case in enumerate(cases):
        canary = canary_map.get(case.case_id) or generate_canary(case.case_id)
        print(f"[{i + 1}/{len(cases)}] {case.case_id}  kind={case.kind}", end="")

        try:
            if args.architecture == "B0":
                result = await run_b0(
                    case=case, canary=canary,
                    target_provider=target_provider, target_model=target_model,
                    system_prompt_mode=args.system_prompt_mode,
                )
            elif args.architecture == "B1":
                result = await run_b1(
                    case=case, canary=canary,
                    target_provider=target_provider, target_model=target_model,
                    defender_provider=defender_provider, defender_model=defender_model,
                    system_prompt_mode=args.system_prompt_mode,
                )
            else:
                raise NotImplementedError(
                    f"Architecture {args.architecture} not yet implemented"
                )

            leaked, leak_variant = detect_canary_leak(result["content"], canary)
            score = score_task(result["content"], case.expected_answer)

            # Common fields
            kwargs = dict(
                run_id=run_id, case_id=case.case_id,
                base_case_id=case.base_case_id,
                architecture=args.architecture,
                kind=case.kind, attack_family=case.attack_family,
                configured_model=target_model,
                actual_model=result.get("actual_model"),
                target_output=result["content"],
                leaked=leaked, leak_variant=leak_variant,
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
                temperature=0.0, max_tokens=256,
                git_commit=git_commit,
            )

            # B1-specific fields
            if args.architecture == "B1":
                kwargs["defender_is_attack"] = result.get("_b1_is_attack", False)
                kwargs["defender_repaired"] = result.get("_b1_repaired", False)
                kwargs["defender_model"] = result.get("_defender_actual_model", "")
                kwargs["defender_latency_ms"] = result.get("_defender_latency_ms")
                kwargs["defender_input_tokens"] = result.get("_defender_input_tokens")
                kwargs["defender_output_tokens"] = result.get("_defender_output_tokens")
                kwargs["defender_raw"] = result.get("_b1_defender_raw")

            record = RunRecord(**kwargs)

            if leaked:
                all_leaked += 1
            if result.get("_b1_is_attack"):
                all_adjudicated_attack += 1

        except Exception as e:
            record = RunRecord(
                run_id=run_id, case_id=case.case_id,
                base_case_id=case.base_case_id,
                architecture=args.architecture,
                kind=case.kind, attack_family=case.attack_family,
                configured_model=target_model,
                target_output="", leaked=False,
                error=f"{type(e).__name__}: {e}",
                system_prompt_mode=args.system_prompt_mode,
                dataset_seed=args.dataset_seed, dataset_hash=dataset_hash,
                temperature=0.0, max_tokens=256, git_commit=git_commit,
            )
            all_errors += 1

        with output_path.open("a", encoding="utf-8") as out:
            out.write(record.model_dump_json() + "\n")

        records.append(record)
        parts = []
        if record.error:
            parts.append(f"  ERROR: {record.error[:60]}")
        else:
            parts.append(f"  leaked={record.leaked}  correct={record.task_correct_auto}")
            if args.architecture == "B1":
                parts.append(f"  def-attack={record.defender_is_attack}")
            if record.latency_ms:
                parts.append(f"  {record.latency_ms:.0f}ms")
            if record.failure_category and record.failure_category != "none":
                parts.append(f"  [{record.failure_category}]")
        print("".join(parts))

    # 9) Summary
    print()
    print(f"===== Complete =====")
    print(f"  Output:     {args.output}")
    print(f"  Total:      {len(records)} | Leaked: {all_leaked} | Errors: {all_errors}")
    if args.architecture == "B1":
        print(f"  Defender flagged as attack: {all_adjudicated_attack}")
    over = sum(1 for r in records if r.over_refusal)
    hij = sum(1 for r in records if r.task_hijacked)
    print(f"  Over-refusal: {over} | Hijacked: {hij}")
    if args.experiment_name:
        print(f"  Experiment: {args.experiment_name}")


if __name__ == "__main__":
    asyncio.run(main())