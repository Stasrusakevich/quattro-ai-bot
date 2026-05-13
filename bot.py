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

from database.db import init_db
from services.ai import generate_ai_response
from services.logger import logger
from services.memory import (
    save_message,
    get_conversation,
    clear_conversation,
)
from services.user_settings import (
    set_user_mode,
    get_user_mode,
)


load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("START COMMAND RECEIVED")

    await update.message.reply_text(
        "Quattro AI Assistant запущен.\n\n"
        "Режимы:\n"
        "/assistant — общий ассистент\n"
        "/sales — помощник продаж\n"
        "/manager — помощник менеджера\n\n"
        "Напиши сообщение — я отвечу с учетом выбранного режима."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("HELP COMMAND RECEIVED")

    await update.message.reply_text(
        "Команды:\n\n"
        "/start — запустить бота\n"
        "/help — помощь\n"
        "/ping — проверка связи\n"
        "/status — статус системы\n"
        "/memory — показать последние сообщения\n"
        "/clear — очистить память\n\n"
        "/assistant — общий режим\n"
        "/sales — режим продаж\n"
        "/manager — режим менеджера"
    )


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("PING COMMAND RECEIVED")
    await update.message.reply_text("pong")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    mode = get_user_mode(user_id)

    logger.info(f"STATUS COMMAND RECEIVED FROM USER {user_id}")

    await update.message.reply_text(
        "Quattro AI Status\n\n"
        "✅ Bot: online\n"
        "✅ Telegram: connected\n"
        "✅ AI: connected\n"
        "✅ Memory: active\n"
        "✅ SQLite: connected\n"
        f"✅ Current mode: {mode}"
    )


async def assistant_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    set_user_mode(user_id, "assistant")

    logger.info(f"USER {user_id} MODE SET TO assistant")

    await update.message.reply_text(
        "Включен общий режим Quattro AI Assistant."
    )


async def sales_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    set_user_mode(user_id, "sales")

    logger.info(f"USER {user_id} MODE SET TO sales")

    await update.message.reply_text(
        "Включен режим продаж. Буду помогать с клиентами, заявками и доведением до следующего шага."
    )


async def manager_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    set_user_mode(user_id, "manager")

    logger.info(f"USER {user_id} MODE SET TO manager")

    await update.message.reply_text(
        "Включен режим менеджера. Буду помогать с задачами, чек-листами и операционкой."
    )


async def memory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    logger.info(f"MEMORY COMMAND RECEIVED FROM USER {user_id}")

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

    logger.info(f"CLEAR COMMAND RECEIVED FROM USER {user_id}")

    clear_conversation(user_id)

    await update.message.reply_text("Память очищена.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    user_id = update.effective_user.id
    mode = get_user_mode(user_id)

    if not user_text:
        return

    logger.info(f"USER {user_id} MODE {mode}: {user_text}")

    try:
        save_message(user_id, "user", user_text)

        ai_response = generate_ai_response(
            user_id=user_id,
            text=user_text
        )

        save_message(user_id, "assistant", ai_response)

        logger.info(f"AI RESPONSE TO USER {user_id}: {ai_response}")

        await update.message.reply_text(ai_response)

    except Exception as error:
        logger.error(f"AI ERROR FOR USER {user_id}: {error}")

        await update.message.reply_text(
            "Ошибка AI Assistant. Проверь логи Railway."
        )


def main():
    if not TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN not found")

    init_db()

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("memory", memory))
    app.add_handler(CommandHandler("clear", clear))

    app.add_handler(CommandHandler("assistant", assistant_mode))
    app.add_handler(CommandHandler("sales", sales_mode))
    app.add_handler(CommandHandler("manager", manager_mode))

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        )
    )

    logger.info("QUATTRO AI BOT STARTED")

    app.run_polling()


if __name__ == "__main__":
    main()
