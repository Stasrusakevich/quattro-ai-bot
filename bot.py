import os

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from services.ai import generate_ai_response
from services.logger import logger


load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я Quattro AI Assistant.\n\n"
        "Могу помогать с клиентами, заявками, текстами, задачами и внутренними процессами Quattro Space."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Доступные команды:\n\n"
        "/start — запустить бота\n"
        "/help — помощь\n\n"
        "Просто напиши сообщение, и я отвечу как AI Assistant Quattro Space."
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    user_id = update.effective_user.id

    logger.info(f"Message from user {user_id}: {user_text}")

    try:
        ai_response = generate_ai_response(user_text)
        await update.message.reply_text(ai_response)

    except Exception as error:
        logger.error(f"AI response error: {error}")
        await update.message.reply_text(
            "Произошла ошибка при обработке сообщения. "
            "Стас уже может проверить логи и исправить проблему."
        )


def main():
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("Не найден TELEGRAM_BOT_TOKEN")

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Quattro AI Assistant started")

    app.run_polling()


if __name__ == "__main__":
    main()
