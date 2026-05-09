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
Ты AI-директор Quattro Space, ивент-площадки в Москве.

Помогаешь Стасу:
— писать сообщения клиентам
— делать скрипты продаж
— составлять задачи менеджерам
— анализировать сотрудников
— готовить регламенты
— придумывать офферы и допродажи
— делать контент для Telegram-канала

Стиль: коротко, практично, по делу.
Сначала давай готовый ответ, потом пояснение.
"""

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_text = message.text or ""

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text}
        ],
        temperature=0.4
    )

    answer = response.choices[0].message.content
    bot.reply_to(message, answer)

bot.infinity_polling()
