import os
import tempfile
import telebot
from telebot import types
from openai import OpenAI

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not TELEGRAM_TOKEN:
    raise ValueError("Не найден TELEGRAM_TOKEN")

if not GROQ_API_KEY:
    raise ValueError("Не найден GROQ_API_KEY")

bot = telebot.TeleBot(TELEGRAM_TOKEN)

client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

TEXT_MODEL = "llama-3.1-8b-instant"
VOICE_MODEL = "whisper-large-v3"

MAX_HISTORY_MESSAGES = 12

# После команды /myid вставь сюда свой Telegram ID
ADMIN_IDS = []

user_histories = {}
user_modes = {}

BASE_SYSTEM_PROMPT = """
Ты AI-директор Quattro Space.

Работаешь как личный помощник Стаса по управлению ивент-площадкой.
Отвечай кратко, практично и по делу.
Сначала давай готовый результат, потом пояснение.
Не используй лишнюю теорию.
"""

MODES = {
    "default": """
Режим: универсальный помощник.
Помогай с любыми рабочими задачами Стаса.
""",

    "sales": """
Режим: директор по продажам.
Фокус: клиенты, дожимы, КП, скрипты, встречи, сделки, возражения, повторные касания.
Пиши уверенно, но без давления.
""",

    "ops": """
Режим: операционный управляющий.
Фокус: задачи, регламенты, контроль сотрудников, процессы, стандарты, чек-листы, ответственность.
Пиши конкретно и управленчески.
""",

    "hr": """
Режим: HR и руководитель команды.
Фокус: сотрудники, мотивация, конфликты, KPI, обратная связь, дисциплина, найм.
Помогай формулировать спокойно, твердо и конструктивно.
""",

    "content": """
Режим: редактор Telegram-канала про event-индустрию.
Фокус: посты, идеи, заголовки, сторителлинг, закулисье мероприятий, экспертный тон.
Пиши живо, без пафоса и рекламной воды.
""",

    "finance": """
Режим: финансовый помощник.
Фокус: расходы, доходы, долги, планирование платежей, юнит-экономика, загрузка площадки.
Пиши аккуратно и понятно.
""",

    "producer": """
Режим: реализатор мероприятия / event producer.

Фокус:
— подготовка мероприятия
— чек-листы реализации
— пожелания клиента
— тайминг
— зоны ответственности
— подрядчики
— техника
— банкет / фуршет / welcome
— монтаж и демонтаж
— контроль перед стартом

Всегда структурируй ответ:
1. Краткое резюме мероприятия
2. Чек-лист подготовки
3. Что уточнить у клиента
4. Риски
5. Контроль в день мероприятия
6. Следующий шаг

Пиши как опытный реализатор:
— конкретно
— спокойно
— без воды
— без лишней теории
— с пониманием event-индустрии
"""
}


def load_knowledge():
    try:
        with open("knowledge.txt", "r", encoding="utf-8") as file:
            return file.read()
    except FileNotFoundError:
        return ""


def save_memory(text):
    with open("knowledge.txt", "a", encoding="utf-8") as file:
        file.write("\n\nДОПОЛНИТЕЛЬНАЯ ПАМЯТЬ:\n")
        file.write(text.strip())


def is_admin(user_id):
    # Если ADMIN_IDS пустой — команда /remember временно доступна всем.
    # После проверки /myid лучше вставить свой ID в ADMIN_IDS.
    if not ADMIN_IDS:
        return True
    return user_id in ADMIN_IDS


def get_user_history(user_id):
    if user_id not in user_histories:
        user_histories[user_id] = []
    return user_histories[user_id]


def get_user_mode(user_id):
    return user_modes.get(user_id, "default")


def set_user_mode(user_id, mode):
    user_modes[user_id] = mode


def build_system_prompt(user_id):
    knowledge = load_knowledge()
    mode = get_user_mode(user_id)
    mode_prompt = MODES.get(mode, MODES["default"])

    return f"""
{BASE_SYSTEM_PROMPT}

{mode_prompt}

Память ассистента:
{knowledge}
"""


def split_long_message(text, limit=3900):
    if len(text) <= limit:
        return [text]

    parts = []

    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)

        if cut == -1:
            cut = limit

        parts.append(text[:cut])
        text = text[cut:].strip()

    if text:
        parts.append(text)

    return parts


def send_long_reply(chat_id, text, reply_to_message_id=None):
    parts = split_long_message(text)

    for index, part in enumerate(parts):
        if index == 0 and reply_to_message_id:
            bot.send_message(
                chat_id,
                part,
                reply_to_message_id=reply_to_message_id
            )
        else:
            bot.send_message(chat_id, part)


def ask_ai(user_id, user_text):
    history = get_user_history(user_id)

    messages = [
        {
            "role": "system",
            "content": build_system_prompt(user_id)
        }
    ]

    messages.extend(history)

    messages.append({
        "role": "user",
        "content": user_text
    })

    response = client.chat.completions.create(
        model=TEXT_MODEL,
        messages=messages,
        temperature=0.4
    )

    answer = response.choices[0].message.content

    history.append({
        "role": "user",
        "content": user_text
    })

    history.append({
        "role": "assistant",
        "content": answer
    })

    user_histories[user_id] = history[-MAX_HISTORY_MESSAGES:]

    return answer


@bot.message_handler(commands=["start", "help"])
def help_command(message):
    text = """
Я AI-ассистент Quattro Space.

Команды:
/sales — режим продаж
/ops — операционный режим
/hr — сотрудники и управление
/content — контент для канала
/finance — финансы
/producer — режим реализатора мероприятия
/eventcheck — чек-лист перед мероприятием
/default — обычный режим
/mode — показать текущий режим
/reset — очистить память текущего диалога
/remember — добавить информацию в память
/myid — показать твой Telegram ID

Можно писать текстом или отправлять голосовые.
"""
    bot.reply_to(message, text)


@bot.message_handler(commands=["myid"])
def myid_command(message):
    bot.reply_to(message, f"Твой Telegram ID: {message.from_user.id}")


@bot.message_handler(commands=["mode"])
def mode_command(message):
    mode = get_user_mode(message.from_user.id)
    bot.reply_to(message, f"Текущий режим: {mode}")


@bot.message_handler(commands=["reset"])
def reset_command(message):
    user_histories[message.from_user.id] = []
    bot.reply_to(message, "Память текущего диалога очищена.")


@bot.message_handler(commands=["remember"])
def remember_command(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "У тебя нет доступа к изменению памяти.")
        return

    text = message.text.replace("/remember", "").strip()

    if not text:
        bot.reply_to(message, "Напиши так: /remember важная информация для памяти")
        return

    save_memory(text)
    bot.reply_to(message, "Сохранил в память.")


@bot.message_handler(commands=["sales"])
def sales_command(message):
    set_user_mode(message.from_user.id, "sales")
    bot.reply_to(message, "Включен режим продаж.")


@bot.message_handler(commands=["ops"])
def ops_command(message):
    set_user_mode(message.from_user.id, "ops")
    bot.reply_to(message, "Включен операционный режим.")


@bot.message_handler(commands=["hr"])
def hr_command(message):
    set_user_mode(message.from_user.id, "hr")
    bot.reply_to(message, "Включен HR-режим.")


@bot.message_handler(commands=["content"])
def content_command(message):
    set_user_mode(message.from_user.id, "content")
    bot.reply_to(message, "Включен режим контента.")


@bot.message_handler(commands=["finance"])
def finance_command(message):
    set_user_mode(message.from_user.id, "finance")
    bot.reply_to(message, "Включен финансовый режим.")


@bot.message_handler(commands=["producer"])
def producer_command(message):
    set_user_mode(message.from_user.id, "producer")
    bot.reply_to(message, "Включен режим реализатора мероприятия.")


@bot.message_handler(commands=["default"])
def default_command(message):
    set_user_mode(message.from_user.id, "default")
    bot.reply_to(message, "Включен обычный режим.")


@bot.message_handler(commands=["eventcheck"])
def eventcheck_command(message):
    checklist = """
PRE-EVENT CHECK-LIST

1. Клиент и вводные
— дата мероприятия
— время начала и окончания
— количество гостей
— формат мероприятия
— контакт ответственного со стороны клиента

2. Зал и рассадка
— выбран зал
— утверждена схема рассадки
— проверена вместимость
— понятна логика перемещения гостей

3. Еда и напитки
— утверждено меню
— подтвержден welcome
— согласован бар
— учтены ограничения по питанию
— понятен тайминг подачи

4. Техника
— экран
— звук
— микрофоны
— свет
— презентация
— ноутбук / кликер
— ответственный техник

5. Персонал
— менеджер мероприятия
— банкетный менеджер
— официанты
— гардероб
— клининг
— охрана
— техник

6. Подрядчики
— ведущий
— диджей
— декор
— фото / видео
— артисты
— время заезда и выезда

7. Логистика
— монтаж
— демонтаж
— парковка
— вход гостей
— навигация
— зона разгрузки

8. Риски
— что может пойти не так
— кто принимает решения на месте
— запасной план

9. Финальный контроль
— зал готов
— техника проверена
— персонал на месте
— клиент встретен
— тайминг у всех ответственных
"""
    bot.reply_to(message, checklist)


@bot.message_handler(content_types=["voice"])
def handle_voice(message):
    try:
        bot.send_chat_action(message.chat.id, "typing")

        file_info = bot.get_file(message.voice.file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as temp_voice:
            temp_voice.write(downloaded_file)
            temp_voice_path = temp_voice.name

        with open(temp_voice_path, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                model=VOICE_MODEL,
                file=audio_file
            )

        text = transcription.text

        bot.reply_to(message, f"Распознал:\n{text}")

        answer = ask_ai(message.from_user.id, text)

        send_long_reply(
            chat_id=message.chat.id,
            text=answer,
            reply_to_message_id=message.message_id
        )

    except Exception as e:
        bot.reply_to(message, f"Ошибка при обработке голосового: {e}")


@bot.inline_handler(func=lambda query: True)
def inline_query(query):
    try:
        user_text = query.query.strip()

        if not user_text:
            return

        answer = ask_ai(query.from_user.id, user_text)

        result = types.InlineQueryResultArticle(
            id="1",
            title="Ответ AI-ассистента",
            description=answer[:120],
            input_message_content=types.InputTextMessageContent(
                message_text=answer[:4000]
            )
        )

        bot.answer_inline_query(query.id, [result], cache_time=1)

    except Exception:
        pass


@bot.message_handler(content_types=["text"])
def handle_text(message):
    try:
        bot.send_chat_action(message.chat.id, "typing")

        answer = ask_ai(
            user_id=message.from_user.id,
            user_text=message.text
        )

        send_long_reply(
            chat_id=message.chat.id,
            text=answer,
            reply_to_message_id=message.message_id
        )

    except Exception as e:
        bot.reply_to(message, f"Ошибка: {e}")


@bot.message_handler(func=lambda message: True)
def handle_other(message):
    bot.reply_to(message, "Пока я понимаю текст и голосовые сообщения.")


bot.infinity_polling(skip_pending=True)
