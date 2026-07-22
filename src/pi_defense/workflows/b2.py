"""
B2 workflow: three parallel heterogeneous detectors + OR routing + repair agent.

Architecture:
  1. Boundary detector (Agent A) — instruction boundary & direct override detection
  2. Semantic detector (Agent B) — semantic intent & role impersonation detection
  3. Indirect detector (Agent C) — indirect injection & format confusion detection
  4. OR trigger: ANY detector suspicious → call repair agent
  5. Repair agent cleans the prompt
  6. ALL pass → original content goes to target model
"""

import asyncio
import json
import re
from typing import Any

from pi_defense.clients import chat_completion
from pi_defense.prompts import (
    BOUNDARY_DETECTOR_PROMPT,
    SEMANTIC_DETECTOR_PROMPT,
    INDIRECT_DETECTOR_PROMPT,
    REPAIR_PROMPT,
    build_target_system_prompt,
    build_target_user_prompt,
    compute_system_prompt_hash,
)


# ── JSON extraction helper (shared) ──────────────────

def _extract_json(text: str) -> dict[str, Any] | None:
    text = text.strip()
    # Direct full parse
    if text.startswith("{"):
        try: return json.loads(text)
        except json.JSONDecodeError: pass
    # Code fence: ```json ... ``` or ``` ... ```
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if m:
        inner = m.group(1).strip()
        if inner.startswith("{"):
            try: return json.loads(inner)
            except json.JSONDecodeError: pass
    # First { ... } block（non-greedy, multi-line）
    m = re.search(r"\{[^{}]*", text, re.DOTALL)
    if m:
        # Walk forward to find matching brace
        start = m.start()
        depth = 0
        for i in range(start, len(text)):
            if text[i] == '{': depth += 1
            elif text[i] == '}': depth -= 1
            if depth == 0:
                try: return json.loads(text[start:i+1])
                except json.JSONDecodeError: break
    return None


def _is_suspicious(parsed: dict[str, Any] | None) -> bool:
    if parsed is None:
        return True  # parse failure → conservative: treat as suspicious
    for key in ("suspicious", "is_attack", "suspicious"):
        val = parsed.get(key)
        if val is True or val is False:
            return bool(val)
    return True  # no verdict key → conservative


# ── Single detector call ─────────────────────────────

async def _run_detector(
    provider: str,
    model: str,
    prompt: str,
    user_input: str,
    external_content: str,
    label: str,
) -> dict:
    full_content = f"User input:\n{user_input}"
    if external_content:
        full_content += f"\n\nExternal content:\n{external_content}"

    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": full_content},
    ]

    result = await chat_completion(
        provider=provider, model=model,
        messages=messages, temperature=0.0, max_tokens=512,
    )

    content = result["content"]
    parsed = _extract_json(content)

    return {
        "label": label,
        "suspicious": _is_suspicious(parsed),
        "parsed": parsed,
        "raw": content,
        "latency_ms": result.get("latency_ms"),
        "input_tokens": result.get("input_tokens"),
        "output_tokens": result.get("output_tokens"),
        "actual_model": result.get("actual_model"),
    }


# ── Repair agent ─────────────────────────────────────

async def _run_repair(
    provider: str,
    model: str,
    task: str,
    user_input: str,
    external_content: str,
    detector_reports: list[dict],
) -> dict:
    reports_text = json.dumps([
        {"detector": r["label"], "suspicious": r["suspicious"],
         "parsed": r.get("parsed")}
        for r in detector_reports
    ], indent=2, ensure_ascii=False)

    full_content = (
        f"Trusted task:\n{task}\n\n"
        f"User input:\n{user_input}\n\n"
        f"External content:\n{external_content or '(none)'}\n\n"
        f"Detection reports:\n{reports_text}"
    )

    messages = [
        {"role": "system", "content": REPAIR_PROMPT},
        {"role": "user", "content": full_content},
    ]

    result = await chat_completion(
        provider=provider, model=model,
        messages=messages, temperature=0.0, max_tokens=1024,
    )

    content = result["content"]
    parsed = _extract_json(content)

    return {
        "parsed": parsed,
        "raw": content,
        "latency_ms": result.get("latency_ms"),
        "input_tokens": result.get("input_tokens"),
        "output_tokens": result.get("output_tokens"),
        "actual_model": result.get("actual_model"),
    }


# ── B2 main workflow ─────────────────────────────────

async def run_b2(
    case,
    canary: str,
    target_provider: str,
    target_model: str,
    detector_configs: list[dict],       # [{"provider": ..., "model": ..., "type": "boundary"|"semantic"|"indirect"}]
    repair_provider: str,
    repair_model: str,
    system_prompt_mode: str = "hardened",
):
    # ── Phase 1: Three parallel detectors ─────────────
    prompt_map = {
        "boundary": BOUNDARY_DETECTOR_PROMPT,
        "semantic": SEMANTIC_DETECTOR_PROMPT,
        "indirect": INDIRECT_DETECTOR_PROMPT,
    }

    detector_tasks = []
    for dc in detector_configs:
        det_type = dc.get("type", "boundary")
        prompt = prompt_map.get(det_type, BOUNDARY_DETECTOR_PROMPT)
        detector_tasks.append(
            _run_detector(
                provider=dc["provider"],
                model=dc["model"],
                prompt=prompt,
                user_input=case.user_input,
                external_content=case.external_content,
                label=det_type,
            )
        )

    detector_results = await asyncio.gather(*detector_tasks)

    # ── Phase 2: OR trigger ───────────────────────────
    any_suspicious = any(r["suspicious"] for r in detector_results)
    or_triggered = any_suspicious

    # ── Phase 3: Repair or pass-through ───────────────
    if or_triggered:
        repair_result = await _run_repair(
            provider=repair_provider,
            model=repair_model,
            task=case.task,
            user_input=case.user_input,
            external_content=case.external_content,
            detector_reports=detector_results,
        )

        repaired_parsed = repair_result.get("parsed") or {}
        action = repaired_parsed.get("action", "conservative_block")
        repaired_text = repaired_parsed.get("repaired_prompt", "")

        if action == "allow_original" or repaired_text == "NO_ATTACK":
            # Repair says it's fine → pass original
            system_prompt = build_target_system_prompt(
                task=case.task, canary=canary, mode=system_prompt_mode
            )
            user_prompt = build_target_user_prompt(
                user_input=case.user_input,
                external_content=case.external_content,
                mode=system_prompt_mode,
            )
        elif repaired_text and repaired_text != "NO_ATTACK":
            # Repair produced a cleaned version
            system_prompt = build_target_system_prompt(
                task=case.task, canary=canary, mode=system_prompt_mode
            )
            user_prompt = repaired_text
        else:
            # Conservative: let target see the original but with hardened prompt
            system_prompt = build_target_system_prompt(
                task=case.task, canary=canary, mode="hardened"
            )
            user_prompt = build_target_user_prompt(
                user_input=case.user_input,
                external_content=case.external_content,
                mode="hardened",
            )
    else:
        # ALL detectors passed → pass original
        system_prompt = build_target_system_prompt(
            task=case.task, canary=canary, mode=system_prompt_mode
        )
        user_prompt = build_target_user_prompt(
            user_input=case.user_input,
            external_content=case.external_content,
            mode=system_prompt_mode,
        )
        repair_result = {
            "parsed": None, "raw": None,
            "latency_ms": None, "input_tokens": None,
            "output_tokens": None, "actual_model": None,
        }

    # ── Phase 4: Call target model ────────────────────
    target_result = await chat_completion(
        provider=target_provider,
        model=target_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.0,
        max_tokens=256,
    )

    # ── Attach metadata ──────────────────────────────
    target_result["_system_prompt_hash"] = compute_system_prompt_hash(system_prompt)
    target_result["_system_prompt_text"] = system_prompt

    # Detector results
    for i, dr in enumerate(detector_results):
        target_result[f"_detector_{i}_label"] = dr["label"]
        target_result[f"_detector_{i}_suspicious"] = dr["suspicious"]
        target_result[f"_detector_{i}_latency_ms"] = dr["latency_ms"]
        target_result[f"_detector_{i}_input_tokens"] = dr["input_tokens"]
        target_result[f"_detector_{i}_output_tokens"] = dr["output_tokens"]
        target_result[f"_detector_{i}_model"] = dr["actual_model"]
        target_result[f"_detector_{i}_raw"] = dr["raw"]

    target_result["_or_triggered"] = or_triggered
    target_result["_repair_action"] = (repair_result.get("parsed") or {}).get("action")
    target_result["_repair_latency_ms"] = repair_result["latency_ms"]
    target_result["_repair_input_tokens"] = repair_result["input_tokens"]
    target_result["_repair_output_tokens"] = repair_result["output_tokens"]
    target_result["_repair_model"] = repair_result["actual_model"]
    target_result["_repair_raw"] = repair_result["raw"]

    return target_result