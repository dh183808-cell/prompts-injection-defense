import os
import asyncio
import httpx
from dotenv import load_dotenv

load_dotenv()


async def fetch_models(name: str, base_url: str, api_key: str):
    url = f"{base_url.rstrip('/')}/models"

    headers = {
        "Authorization": f"Bearer {api_key}",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    models = data.get("data", [])

    print(f"\n===== {name} =====")

    keywords = [
        "qwen",
        "gemma",
        "mistral",
        "ministral",
        "glm",
        "deepseek",
        "kimi",
        "moonshot",
        "phi",
    ]

    for item in models:
        model_id = item.get("id", "")
        if any(k in model_id.lower() for k in keywords):
            print(model_id)


async def main():
    await fetch_models(
        "OpenRouter",
        os.getenv("OPENROUTER_BASE_URL"),
        os.getenv("OPENROUTER_API_KEY"),
    )

    await fetch_models(
        "SiliconFlow",
        os.getenv("SILICONFLOW_BASE_URL"),
        os.getenv("SILICONFLOW_API_KEY"),
    )


if __name__ == "__main__":
    asyncio.run(main())
