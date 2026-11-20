import asyncio
from contextlib import suppress
import re

from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import Application, ApplicationHandlerStop, CommandHandler, ContextTypes, MessageHandler, filters

from config import load_settings
from database.db import Database, split_text
from services.ai import generate_ai_response
from services.delivery import deliver_notifications
from services.logger import logger
from services.runtime import instance_lock


MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [["Заметка", "Задача Стасу"], ["GPT"]], resize_keyboard=True
)
TASK_PREFIX = re.compile(r"^\s*(?:задач[ауи]\b|стасу\b|для\s+стаса\b)", re.IGNORECASE)
ATTACHMENTS = filters.PHOTO | filters.Document.ALL | filters.VOICE | filters.AUDIO | filters.VIDEO | filters.VIDEO_NOTE | filters.ANIMATION | filters.Sticker.ALL


def resources(context):
    return context.application.bot_data["settings"], context.application.bot_data["database"]


async def guard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if message is None or update.effective_user is None:
        raise ApplicationHandlerStop
    settings, _ = resources(context)
    if message.chat.type != "private":
        if not filters.COMMAND.check_update(update):
            raise ApplicationHandlerStop
        if message.chat_id not in settings.allowed_chat_ids:
            raise ApplicationHandlerStop
    if update.effective_user.id not in settings.allowed_user_ids:
        if message.chat.type == "private":
            await message.reply_text(f"Доступ выдаёт Стас. Передайте ему свой Telegram ID {update.effective_user.id}.")
        raise ApplicationHandlerStop


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("input_mode", None)
    await update.message.reply_text(
        "Напишите заметку — сохраню её и передам Стасу.\n"
        "Для задачи напишите «Задача Стасу …» или /task текст.\n"
        "Для вопроса к GPT нажмите «GPT» или напишите /gpt вопрос.\n"
        "В группах используйте /note_add, /task и /gpt.",
        reply_markup=MAIN_KEYBOARD if update.effective_chat.type == "private" else None,
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("input_mode", None)
    await update.message.reply_text("Готов принять заметку.", reply_markup=MAIN_KEYBOARD)


async def save_incoming(update, context, kind):
    settings, database = resources(context)
    try:
        item, _ = database.accept(update.message, kind, settings.owner_id)
    except Exception as error:
        logger.error("Could not save message: %s", type(error).__name__)
        await update.message.reply_text("Сохранение не удалось. Пожалуйста, повторите сообщение.")
        return
    await deliver_notifications(context.bot, database, item["id"])
    states = database.notification_states(item["id"])
    title = "Задача" if kind == "task" else "Заметка"
    result = f"{title} #{item['id']} сохранена."
    if states and all(state == "sent" for state in states):
        result += " Уведомление Стасу отправлено."
    else:
        result += " Доставка уведомления Стасу ожидает проверки."
    await update.message.reply_text(result)


async def note_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        await save_incoming(update, context, "note")
        return
    if update.effective_chat.type == "private":
        context.user_data["input_mode"] = "note"
    await update.message.reply_text("Напишите /note_add текст заметки или пришлите заметку в личный чат.")


async def task_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        await save_incoming(update, context, "task")
        return
    if update.effective_chat.type == "private":
        context.user_data["input_mode"] = "task"
    await update.message.reply_text("Напишите /task текст задачи или пришлите задачу в личный чат.")


async def gpt_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args)
    if not text:
        if update.effective_chat.type == "private":
            context.user_data["input_mode"] = "gpt"
        await update.message.reply_text("Пришлите вопрос к GPT. Для заметок нажмите «Заметка» или /cancel.")
        return
    await answer_gpt(update, context, text)


async def answer_gpt(update, context, text):
    settings, database = resources(context)
    try:
        item, _ = database.accept(update.message, "gpt", settings.owner_id)
    except Exception as error:
        logger.error("Could not save GPT request: %s", type(error).__name__)
        await update.message.reply_text("Сохранить запрос не удалось. Пожалуйста, повторите сообщение.")
        return
    if item["ai_state"] == "done":
        for part in split_text(item["ai_response"]):
            await update.message.reply_text(part)
        return
    if item["ai_state"] != "pending":
        await update.message.reply_text("Запрос уже принят. Для повторной попытки пришлите новый /gpt запрос.")
        return
    active_users = context.application.bot_data["gpt_active_users"]
    user_id = update.effective_user.id
    if user_id in active_users or len(active_users) >= 2:
        database.finish_ai(item["id"])
        await update.message.reply_text("Запрос сохранён. GPT занят — повторите вопрос новым сообщением чуть позже.")
        return
    if database.claim_ai(item["id"]):
        active_users.add(user_id)
        context.application.create_task(run_gpt(update, context, text, item["id"]), update=update)


async def run_gpt(update, context, text, item_id):
    settings, database = resources(context)
    user_id = update.effective_user.id
    try:
        try:
            history = []
            if update.effective_chat.type == "private":
                history = database.ai_history(user_id, item_id, chat_id=update.effective_chat.id)
            async with asyncio.timeout(50):
                response = await generate_ai_response(settings, text, history)
            database.finish_ai(item_id, response)
        except Exception as error:
            database.finish_ai(item_id)
            logger.warning("GPT request failed: %s", type(error).__name__)
            await update.message.reply_text("Запрос сохранён. GPT сейчас недоступен — сообщите Стасу. Заметки и задачи можно продолжать отправлять.")
            return
        for part in split_text(response):
            await update.message.reply_text(part)
    finally:
        context.application.bot_data["gpt_active_users"].discard(user_id)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    text = message.text or message.caption or ""
    if message.chat.type == "private" and text in {"Заметка", "Задача Стасу", "GPT"}:
        mode = {"Заметка": "note", "Задача Стасу": "task", "GPT": "gpt"}[text]
        context.user_data["input_mode"] = mode
        await message.reply_text({"note": "Пришлите заметку.", "task": "Пришлите задачу для Стаса.", "gpt": "Пришлите вопрос к GPT."}[mode])
        return
    mode = context.user_data.get("input_mode", "note")
    if TASK_PREFIX.match(text):
        await save_incoming(update, context, "task")
    elif mode == "gpt" and message.text:
        await answer_gpt(update, context, text)
    else:
        await save_incoming(update, context, "task" if mode == "task" else "note")


async def inbox(update: Update, context: ContextTypes.DEFAULT_TYPE):
    settings, database = resources(context)
    if update.effective_user.id != settings.owner_id or update.effective_chat.type != "private":
        await update.message.reply_text("Список входящих доступен Стасу в личном чате.")
        return
    command = update.message.text.split()[0].split("@")[0]
    kind = {"/notes": "note", "/tasks": "task"}.get(command)
    rows = database.inbox(kind)
    if not rows:
        await update.message.reply_text("Входящих пока нет.")
        return
    for row in reversed(rows):
        title = "Задача" if row["kind"] == "task" else "Заметка"
        states = ", ".join(database.notification_states(row["id"]))
        body = f"{title} #{row['id']} · {row['created_at']}\n{row['author']}\n{row['text']}\nДоставка: {states}"
        for part in split_text(body):
            await update.message.reply_text(part)


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    settings, database = resources(context)
    if update.effective_user.id != settings.owner_id or update.effective_chat.type != "private":
        return
    ai_status = "ключ задан, соединение проверяется при запросе" if settings.openai_key else "требуется OPENAI_API_KEY"
    await update.message.reply_text(f"Бот работает.\nGPT — {ai_status}.\nУведомления — {database.delivery_counts()}.")


async def retry_notifications(update: Update, context: ContextTypes.DEFAULT_TYPE):
    settings, database = resources(context)
    if update.effective_user.id != settings.owner_id or update.effective_chat.type != "private":
        return
    count = database.retry_failed()
    await deliver_notifications(context.bot, database)
    await update.message.reply_text(f"Повторно поставлено в очередь {count}.\nСостояние — {database.delivery_counts()}.")


async def delivery_worker(application):
    database = application.bot_data["database"]
    while True:
        try:
            await deliver_notifications(application.bot, database)
        except Exception as error:
            logger.error("Delivery worker failed: %s", type(error).__name__)
        await asyncio.sleep(15)


async def on_start(application):
    settings = application.bot_data["settings"]
    webhook = await application.bot.get_webhook_info()
    if webhook.url:
        raise RuntimeError("Настроен webhook. Согласуйте переключение на long polling перед запуском.")
    application.bot_data["database"].recover_interrupted()
    logger.info("Assistant started owner_id=%s", settings.owner_id)
    application.bot_data["delivery_worker"] = asyncio.create_task(delivery_worker(application))


async def on_stop(application):
    task = application.bot_data.get("delivery_worker")
    if task:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


async def on_error(update, context):
    logger.error("Update failed: %s", type(context.error).__name__)


def build_application(settings, database):
    application = (Application.builder().token(settings.token).concurrent_updates(False)
                   .post_init(on_start).post_stop(on_stop).build())
    application.bot_data.update(settings=settings, database=database, gpt_active_users=set())
    application.add_handler(MessageHandler(filters.ALL, guard), group=-1)
    application.add_handler(CommandHandler(["start", "help"], start))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(CommandHandler(["note", "note_add"], note_command))
    application.add_handler(CommandHandler("task", task_command))
    application.add_handler(CommandHandler(["gpt", "ask"], gpt_command))
    application.add_handler(CommandHandler(["inbox", "notes", "tasks"], inbox))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("retry_notifications", retry_notifications))
    application.add_handler(MessageHandler((filters.TEXT | ATTACHMENTS) & ~filters.COMMAND, handle_message))
    application.add_error_handler(on_error)
    return application


def main():
    settings = load_settings()
    with instance_lock(settings.data_dir / "assistant.lock"):
        database = Database(settings.data_dir / "assistant.sqlite3")
        application = build_application(settings, database)
        application.run_polling(allowed_updates=["message"], drop_pending_updates=False)


if __name__ == "__main__":
    main()
