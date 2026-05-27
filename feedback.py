from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from database.db import connect_db


MANAGER_NAME = 1
CLIENT_NAME = 2
EVENT_DATE = 3
EVENT_FORMAT = 4
GUESTS_COUNT = 5
CLIENT_REACTION = 6
OBJECTIONS = 7
NEXT_STEP = 8
COMMENT = 9


async def feedback_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["feedback"] = {}

    await update.message.reply_text(
        "Начинаем обратную связь после просмотра площадки.\n\n"
        "Вопрос 1/9:\n"
        "Имя менеджера?"
    )

    return MANAGER_NAME


async def feedback_manager_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["feedback"]["manager_name"] = update.message.text

    await update.message.reply_text(
        "Вопрос 2/9:\n"
        "Имя клиента?"
    )

    return CLIENT_NAME


async def feedback_client_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["feedback"]["client_name"] = update.message.text

    await update.message.reply_text(
        "Вопрос 3/9:\n"
        "Дата мероприятия?"
    )

    return EVENT_DATE


async def feedback_event_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["feedback"]["event_date"] = update.message.text

    await update.message.reply_text(
        "Вопрос 4/9:\n"
        "Формат мероприятия?"
    )

    return EVENT_FORMAT


async def feedback_event_format(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["feedback"]["event_format"] = update.message.text

    await update.message.reply_text(
        "Вопрос 5/9:\n"
        "Количество гостей?"
    )

    return GUESTS_COUNT


async def feedback_guests_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["feedback"]["guests_count"] = update.message.text

    await update.message.reply_text(
        "Вопрос 6/9:\n"
        "Какая была реакция клиента после просмотра?"
    )

    return CLIENT_REACTION


async def feedback_client_reaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["feedback"]["client_reaction"] = update.message.text

    await update.message.reply_text(
        "Вопрос 7/9:\n"
        "Какие были возражения или сомнения?"
    )

    return OBJECTIONS


async def feedback_objections(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["feedback"]["objections"] = update.message.text

    await update.message.reply_text(
        "Вопрос 8/9:\n"
        "Какой следующий шаг?"
    )

    return NEXT_STEP


async def feedback_next_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["feedback"]["next_step"] = update.message.text

    await update.message.reply_text(
        "Вопрос 9/9:\n"
        "Комментарий менеджера?"
    )

    return COMMENT


async def feedback_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    context.user_data["feedback"]["comment"] = update.message.text

    data = context.user_data["feedback"]

    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO feedback (
            user_id,
            manager_name,
            client_name,
            event_date,
            event_format,
            guests_count,
            client_reaction,
            objections,
            next_step,
            comment
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(user_id),
            data.get("manager_name"),
            data.get("client_name"),
            data.get("event_date"),
            data.get("event_format"),
            data.get("guests_count"),
            data.get("client_reaction"),
            data.get("objections"),
            data.get("next_step"),
            data.get("comment"),
        )
    )

    conn.commit()
    conn.close()

    context.user_data.pop("feedback", None)

    await update.message.reply_text("Обратная связь сохранена.")

    return ConversationHandler.END


async def feedback_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("feedback", None)

    await update.message.reply_text("Заполнение обратной связи отменено.")

    return ConversationHandler.END
