from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from database.db import connect_db


CLIENT_NAME = 1
EVENT_DATE = 2
EVENT_FORMAT = 3
GUESTS_COUNT = 4
CLIENT_REACTION = 5
OBJECTIONS = 6
NEXT_STEP = 7
COMMENT = 8


MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["ОС после встречи", "ОС после мероприятия"],
        ["Продажи", "Заметка"],
    ],
    resize_keyboard=True,
)

FEEDBACK_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["Отмена"],
    ],
    resize_keyboard=True,
)


async def feedback_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    context.user_data["feedback"] = {
        "manager_id": str(user.id),
        "manager_username": user.username or "",
        "manager_first_name": user.first_name or "",
    }

    await update.message.reply_text(
        "Начинаем обратную связь после просмотра площадки.\n\n"
        "Чтобы отменить заполнение, нажмите кнопку «Отмена».\n\n"
        "Вопрос 1/8:\n"
        "Имя клиента?",
        reply_markup=FEEDBACK_KEYBOARD,
    )

    return CLIENT_NAME


async def feedback_client_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["feedback"]["client_name"] = update.message.text

    await update.message.reply_text(
        "Вопрос 2/8:\n"
        "Дата мероприятия?",
        reply_markup=FEEDBACK_KEYBOARD,
    )

    return EVENT_DATE


async def feedback_event_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["feedback"]["event_date"] = update.message.text

    await update.message.reply_text(
        "Вопрос 3/8:\n"
        "Формат мероприятия?",
        reply_markup=FEEDBACK_KEYBOARD,
    )

    return EVENT_FORMAT


async def feedback_event_format(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["feedback"]["event_format"] = update.message.text

    await update.message.reply_text(
        "Вопрос 4/8:\n"
        "Количество гостей?",
        reply_markup=FEEDBACK_KEYBOARD,
    )

    return GUESTS_COUNT


async def feedback_guests_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["feedback"]["guests_count"] = update.message.text

    await update.message.reply_text(
        "Вопрос 5/8:\n"
        "Какая была реакция клиента после просмотра?",
        reply_markup=FEEDBACK_KEYBOARD,
    )

    return CLIENT_REACTION


async def feedback_client_reaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["feedback"]["client_reaction"] = update.message.text

    await update.message.reply_text(
        "Вопрос 6/8:\n"
        "Какие были возражения или сомнения?",
        reply_markup=FEEDBACK_KEYBOARD,
    )

    return OBJECTIONS


async def feedback_objections(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["feedback"]["objections"] = update.message.text

    await update.message.reply_text(
        "Вопрос 7/8:\n"
        "Какой следующий шаг?",
        reply_markup=FEEDBACK_KEYBOARD,
    )

    return NEXT_STEP


async def feedback_next_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["feedback"]["next_step"] = update.message.text

    await update.message.reply_text(
        "Вопрос 8/8:\n"
        "Комментарий менеджера?",
        reply_markup=FEEDBACK_KEYBOARD,
    )

    return COMMENT


async def feedback_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["feedback"]["comment"] = update.message.text

    data = context.user_data["feedback"]

    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO feedback (
            manager_id,
            manager_username,
            manager_first_name,
            client_name,
            event_date,
            event_format,
            guests_count,
            client_reaction,
            objections,
            next_step,
            comment
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            data.get("manager_id"),
            data.get("manager_username"),
            data.get("manager_first_name"),
            data.get("client_name"),
            data.get("event_date"),
            data.get("event_format"),
            data.get("guests_count"),
            data.get("client_reaction"),
            data.get("objections"),
            data.get("next_step"),
            data.get("comment"),
        ),
    )

    conn.commit()
    conn.close()

    context.user_data.pop("feedback", None)

    await update.message.reply_text(
        "Обратная связь сохранена.",
        reply_markup=MAIN_KEYBOARD,
    )

    return ConversationHandler.END


async def feedback_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("feedback", None)

    await update.message.reply_text(
        "Заполнение обратной связи отменено.",
        reply_markup=MAIN_KEYBOARD,
    )

    return ConversationHandler.END
