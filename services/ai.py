"""One explicitly selected provider; no fallback or automatic retries."""

import asyncio

import httpx
from openai import AsyncOpenAI

from config import ROOT


TIMEOUT_SECONDS = 45
MAX_OUTPUT_TOKENS = 2000


class AIUnavailable(Exception):
    """Safe diagnostic: never includes an API key, prompt or API response body."""


# Keep the existing import contract for callers of the old GPT connector.
GPTUnavailable = AIUnavailable


def ai_status(settings):
    """Local configuration only; never sends a health check to a provider."""
    if not settings.ai_enabled:
        return "выключен (AI_ENABLED=false)"
    if not settings.ai_key_name:
        return "неизвестный AI_PROVIDER; подключение недоступно"
    if not settings.ai_key:
        return f"требуется {settings.ai_key_name}"
    if not settings.ai_model_id:
        return "требуется AI_MODEL"
    return f"{settings.ai_provider} / {settings.ai_model_id}: ключ задан, соединение проверяется при запросе"


def load_instructions():
    instructions = (ROOT / "prompts/system_prompt.txt").read_text(encoding="utf-8")
    knowledge_path = ROOT / "knowledge/assistant.md"
    if knowledge_path.is_file():
        instructions += "\n\nСправка Quattro\n" + knowledge_path.read_text(encoding="utf-8")
    return instructions


async def _openai(settings, instructions, messages):
    # Pin the official endpoint so OPENAI_BASE_URL cannot redirect this adapter.
    async with AsyncOpenAI(
        api_key=settings.ai_key, base_url="https://api.openai.com/v1",
        timeout=TIMEOUT_SECONDS, max_retries=0,
    ) as client:
        response = await client.responses.create(
            model=settings.ai_model_id,
            instructions=instructions,
            input=messages,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            store=False,
        )
    if response.status != "completed":
        raise AIUnavailable("OpenAI returned an incomplete response")
    return response.output_text


async def _deepseek(settings, instructions, messages):
    async with AsyncOpenAI(
        api_key=settings.ai_key, base_url="https://api.deepseek.com",
        timeout=TIMEOUT_SECONDS, max_retries=0,
    ) as client:
        response = await client.chat.completions.create(
            model=settings.ai_model_id,
            messages=[{"role": "system", "content": instructions}, *messages],
            max_tokens=MAX_OUTPUT_TOKENS,
            stream=False,
            # Keep the existing short text-answer budget and response time.
            extra_body={"thinking": {"type": "disabled"}},
        )
    if not response.choices or response.choices[0].finish_reason != "stop":
        raise AIUnavailable("DeepSeek returned an incomplete response")
    return response.choices[0].message.content


async def _anthropic(settings, instructions, messages):
    # HTTPX is already used by Telegram/OpenAI; declare it as a direct dependency.
    # Default transport has no retries; redirects are disabled explicitly.
    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS, follow_redirects=False) as client:
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": settings.ai_key,
                "anthropic-version": "2026-10-21",
            },
            json={
                "model": settings.ai_model_id,
                "system": instructions,
                "messages": messages,
                "max_tokens": MAX_OUTPUT_TOKENS,
                "stream": False,
            },
        )
        response.raise_for_status()
        result = response.json()
    if result.get("type") != "message" or result.get("stop_reason") not in {"end_turn", "stop_sequence"}:
        raise AIUnavailable("Anthropic returned an incomplete response")
    return "\n".join(block["text"] for block in result["content"] if block.get("type") == "text")


_ADAPTERS = {"deepseek": _deepseek, "openai": _openai, "anthropic": _anthropic}


async def generate_ai_response(settings, text, history):
    if not settings.ai_enabled:
        raise AIUnavailable("AI is disabled")
    adapter = _ADAPTERS.get(settings.ai_provider)
    if adapter is None:
        raise AIUnavailable("Unsupported AI_PROVIDER")
    if not settings.ai_key:
        raise AIUnavailable(f"{settings.ai_key_name} is missing")
    if not settings.ai_model_id:
        raise AIUnavailable("AI_MODEL is missing")
    instructions = load_instructions()
    messages = [*history, {"role": "user", "content": text}]
    try:
        # Bound the entire call, including connection, retries and response read.
        async with asyncio.timeout(TIMEOUT_SECONDS):
            answer = await adapter(settings, instructions, messages)
        if not isinstance(answer, str) or not answer.strip():
            raise AIUnavailable("AI returned an empty response")
        return answer.strip()
    except AIUnavailable:
        raise
    except (TimeoutError, httpx.TimeoutException):
        raise AIUnavailable("AI request timed out") from None
    except Exception:
        # Provider exceptions can contain credentials, corporate text and bodies.
        raise AIUnavailable("AI provider request failed") from None
