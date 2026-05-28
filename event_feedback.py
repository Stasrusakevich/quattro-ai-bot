from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from database.db import connect_db


EVENT_TYPE = 1
FACT_GUESTS = 2
BEFORE_PROBLEMS = 3
DURING_PROBLEMS = 4
CLIENT_RATING = 5
WHAT_WENT_WELL = 6
WHAT_TO_IMPROVE = 7
EVENT_COMMENT = 8


MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["ОС после встречи", "ОС после мероприятия"],
        ["Продажи", "Заметка"],
    ],
    resize_keyboard=True,
)

EVENT_FEEDBACK_KEYBOARD = ReplyKeyboardMarkup(
    [["Отмена"]],
    resize_keyboard=True,
)


async def event_feedback_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    context.user_data["event_feedback"] = {
        "executor_id": str(user.id),
        "executor_username": user.username or "",
        "executor_first_name": user.first_name or "",
    }

    await update.message.reply_text(
        "Начинаем ОС после мероприятия.\n\n"
        "Чтобы отменить заполнение, нажмите «Отмена» или напишите /cancel.\n\n"
        "Вопрос 1/8:\n"
        "Какое было мероприятие?",
        reply_markup=EVENT_FEEDBACK_KEYBOARD,
    )

    return EVENT_TYPE


async def event_feedback_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["event_feedback"]["event_type"] = update.message.text

    await update.message.reply_text(
        "Вопрос 2/8:\n"
        "Сколько гостей было фактически?",
        reply_markup=EVENT_FEEDBACK_KEYBOARD,
    )

    return FACT_GUESTS


async def event_feedback_fact_guests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["event_feedback"]["fact_guests"] = update.message.text

    await update.message.reply_text(
        "Вопрос 3/8:\n"
        "Были ли проблемы до начала мероприятия?",
        reply_markup=EVENT_FEEDBACK_KEYBOARD,
    )

    return BEFORE_PROBLEMS


async def event_feedback_before_problems(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["event_feedback"]["before_problems"] = update.message.text

    await update.message.reply_text(
        "Вопрос 4/8:\n"
        "Были ли проблемы во время мероприятия?",
        reply_markup=EVENT_FEEDBACK_KEYBOARD,
    )

    return DURING_PROBLEMS


async def event_feedback_during_problems(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["event_feedback"]["during_problems"] = update.message.text

    await update.message.reply_text(
        "Вопрос 5/8:\n"
        "Как клиент оценивал мероприятие?",
        reply_markup=EVENT_FEEDBACK_KEYBOARD,
    )

    return CLIENT_RATING


async def event_feedback_client_rating(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["event_feedback"]["client_rating"] = update.message.text

    await update.message.reply_text(
        "Вопрос 6/8:\n"
        "Что прошло особенно хорошо?",
        reply_markup=EVENT_FEEDBACK_KEYBOARD,
    )

    return WHAT_WENT_WELL


async def event_feedback_what_went_well(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["event_feedback"]["what_went_well"] = update.message.text

    await update.message.reply_text(
        "Вопрос 7/8:\n"
        "Что нужно улучшить в будущем?",
        reply_markup=EVENT_FEEDBACK_KEYBOARD,
    )

    return WHAT_TO_IMPROVE


async def event_feedback_what_to_improve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["event_feedback"]["what_to_improve"] = update.message.text

    await update.message.reply_text(
        "Вопрос 8/8:\n"
        "Дополнительный комментарий.",
        reply_markup=EVENT_FEEDBACK_KEYBOARD,
    )

    return EVENT_COMMENT


async def event_feedback_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["event_feedback"]["comment"] = update.message.text

    data = context.user_data["event_feedback"]

    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO event_feedback (
            executor_id,
            executor_username,
            executor_first_name,
            event_type,
            fact_guests,
            before_problems,
            during_problems,
            client_rating,
            what_went_well,
            what_to_improve,
            comment
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            data.get("executor_id"),
            data.get("executor_username"),
            data.get("executor_first_name"),
            data.get("event_type"),
            data.get("fact_guests"),
            data.get("before_problems"),
            data.get("during_problems"),
            data.get("client_rating"),
            data.get("what_went_well"),
            data.get("what_to_improve"),
            data.get("comment"),
        ),
    )

    conn.commit()
    conn.close()

    context.user_data.pop("event_feedback", None)

    await update.message.reply_text(
        "ОС после мероприятия сохранена.",
        reply_markup=MAIN_KEYBOARD,
    )

    return ConversationHandler.END


async def event_feedback_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("event_feedback", None)

    await update.message.reply_text(
        "Заполнение ОС после мероприятия отменено.",
        reply_markup=MAIN_KEYBOARD,
    )

    return ConversationHandler.END
