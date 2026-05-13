import os
from dotenv import load_dotenv

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("START COMMAND RECEIVED")
    await update.message.reply_text("start работает")


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("PING COMMAND RECEIVED")
    await update.message.reply_text("pong")


def main():
    print("BOT FILE STARTED")

    if not TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN not found")

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ping", ping))

    print("HANDLERS REGISTERED")
    print("BOT POLLING STARTED")

    app.run_polling()


if __name__ == "__main__":
    main()
