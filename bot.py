from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    ConversationHandler,
)

from config import TELEGRAM_BOT_TOKEN, ADMIN_USER_ID
from database.db import init_db
from services.ai import generate_ai_response
from services.logger import logger
from services.memory import save_message, get_conversation, clear_conversation
from services.user_settings import set_user_mode, get_user_mode
from services.knowledge import get_loaded_knowledge_files

from feedback import (
    feedback_start,
    feedback_manager_name,
    feedback_client_name,
    feedback_event_date,
    feedback_event_format,
    feedback_guests_count,
    feedback_client_reaction,
    feedback_objections,
    feedback_next_step,
    feedback_comment,
    feedback_cancel,
    MANAGER_NAME,
    CLIENT_NAME,
    EVENT_DATE,
    EVENT_FORMAT,
    GUESTS_COUNT,
    CLIENT_REACTION,
    OBJECTIONS,
    NEXT_STEP,
    COMMENT,
)

from exports import export_feedback_to_xlsx


def is_admin(user_id):
    return str(user_id) == str(ADMIN_USER_ID)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Quattro AI Assistant запущен."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/feedback — заполнить feedback\n"
        "/feedback_export — экспорт feedback\n"
        "/sales\n"
        "/manager\n"
        "/operations"
    )


async def feedback_export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_admin(user_id):
        await update.message.reply_text("Нет доступа.")
        return

    file_path = export_feedback_to_xlsx()

    await update.message.reply_document(
        document=open(file_path, "rb"),
        filename="feedback_export.xlsx"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_text = update.message.text

    if not user_text:
        return

    try:
        save_message(user_id, "user", user_text)

        ai_response = generate_ai_response(
            user_id=user_id,
            text=user_text
        )

        save_message(user_id, "assistant", ai_response)

        await update.message.reply_text(ai_response)

    except Exception as error:
        logger.error(f"AI ERROR FOR USER {user_id}: {error}")

        await update.message.reply_text(
            "Ошибка AI Assistant."
        )


def main():
    init_db()

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    feedback_handler = ConversationHandler(
        entry_points=[CommandHandler("feedback", feedback_start)],
        states={
            MANAGER_NAME: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    feedback_manager_name
                )
            ],
            CLIENT_NAME: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    feedback_client_name
                )
            ],
            EVENT_DATE: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    feedback_event_date
                )
            ],
            EVENT_FORMAT: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    feedback_event_format
                )
            ],
            GUESTS_COUNT: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    feedback_guests_count
                )
            ],
            CLIENT_REACTION: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    feedback_client_reaction
                )
            ],
            OBJECTIONS: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    feedback_objections
                )
            ],
            NEXT_STEP: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    feedback_next_step
                )
            ],
            COMMENT: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    feedback_comment
                )
            ],
        },
        fallbacks=[CommandHandler("cancel", feedback_cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("feedback_export", feedback_export))

    app.add_handler(feedback_handler)

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
