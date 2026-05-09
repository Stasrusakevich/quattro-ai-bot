import telebot
from openai import OpenAI

from config import TELEGRAM_TOKEN, GROQ_API_KEY, GROQ_BASE_URL
from handlers import register_handlers

bot = telebot.TeleBot(TELEGRAM_TOKEN)

client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url=GROQ_BASE_URL
)

register_handlers(bot, client)

bot.infinity_polling(skip_pending=True)
