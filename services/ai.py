from groq import Groq

from config import GROQ_API_KEY

from services.memory import get_conversation
from services.prompts import load_prompt

client = Groq(api_key=GROQ_API_KEY)

SYSTEM_PROMPT = load_prompt("system_prompt.txt")


def generate_ai_response(user_id, text):
    conversation = get_conversation(user_id)

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT
        }
    ]

    messages.extend(conversation)

    messages.append(
        {
            "role": "user",
            "content": text
        }
    )

    chat_completion = client.chat.completions.create(
        messages=messages,
        model="llama-3.1-8b-instant"
    )

    return chat_completion.choices[0].message.content
