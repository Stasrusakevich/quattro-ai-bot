from telegram import Update, ReplyKeyboardMarkup
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
from services.manager_notes import add_note, get_last_notes

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


MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["ОС после встречи", "ОС после мероприятия"],
        ["Продажи", "Заметка"],
    ],
    resize_keyboard=True,
)


def is_admin(user_id):
    return str(user_id) == str(ADMIN_USER_ID)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Quattro AI Assistant запущен.\n\n"
        "Выберите действие в меню ниже.",
        reply_markup=MAIN_KEYBOARD,
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Доступные действия:\n\n"
        "ОС после встречи — заполнить обратную связь после просмотра\n"
        "ОС после мероприятия — скоро добавим\n"
        "Продажи — включить режим продаж\n"
        "Заметка — добавить наблюдение или вопрос в базу\n\n"
        "Команды:\n"
        "/feedback\n"
        "/sales\n"
        "/note_add текст заметки\n"
        "/notes",
        reply_markup=MAIN_KEYBOARD,
    )


async def modes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/assistant — общий помощник\n"
        "/sales — продажи\n"
        "/manager — менеджер\n"
        "/operations — операционка",
        reply_markup=MAIN_KEYBOARD,
    )


async def knowledge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    files = get_loaded_knowledge_files()

    if not files:
        await update.message.reply_text(
            "Файлы knowledge не найдены.",
            reply_markup=MAIN_KEYBOARD,
        )
        return

    text = "Загруженные knowledge-файлы:\n\n" + "\n".join(files)

    await update.message.reply_text(
        text[:4000],
        reply_markup=MAIN_KEYBOARD,
    )


async def brief(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Для брифа мероприятия напишите:\n\n"
        "- формат мероприятия\n"
        "- количество гостей\n"
        "- дата\n"
        "- бюджет\n"
        "- нужен ли кейтеринг\n"
        "- нужна ли техника\n"
        "- особые пожелания",
        reply_markup=MAIN_KEYBOARD,
    )


async def followup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Для follow-up напишите:\n\n"
        "- какой был контакт\n"
        "- что обсуждали\n"
        "- что обещали клиенту\n"
        "- следующий шаг",
        reply_markup=MAIN_KEYBOARD,
    )


async def checklist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Для checklist напишите:\n\n"
        "- формат мероприятия\n"
        "- количество гостей\n"
        "- дата\n"
        "- ключевые задачи",
        reply_markup=MAIN_KEYBOARD,
    )


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "pong",
        reply_markup=MAIN_KEYBOARD,
    )


async def whoami(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    await update.message.reply_text(
        f"Telegram user_id: {user.id}\n"
        f"Username: @{user.username}\n"
        f"First name: {user.first_name}",
        reply_markup=MAIN_KEYBOARD,
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_admin(user_id):
        await update.message.reply_text(
            "Нет доступа.",
            reply_markup=MAIN_KEYBOARD,
        )
        return

    await update.message.reply_text(
        "Quattro AI Status\n\n"
        "✅ Bot: online\n"
        "✅ AI: connected\n"
        "✅ Memory: active\n"
        "✅ SQLite: connected\n"
        f"✅ Current mode: {get_user_mode(user_id)}",
        reply_markup=MAIN_KEYBOARD,
    )


async def assistant_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_user_mode(update.effective_user.id, "assistant")

    await update.message.reply_text(
        "Включен общий режим.",
        reply_markup=MAIN_KEYBOARD,
    )


async def sales_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_user_mode(update.effective_user.id, "sales")

    await update.message.reply_text(
        "Включен режим продаж.\n\n"
        "Вставьте сообщение клиента, и я помогу подготовить ответ.",
        reply_markup=MAIN_KEYBOARD,
    )


async def manager_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_user_mode(update.effective_user.id, "manager")

    await update.message.reply_text(
        "Включен режим менеджера.",
        reply_markup=MAIN_KEYBOARD,
    )


async def operations_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_user_mode(update.effective_user.id, "operations")

    await update.message.reply_text(
        "Включен operations режим.",
        reply_markup=MAIN_KEYBOARD,
    )


async def memory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_admin(user_id):
        await update.message.reply_text(
            "Нет доступа.",
            reply_markup=MAIN_KEYBOARD,
        )
        return

    conversation = get_conversation(user_id)

    if not conversation:
        await update.message.reply_text(
            "Память пустая.",
            reply_markup=MAIN_KEYBOARD,
        )
        return

    text = "\n\n".join(
        [f"{message['role']}: {message['content']}" for message in conversation]
    )

    await update.message.reply_text(
        text[:4000],
        reply_markup=MAIN_KEYBOARD,
    )


async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_admin(user_id):
        await update.message.reply_text(
            "Нет доступа.",
            reply_markup=MAIN_KEYBOARD,
        )
        return

    clear_conversation(user_id)

    await update.message.reply_text(
        "Память очищена.",
        reply_markup=MAIN_KEYBOARD,
    )


async def feedback_export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_admin(user_id):
        await update.message.reply_text(
            "Нет доступа.",
            reply_markup=MAIN_KEYBOARD,
        )
        return

    file_path = export_feedback_to_xlsx()

    with open(file_path, "rb") as file:
        await update.message.reply_document(
            document=file,
            filename="feedback_export.xlsx"
        )


async def note_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    text = " ".join(context.args)

    if not text:
        await update.message.reply_text(
            "Напиши заметку после команды.\n\n"
            "Пример:\n"
            "/note_add Клиенты часто спрашивают про парковку",
            reply_markup=MAIN_KEYBOARD,
        )
        return

    add_note(user, text)

    await update.message.reply_text(
        "Заметка сохранена.",
        reply_markup=MAIN_KEYBOARD,
    )


async def notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_admin(user_id):
        await update.message.reply_text(
            "Нет доступа.",
            reply_markup=MAIN_KEYBOARD,
        )
        return

    rows = get_last_notes()

    if not rows:
        await update.message.reply_text(
            "Заметок пока нет.",
            reply_markup=MAIN_KEYBOARD,
        )
        return

    text = "Последние заметки менеджеров:\n\n"

    for created_at, first_name, username, note in rows:
        author = first_name or username or "unknown"
        text += f"• {created_at} — {author}\n{note}\n\n"

    await update.message.reply_text(
        text[:4000],
        reply_markup=MAIN_KEYBOARD,
    )


async def handle_menu_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "ОС после встречи":
        return await feedback_start(update, context)

    if text == "ОС после мероприятия":
        await update.message.reply_text(
            "ОС после мероприятия скоро добавим.",
            reply_markup=MAIN_KEYBOARD,
        )
        return

    if text == "Продажи":
        return await sales_mode(update, context)

    if text == "Заметка":
        await update.message.reply_text(
            "Напишите заметку командой:\n\n"
            "/note_add текст заметки\n\n"
            "Пример:\n"
            "/note_add Клиенты часто спрашивают про парковку",
            reply_markup=MAIN_KEYBOARD,
        )
        return

    await handle_message(update, context)


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

        await update.message.reply_text(
            ai_response,
            reply_markup=MAIN_KEYBOARD,
        )

    except Exception as error:
        logger.error(f"AI ERROR FOR USER {user_id}: {error}")

        await update.message.reply_text(
            "Ошибка AI Assistant. Проверь логи Railway.",
            reply_markup=MAIN_KEYBOARD,
        )


def main():
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN not found")

    init_db()

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    feedback_handler = ConversationHandler(
        entry_points=[
            CommandHandler("feedback", feedback_start),
            MessageHandler(filters.Regex("^ОС после встречи$"), feedback_start),
        ],
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

    app.add_handler(CommandHandler("note_add", note_add))
    app.add_handler(CommandHandler("notes", notes))

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
            handle_menu_buttons
        )
    )

    logger.info("QUATTRO AI BOT STARTED")

    app.run_polling()


if __name__ == "__main__":
    main()
