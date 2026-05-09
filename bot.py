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


def load_knowledge():
    try:
        with open("knowledge.txt", "r", encoding="utf-8") as file:
            return file.read()
    except FileNotFoundError:
        return ""


@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_text = message.text or ""
    knowledge = load_knowledge()

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT + "\n\nПамять ассистента:\n" + knowledge
            },
            {
                "role": "user",
                "content": user_text
            }
        ],
        temperature=0.4
    )

    answer = response.choices[0].message.content
    bot.reply_to(message, answer)


bot.infinity_polling()
