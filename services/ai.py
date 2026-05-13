from groq import Groq

from config import GROQ_API_KEY
from services.memory import get_conversation

client = Groq(api_key=GROQ_API_KEY)


SYSTEM_PROMPT = """
Ты — AI Assistant компании Quattro Space.

Помогай:
- с клиентами
- мероприятиями
- задачами
- продажами
- внутренними процессами

Отвечай кратко, понятно и профессионально.
"""


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
