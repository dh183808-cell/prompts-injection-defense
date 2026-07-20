import os
import time

from dotenv import load_dotenv
from openai import AsyncOpenAI
from tenacity import retry, wait_exponential, stop_after_attempt


load_dotenv()


def build_client(provider: str) -> AsyncOpenAI:
    if provider == "openrouter":
        return AsyncOpenAI(
            api_key=os.getenv("OPENROUTER_API_KEY"),
            base_url=os.getenv("OPENROUTER_BASE_URL"),
        )

    if provider == "siliconflow":
        return AsyncOpenAI(
            api_key=os.getenv("SILICONFLOW_API_KEY"),
            base_url=os.getenv("SILICONFLOW_BASE_URL"),
        )

    raise ValueError(f"Unsupported provider: {provider}")


@retry(
    wait=wait_exponential(min=1, max=20),
    stop=stop_after_attempt(3),
    reraise=True,
)
async def chat_completion(
    provider: str,
    model: str,
    messages: list[dict],
    temperature: float = 0.0,
    max_tokens: int = 512,
):
    client = build_client(provider)

    start = time.perf_counter()

    response = await client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    elapsed_ms = (time.perf_counter() - start) * 1000

    choice = response.choices[0]
    content = choice.message.content or ""

    usage = response.usage

    return {
        "content": content,
        "actual_model": response.model,
        "latency_ms": elapsed_ms,
        "input_tokens": usage.prompt_tokens if usage else None,
        "output_tokens": usage.completion_tokens if usage else None,
    }
