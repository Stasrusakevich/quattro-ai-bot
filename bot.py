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
    feedback_client_name,
    feedback_event_date,
    feedback_event_format,
    feedback_guests_count,
    feedback_client_reaction,
    feedback_objections,
    feedback_next_step,
    feedback_comment,
    feedback_cancel,
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
        "Quattro AI Assistant запущен.\n\n"
        "/modes — режимы\n"
        "/sales — режим продаж\n"
        "/feedback — обратная связь после просмотра\n"
        "/feedback_export — экспорт feedback"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Команды Quattro AI:\n\n"
        "/start\n"
        "/help\n"
        "/modes\n"
        "/ping\n"
        "/whoami\n"
        "/knowledge\n\n"
        "Режимы:\n"
        "/assistant\n"
        "/sales\n"
        "/manager\n"
        "/operations\n\n"
        "Инструменты:\n"
        "/brief\n"
        "/followup\n"
        "/checklist\n"
        "/feedback\n"
        "/cancel\n\n"
        "Admin:\n"
        "/status\n"
        "/memory\n"
        "/clear\n"
        "/feedback_export"
    )


async def modes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/assistant — общий помощник\n"
        "/sales — продажи\n"
        "/manager — менеджер\n"
        "/operations — операционка"
    )


async def knowledge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    files = get_loaded_knowledge_files()

    if not files:
        await update.message.reply_text("Файлы knowledge не найдены.")
        return

    text = "Загруженные knowledge-файлы:\n\n" + "\n".join(files)
    await update.message.reply_text(text[:4000])


async def brief(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Для брифа мероприятия напишите:\n\n"
        "- формат мероприятия\n"
        "- количество гостей\n"
        "- дата\n"
        "- бюджет\n"
        "- нужен ли кейтеринг\n"
        "- нужна ли техника\n"
        "- особые пожелания"
    )


async def followup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Для follow-up напишите:\n\n"
        "- какой был контакт\n"
        "- что обсуждали\n"
        "- что обещали клиенту\n"
        "- следующий шаг"
    )


async def checklist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Для checklist напишите:\n\n"
        "- формат мероприятия\n"
        "- количество гостей\n"
        "- дата\n"
        "- ключевые задачи\n\n"
        "Я подготовлю список проверки."
    )


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("pong")


async def whoami(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    await update.message.reply_text(
        f"Telegram user_id: {user.id}\n"
        f"Username: @{user.username}\n"
        f"First name: {user.first_name}"
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_admin(user_id):
        await update.message.reply_text("Нет доступа.")
        return

    await update.message.reply_text(
        "Quattro AI Status\n\n"
        "✅ Bot: online\n"
        "✅ AI: connected\n"
        "✅ Memory: active\n"
        "✅ SQLite: connected\n"
        f"✅ Current mode: {get_user_mode(user_id)}"
    )


async def assistant_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_user_mode(update.effective_user.id, "assistant")
    await update.message.reply_text("Включен общий режим.")


async def sales_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_user_mode(update.effective_user.id, "sales")
    await update.message.reply_text("Включен режим продаж.")


async def manager_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_user_mode(update.effective_user.id, "manager")
    await update.message.reply_text("Включен режим менеджера.")


async def operations_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_user_mode(update.effective_user.id, "operations")
    await update.message.reply_text("Включен operations режим.")


async def memory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_admin(user_id):
        await update.message.reply_text("Нет доступа.")
        return

    conversation = get_conversation(user_id)

    if not conversation:
        await update.message.reply_text("Память пустая.")
        return

    text = "\n\n".join(
        [f"{message['role']}: {message['content']}" for message in conversation]
    )

    await update.message.reply_text(text[:4000])


async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_admin(user_id):
        await update.message.reply_text("Нет доступа.")
        return

    clear_conversation(user_id)
    await update.message.reply_text("Память очищена.")


async def feedback_export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_admin(user_id):
        await update.message.reply_text("Нет доступа.")
        return

    file_path = export_feedback_to_xlsx()

    with open(file_path, "rb") as file:
        await update.message.reply_document(
            document=file,
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
            "Ошибка AI Assistant. Проверь логи Railway."
        )


def main():
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN not found")

    init_db()

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    feedback_handler = ConversationHandler(
        entry_points=[CommandHandler("feedback", feedback_start)],
        states={
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

    app.add_handler(feedback_handler)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("modes", modes))
    app.add_handler(CommandHandler("knowledge", knowledge))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("whoami", whoami))

    app.add_handler(CommandHandler("brief", brief))
    app.add_handler(CommandHandler("followup", followup))
    app.add_handler(CommandHandler("checklist", checklist))
    app.add_handler(CommandHandler("feedback_export", feedback_export))

    app.add_handler(CommandHandler("assistant", assistant_mode))
    app.add_handler(CommandHandler("sales", sales_mode))
    app.add_handler(CommandHandler("manager", manager_mode))
    app.add_handler(CommandHandler("operations", operations_mode))

    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("memory", memory))
    app.add_handler(CommandHandler("clear", clear))

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
