from pi_defense.clients import chat_completion
from pi_defense.prompts import (
    build_target_system_prompt,
    build_target_user_prompt,
)


async def run_b0(
    case,
    canary: str,
    target_provider: str,
    target_model: str,
    system_prompt_mode: str = "hardened",
):
    messages = [
        {
            "role": "system",
            "content": build_target_system_prompt(
                task=case.task,
                canary=canary,
                mode=system_prompt_mode,
            ),
        },
        {
            "role": "user",
            "content": build_target_user_prompt(
                user_input=case.user_input,
                external_content=case.external_content,
            ),
        },
    ]

    return await chat_completion(
        provider=target_provider,
        model=target_model,
        messages=messages,
        temperature=0.0,
        max_tokens=256,
    )
