"""Command-line entry point for prompt injection defense experiments.

Supported architectures: B0, B1, B2, B3
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
from pi_defense.workflows.b2 import run_b2
from pi_defense.workflows.b3 import run_b3

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
    parser.add_argument("--experiment-name", default=None, help="Tag written into each run_id")
    parser.add_argument("--system-prompt-mode", default="minimal", choices=["minimal", "hardened"],
                        help="minimal or hardened system prompt")
    parser.add_argument("--dataset-seed", type=int, default=None, help="Dataset random seed")
    parser.add_argument("--max-concurrency", type=int, default=1,
                        help="Max concurrent samples (default 1 = sequential)")
    return parser.parse_args(argv)


async def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    # 1) Load config
    config = load_config(args.config)
    target_cfg = config["target"]
    target_provider: str = target_cfg["provider"]
    target_model: str = target_cfg["model"]

    defender_provider = defender_model = ""
    if args.architecture == "B1":
        defender_cfg = config.get("strong_defender", {})
        defender_provider = defender_cfg.get("provider", "")
        defender_model = defender_cfg.get("model", "")

    detector_configs: list[dict] = []
    repair_provider = repair_model = adjudicator_provider = adjudicator_model = ""
    if args.architecture in ("B2", "B3"):
        detector_configs_raw = config.get("detectors", {})
        detector_configs = [
            {"type": label, "provider": d.get("provider", ""), "model": d.get("model", "")}
            for label, d in detector_configs_raw.items()
        ]
        repair_cfg = config.get("repair", {})
        repair_provider = repair_cfg.get("provider", "")
        repair_model = repair_cfg.get("model", "")
    if args.architecture == "B3":
        adj_cfg = config.get("adjudicator", {})
        adjudicator_provider = adj_cfg.get("provider", "")
        adjudicator_model = adj_cfg.get("model", "")

    # 2) Check API keys
    check_api_keys(config)

    # 3) Load cases
    cases = load_cases(args.data)
    if args.limit is not None:
        cases = cases[: args.limit]

    dataset_hash = compute_dataset_hash(args.data)

    canary_map: dict[str, str] = {}
    if args.canary_map:
        with open(args.canary_map, "r", encoding="utf-8") as f:
            canary_map = json.load(f)

    git_commit = _get_git_commit()
    exp_tag = args.experiment_name or args.architecture
    run_stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_id = f"{exp_tag}_{run_stamp}_{uuid.uuid4().hex[:8]}"
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Architecture: {args.architecture}")
    print(f"Experiment:   {exp_tag}")
    print(f"Prompt mode:  {args.system_prompt_mode}")
    print(f"Target:       {target_model} ({target_provider})")
    print(f"Concurrency:  {args.max_concurrency}")
    if args.architecture == "B1":
        print(f"Defender:     {defender_model} ({defender_provider})")
    if args.architecture in ("B2", "B3"):
        for dc in detector_configs:
            print(f"  Detector:   {dc['type']:12s} {dc['model']} ({dc['provider']})")
        print(f"  Repair:      {repair_model} ({repair_provider})")
    if args.architecture == "B3":
        print(f"  Adjudicator: {adjudicator_model} ({adjudicator_provider})")
    print(f"Samples:      {len(cases)}")
    print(f"Dataset hash: {dataset_hash}")
    print(f"Git commit:   {git_commit}")
    print()

    sem = asyncio.Semaphore(args.max_concurrency)

    async def process_one(case: ExperimentCase) -> RunRecord:
        canary = canary_map.get(case.case_id) or generate_canary(case.case_id)
        async with sem:
            try:
                if args.architecture == "B0":
                    result = await run_b0(case=case, canary=canary,
                                          target_provider=target_provider, target_model=target_model,
                                          system_prompt_mode=args.system_prompt_mode)
                elif args.architecture == "B1":
                    result = await run_b1(case=case, canary=canary,
                                          target_provider=target_provider, target_model=target_model,
                                          defender_provider=defender_provider, defender_model=defender_model,
                                          system_prompt_mode=args.system_prompt_mode)
                elif args.architecture == "B2":
                    result = await run_b2(case=case, canary=canary,
                                          target_provider=target_provider, target_model=target_model,
                                          detector_configs=detector_configs,
                                          repair_provider=repair_provider, repair_model=repair_model,
                                          system_prompt_mode=args.system_prompt_mode)
                elif args.architecture == "B3":
                    result = await run_b3(case=case, canary=canary,
                                          target_provider=target_provider, target_model=target_model,
                                          detector_configs=detector_configs,
                                          adjudicator_provider=adjudicator_provider,
                                          adjudicator_model=adjudicator_model,
                                          repair_provider=repair_provider, repair_model=repair_model,
                                          system_prompt_mode=args.system_prompt_mode)
                else:
                    raise NotImplementedError(f"Architecture {args.architecture} not yet implemented")

                leaked, leak_variant = detect_canary_leak(result["content"], canary)
                score = score_task(result["content"], case.expected_answer)

                kwargs = dict(
                    run_id=run_id, case_id=case.case_id, base_case_id=case.base_case_id,
                    architecture=args.architecture, kind=case.kind, attack_family=case.attack_family,
                    configured_model=target_model, actual_model=result.get("actual_model"),
                    target_output=result["content"], leaked=leaked, leak_variant=leak_variant,
                    task_correct_auto=score["task_correct_auto"],
                    task_correct_manual=score["task_correct_manual"],
                    task_correct=score["task_correct_auto"],
                    failure_category=score["failure_category"],
                    over_refusal=score["over_refusal"], task_hijacked=score["task_hijacked"],
                    latency_ms=result.get("latency_ms"), input_tokens=result.get("input_tokens"),
                    output_tokens=result.get("output_tokens"),
                    system_prompt_mode=args.system_prompt_mode,
                    system_prompt_hash=result.get("_system_prompt_hash"),
                    dataset_seed=args.dataset_seed, dataset_hash=dataset_hash,
                    temperature=0.0, max_tokens=256, git_commit=git_commit,
                )

                # B1 fields
                if args.architecture == "B1":
                    kwargs["defender_is_attack"] = result.get("_b1_is_attack", False)
                    kwargs["defender_repaired"] = result.get("_b1_repaired", False)
                    kwargs["defender_model"] = result.get("_defender_actual_model", "")
                    kwargs["defender_latency_ms"] = result.get("_defender_latency_ms")
                    kwargs["defender_input_tokens"] = result.get("_defender_input_tokens")
                    kwargs["defender_output_tokens"] = result.get("_defender_output_tokens")
                    kwargs["defender_raw"] = result.get("_b1_defender_raw")

                # B2/B3 shared fields
                if args.architecture in ("B2", "B3"):
                    for i in range(3):
                        kwargs[f"detector_{i}_suspicious"] = result.get(f"_detector_{i}_suspicious")
                        kwargs[f"detector_{i}_latency_ms"] = result.get(f"_detector_{i}_latency_ms")
                        kwargs[f"detector_{i}_model"] = result.get(f"_detector_{i}_model")
                    kwargs["or_triggered"] = result.get("_or_triggered", False)
                    kwargs["repair_action"] = result.get("_repair_action")
                    kwargs["repair_latency_ms"] = result.get("_repair_latency_ms")
                    kwargs["repair_model"] = result.get("_repair_model")
                    kwargs["repair_raw"] = result.get("_repair_raw")

                # B3-only fields
                if args.architecture == "B3":
                    kwargs["adjudicator_confirmed"] = result.get("_adjudicator_confirmed", False)
                    kwargs["adjudicator_action"] = result.get("_adjudicator_action")
                    kwargs["adjudicator_latency_ms"] = result.get("_adjudicator_latency_ms")
                    kwargs["adjudicator_model"] = result.get("_adjudicator_model")
                    kwargs["adjudicator_raw"] = result.get("_adjudicator_raw")

                return RunRecord(**kwargs)

            except Exception as e:
                return RunRecord(
                    run_id=run_id, case_id=case.case_id, base_case_id=case.base_case_id,
                    architecture=args.architecture, kind=case.kind, attack_family=case.attack_family,
                    configured_model=target_model, target_output="", leaked=False,
                    error=f"{type(e).__name__}: {e}",
                    system_prompt_mode=args.system_prompt_mode,
                    dataset_seed=args.dataset_seed, dataset_hash=dataset_hash,
                    temperature=0.0, max_tokens=256, git_commit=git_commit,
                )

    # Process with concurrency
    tasks = [process_one(case) for case in cases]
    records = []
    for coro in asyncio.as_completed(tasks):
        record = await coro
        records.append(record)

        with output_path.open("a", encoding="utf-8") as out:
            out.write(record.model_dump_json() + "\n")

        # Status line
        parts = []
        if record.error:
            parts.append(f"  ERROR: {record.error[:60]}")
        else:
            parts.append(f"  leaked={record.leaked}  correct={record.task_correct_auto}")
            if record.latency_ms:
                parts.append(f"  {record.latency_ms:.0f}ms")
            if record.failure_category and record.failure_category != "none":
                parts.append(f"  [{record.failure_category}]")
        print(f"[{len(records)}/{len(cases)}] {record.case_id}  kind={record.kind}", end="")
        print("".join(parts))

    # Summary
    all_leaked = sum(1 for r in records if r.leaked)
    all_errors = sum(1 for r in records if r.error)
    over = sum(1 for r in records if r.over_refusal)
    hij = sum(1 for r in records if r.task_hijacked)
    print()
    print(f"===== Complete =====")
    print(f"  Output:     {args.output}")
    print(f"  Total:      {len(records)} | Leaked: {all_leaked} | Errors: {all_errors}")
    print(f"  Over-refusal: {over} | Hijacked: {hij}")
    if args.experiment_name:
        print(f"  Experiment: {args.experiment_name}")


if __name__ == "__main__":
    asyncio.run(main())