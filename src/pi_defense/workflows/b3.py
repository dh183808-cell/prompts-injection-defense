"""
B3 workflow: three parallel detectors + adjudicator (Nex-N2-Pro) + repair + target.

Architecture:
  B2: detectors → OR → repair → target
  B3: detectors → adjudicate → repair → target
"""
import asyncio
import json
import re
from typing import Any

from pi_defense.clients import chat_completion
from pi_defense.prompts import (
    ADJUDICATION_PROMPT,
    BOUNDARY_DETECTOR_PROMPT,
    SEMANTIC_DETECTOR_PROMPT,
    INDIRECT_DETECTOR_PROMPT,
    REPAIR_PROMPT,
    build_target_system_prompt,
    build_target_user_prompt,
    compute_system_prompt_hash,
)


def extract_json(text: str) -> dict[str, Any] | None:
    text = text.strip()
    if text.startswith("{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if m:
        inner = m.group(1).strip()
        if inner.startswith("{"):
            try:
                return json.loads(inner)
            except json.JSONDecodeError:
                pass
    m = re.search(r"\{[^{}]*", text, re.DOTALL)
    if m:
        start = m.start()
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i+1])
                except json.JSONDecodeError:
                    break
    return None


async def run_detector(
    provider: str, model: str, prompt: str,
    user_input: str, external_content: str, label: str,
) -> dict:
    content = f"User input:\n{user_input}"
    if external_content:
        content += f"\n\nExternal content:\n{external_content}"
    result = await chat_completion(
        provider=provider, model=model,
        messages=[{"role": "system", "content": prompt}, {"role": "user", "content": content}],
        temperature=0.0, max_tokens=512,
    )
    parsed = extract_json(result["content"])
    return {
        "label": label,
        "suspicious": bool((parsed or {}).get("suspicious", False) or (parsed or {}).get("is_attack", False)),
        "parsed": parsed,
        "raw": result["content"],
        "latency_ms": result.get("latency_ms"),
        "input_tokens": result.get("input_tokens"),
        "output_tokens": result.get("output_tokens"),
        "actual_model": result.get("actual_model"),
    }


async def run_adjudicator(
    provider: str, model: str,
    task: str, user_input: str, external_content: str,
    detector_reports: list[dict],
) -> dict:
    reports_text = json.dumps([
        {"detector": r["label"], "suspicious": r["suspicious"], "parsed": r.get("parsed")}
        for r in detector_reports
    ], indent=2, ensure_ascii=False)
    content = (
        f"Trusted task:\n{task}\n\n"
        f"User input:\n{user_input}\n\n"
        f"External content:\n{external_content or '(none)'}\n\n"
        f"Detection reports:\n{reports_text}"
    )
    result = await chat_completion(
        provider=provider, model=model,
        messages=[{"role": "system", "content": ADJUDICATION_PROMPT}, {"role": "user", "content": content}],
        temperature=0.0, max_tokens=1024,
    )
    parsed = extract_json(result["content"])
    return {
        "parsed": parsed,
        "raw": result["content"],
        "latency_ms": result.get("latency_ms"),
        "input_tokens": result.get("input_tokens"),
        "output_tokens": result.get("output_tokens"),
        "actual_model": result.get("actual_model"),
    }


async def run_b3(
    case, canary: str,
    target_provider: str, target_model: str,
    detector_configs: list[dict],
    adjudicator_provider: str, adjudicator_model: str,
    repair_provider: str, repair_model: str,
    system_prompt_mode: str = "minimal",
) -> dict:
    prompt_map = {
        "boundary": BOUNDARY_DETECTOR_PROMPT,
        "semantic": SEMANTIC_DETECTOR_PROMPT,
        "indirect": INDIRECT_DETECTOR_PROMPT,
    }

    # Phase 1: parallel detectors
    detector_tasks = []
    for dc in detector_configs:
        det_type = dc.get("type", "boundary")
        detector_tasks.append(run_detector(
            provider=dc["provider"], model=dc["model"],
            prompt=prompt_map.get(det_type, BOUNDARY_DETECTOR_PROMPT),
            user_input=case.user_input, external_content=case.external_content,
            label=det_type,
        ))
    detector_results = await asyncio.gather(*detector_tasks)
    any_suspicious = any(r["suspicious"] for r in detector_results)

    # Phase 2: adjudicate
    adjudicator_result = None
    if any_suspicious:
        adjudicator_result = await run_adjudicator(
            provider=adjudicator_provider, model=adjudicator_model,
            task=case.task, user_input=case.user_input,
            external_content=case.external_content,
            detector_reports=detector_results,
        )

    # Phase 3: determine action & optionally repair
    confirmed_attack = False
    adjudicator_action = None
    if adjudicator_result and adjudicator_result.get("parsed"):
        adj_parsed = adjudicator_result["parsed"]
        confirmed_attack = adj_parsed.get("confirmed_attack", False)
        adjudicator_action = adj_parsed.get("action", "allow_original")

    repair_result = None
    if confirmed_attack and adjudicator_action == "repair":
        reports_text = json.dumps([
            {"detector": r["label"], "suspicious": r["suspicious"], "parsed": r.get("parsed")}
            for r in detector_results
        ], indent=2, ensure_ascii=False)
        repair_content = (
            f"Trusted task:\n{case.task}\n\n"
            f"User input:\n{case.user_input}\n\n"
            f"External content:\n{case.external_content or '(none)'}\n\n"
            f"Detection reports:\n{reports_text}"
        )
        repair_api_result = await chat_completion(
            provider=repair_provider, model=repair_model,
            messages=[{"role": "system", "content": REPAIR_PROMPT}, {"role": "user", "content": repair_content}],
            temperature=0.0, max_tokens=1024,
        )
        repair_parsed = extract_json(repair_api_result["content"])
        repair_result = {
            "parsed": repair_parsed, "raw": repair_api_result["content"],
            "latency_ms": repair_api_result.get("latency_ms"),
            "input_tokens": repair_api_result.get("input_tokens"),
            "output_tokens": repair_api_result.get("output_tokens"),
            "actual_model": repair_api_result.get("actual_model"),
        }

    # Phase 4: call target
    use_repaired = False
    if repair_result and repair_result.get("parsed"):
        repaired_text = (repair_result["parsed"] or {}).get("repaired_prompt", "")
        use_repaired = bool(repaired_text and repaired_text != "NO_ATTACK" and repaired_text != "NO_ATTACK")

    mode_to_use = system_prompt_mode
    if confirmed_attack and adjudicator_action == "conservative_block":
        mode_to_use = "hardened"

    system_prompt = build_target_system_prompt(task=case.task, canary=canary, mode=mode_to_use)
    if use_repaired:
        user_prompt = repaired_text
    else:
        user_prompt = build_target_user_prompt(
            user_input=case.user_input, external_content=case.external_content, mode=mode_to_use,
        )

    target_result = await chat_completion(
        provider=target_provider, model=target_model,
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        temperature=0.0, max_tokens=256,
    )
    target_result["_system_prompt_hash"] = compute_system_prompt_hash(system_prompt)

    # Attach all metadata
    for i, dr in enumerate(detector_results):
        target_result[f"_detector_{i}_suspicious"] = dr["suspicious"]
        target_result[f"_detector_{i}_latency_ms"] = dr["latency_ms"]
        target_result[f"_detector_{i}_input_tokens"] = dr["input_tokens"]
        target_result[f"_detector_{i}_output_tokens"] = dr["output_tokens"]
        target_result[f"_detector_{i}_model"] = dr["actual_model"]
        target_result[f"_detector_{i}_label"] = dr["label"]
    target_result["_or_triggered"] = any_suspicious
    target_result["_adjudicator_confirmed"] = confirmed_attack
    target_result["_adjudicator_action"] = adjudicator_action
    target_result["_adjudicator_latency_ms"] = (adjudicator_result or {}).get("latency_ms")
    target_result["_adjudicator_input_tokens"] = (adjudicator_result or {}).get("input_tokens")
    target_result["_adjudicator_output_tokens"] = (adjudicator_result or {}).get("output_tokens")
    target_result["_adjudicator_model"] = (adjudicator_result or {}).get("actual_model")
    target_result["_adjudicator_raw"] = (adjudicator_result or {}).get("raw")
    if repair_result:
        target_result["_repair_latency_ms"] = repair_result.get("latency_ms")
        target_result["_repair_input_tokens"] = repair_result.get("input_tokens")
        target_result["_repair_output_tokens"] = repair_result.get("output_tokens")
        target_result["_repair_model"] = repair_result.get("actual_model")
        target_result["_repair_action"] = (repair_result.get("parsed") or {}).get("action", "")
        target_result["_repair_raw"] = repair_result.get("raw")
    return target_result