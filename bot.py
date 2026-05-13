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

from services.memory import (
    save_message,
    get_conversation,
    clear_conversation,
)

from database.db import init_db


load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Quattro AI Assistant запущен."
    )
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        """
Quattro AI Status

✅ Bot: online
✅ AI: connected
✅ Memory: active
✅ SQLite: connected
"""
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        """
Команды:

/start
/help
/ping
/memory
/clear
"""
    )


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("pong")


async def memory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    conversation = get_conversation(user_id)

    if not conversation:
        await update.message.reply_text("Память пустая.")
        return

    text = "\n\n".join(
        [
            f"{msg['role']}: {msg['content']}"
            for msg in conversation
        ]
    )

    await update.message.reply_text(text[:4000])


async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    clear_conversation(user_id)

    await update.message.reply_text(
        "Память очищена."
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    user_id = update.effective_user.id

    if not user_text:
        return

    logger.info(f"USER {user_id}: {user_text}")

    try:
        save_message(user_id, "user", user_text)

        ai_response = generate_ai_response(
            user_id=user_id,
            text=user_text
        )

        save_message(user_id, "assistant", ai_response)

        logger.info(f"AI {user_id}: {ai_response}")

        await update.message.reply_text(ai_response)

    except Exception as error:
        logger.error(f"ERROR: {error}")

        await update.message.reply_text(
            "Ошибка AI Assistant."
        )


def main():
    if not TOKEN:
        raise ValueError(
            "TELEGRAM_BOT_TOKEN not found"
        )

    init_db()

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("memory", memory))
    app.add_handler(CommandHandler("clear", clear))

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        )
    )

    logger.info("Quattro AI started")

    app.run_polling()


if __name__ == "__main__":
    main()
