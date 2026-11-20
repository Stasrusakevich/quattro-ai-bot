from openai import AsyncOpenAI

from config import ROOT


class GPTUnavailable(Exception):
    pass


async def generate_ai_response(settings, text, history):
    if not settings.openai_key:
        raise GPTUnavailable("OPENAI_API_KEY is missing")
    instructions = (ROOT / "prompts/system_prompt.txt").read_text(encoding="utf-8")
    knowledge_path = ROOT / "knowledge/assistant.md"
    if knowledge_path.is_file():
        instructions += "\n\nСправка Quattro\n" + knowledge_path.read_text(encoding="utf-8")
    async with AsyncOpenAI(api_key=settings.openai_key, timeout=45, max_retries=0) as client:
        response = await client.responses.create(
            model=settings.openai_model,
            instructions=instructions,
            input=[*history, {"role": "user", "content": text}],
            max_output_tokens=2000,
            store=False,
        )
    if response.status != "completed" or not response.output_text.strip():
        raise GPTUnavailable("GPT returned an incomplete response")
    return response.output_text.strip()
