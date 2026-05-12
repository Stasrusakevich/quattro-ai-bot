from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from dotenv import load_dotenv
import os

from services.ai import generate_ai_response
from services.logger import logger


load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Quattro AI Assistant запущен."
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text

    ai_response = generate_ai_response(user_text)

    await update.message.reply_text(ai_response)


def main():
    if not TOKEN:
        raise ValueError("Не найден TELEGRAM_BOT_TOKEN")

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    logger.info("Bot started")
    print("Bot started...")

    app.run_polling()


if __name__ == "__main__":
    main()
