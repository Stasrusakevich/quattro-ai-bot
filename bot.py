import os
import telebot
from openai import OpenAI

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

bot = telebot.TeleBot(TELEGRAM_TOKEN)

client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

SYSTEM_PROMPT = """
Ты AI-директор Quattro Space.

Работаешь как помощник Стаса по управлению ивент-площадкой.
Отвечай кратко, практично и по делу.
Сначала давай готовое решение, потом пояснение.
"""

# Краткосрочная память диалогов
user_histories = {}

MAX_HISTORY_MESSAGES = 10


def load_knowledge():
    try:
        with open("knowledge.txt", "r", encoding="utf-8") as file:
            return file.read()
    except FileNotFoundError:
        return ""


def get_user_history(user_id):
    if user_id not in user_histories:
        user_histories[user_id] = []
    return user_histories[user_id]


@bot.message_handler(commands=["reset"])
def reset_history(message):
    user_id = message.from_user.id
    user_histories[user_id] = []
    bot.reply_to(message, "Память текущего диалога очищена.")


@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_id = message.from_user.id
    user_text = message.text or ""

    knowledge = load_knowledge()
    history = get_user_history(user_id)

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT + "\n\nПамять ассистента:\n" + knowledge
        }
    ]

    messages.extend(history)

    messages.append({
        "role": "user",
        "content": user_text
    })

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=messages,
        temperature=0.4
    )

    answer = response.choices[0].message.content

    history.append({
        "role": "user",
        "content": user_text
    })

    history.append({
        "role": "assistant",
        "content": answer
    })

    user_histories[user_id] = history[-MAX_HISTORY_MESSAGES:]

    bot.reply_to(message, answer)


bot.infinity_polling()
