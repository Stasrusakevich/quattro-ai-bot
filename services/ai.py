from groq import Groq

from config import GROQ_API_KEY
from services.memory import get_conversation
from services.prompts import load_prompt
from services.user_settings import get_user_mode
from services.knowledge import load_all_knowledge


client = Groq(api_key=GROQ_API_KEY)


def get_prompt_by_mode(mode):
    if mode == "sales":
        return load_prompt("sales_prompt.txt")

    if mode == "manager":
        return load_prompt("manager_prompt.txt")

    return load_prompt("system_prompt.txt")


def generate_ai_response(user_id, text):
    mode = get_user_mode(user_id)
    system_prompt = get_prompt_by_mode(mode)
    knowledge = load_all_knowledge()
    conversation = get_conversation(user_id)

    messages = [
        {
            "role": "system",
            "content": system_prompt
        },
        {
            "role": "system",
            "content": f"База знаний Quattro Space:\n\n{knowledge}"
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
