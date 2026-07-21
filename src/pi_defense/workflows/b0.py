import hashlib

from pi_defense.clients import chat_completion
from pi_defense.prompts import (
    build_target_system_prompt,
    build_target_user_prompt,
    compute_system_prompt_hash,
)


async def run_b0(
    case,
    canary: str,
    target_provider: str,
    target_model: str,
    system_prompt_mode: str = "hardened",
):
    system_prompt = build_target_system_prompt(
        task=case.task,
        canary=canary,
        mode=system_prompt_mode,
    )
    user_prompt = build_target_user_prompt(
        user_input=case.user_input,
        external_content=case.external_content,
        mode=system_prompt_mode,
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    result = await chat_completion(
        provider=target_provider,
        model=target_model,
        messages=messages,
        temperature=0.0,
        max_tokens=256,
    )

    # Attach metadata for the runner
    result["_system_prompt_hash"] = compute_system_prompt_hash(system_prompt)
    result["_system_prompt_text"] = system_prompt
    return result
