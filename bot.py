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
ADMIN_IDS = []

user_histories = {}
user_modes = {}

BASE_SYSTEM_PROMPT = """
Ты Quattro Space AI Assistant — помощник сотрудников ивент-площадки Quattro Space.

Твоя задача — помогать сотрудникам в ежедневной работе:
— обрабатывать заявки клиентов
— подбирать залы
— писать ответы клиентам
— делать дожимы
— составлять КП
— готовить чек-листы мероприятий
— помогать реализаторам
— составлять задачи на день
— работать с базой знаний площадки

Стиль:
— коротко
— практично
— по делу
— без воды
— сначала готовое решение
— потом пояснение
— если данных мало, задай максимум один уточняющий вопрос
"""

MODES = {
    "default": """
Режим: универсальный помощник сотрудников Quattro Space.
Помогай с любыми рабочими задачами площадки.
""",

    "client": """
Режим: клиент / заявка.
Фокус: обработка заявки клиента, ответы, дожимы, возражения, уточняющие вопросы, следующий шаг.
""",

    "hall": """
Режим: подбор зала.
Фокус: подобрать подходящий зал Quattro Space под формат, количество гостей, посадку, технику и пожелания клиента.
Всегда предлагай 1 основной зал и 1 альтернативу, если это уместно.
""",

    "proposal": """
Режим: КП / коммерческое предложение.
Фокус: составить структуру КП, короткое сообщение клиенту, официальное письмо, предложение по залу, еде, бару, технике и допродажам.
""",

    "producer": """
Режим: реализация мероприятия / event producer.
Фокус: чек-листы, тайминг, пожелания клиента, зоны ответственности, подрядчики, техника, монтаж, демонтаж и контроль перед стартом.
""",

    "tasks": """
Режим: задачи на день.
Фокус: составить план задач для менеджера, реализатора, операционного сотрудника или руководителя.
Если заявок мало — предложить полезные действия без холодного поиска.
""",

    "knowledge": """
Режим: база знаний.
Фокус: отвечать по информации о Quattro Space, залах, вместимости, форматах, регламентах, правилах и частых вопросах.
""",

    "team": """
Режим: сотрудники / команда.
Фокус: разбор сообщений сотрудников, обратная связь, постановка задач, KPI, конфликты, регламенты.
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

База знаний Quattro Space:
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


def main_menu():
    markup = types.ReplyKeyboardMarkup(
        resize_keyboard=True,
        row_width=2
    )

    buttons = [
        types.KeyboardButton("💬 Клиент / заявка"),
        types.KeyboardButton("📍 Подобрать зал"),
        types.KeyboardButton("📄 Сделать КП"),
        types.KeyboardButton("🎬 Реализация"),
        types.KeyboardButton("✅ Задачи на день"),
        types.KeyboardButton("📚 База знаний"),
        types.KeyboardButton("⚙️ Админ")
    ]

    markup.add(*buttons)
    return markup


def admin_menu():
    markup = types.ReplyKeyboardMarkup(
        resize_keyboard=True,
        row_width=2
    )

    buttons = [
        types.KeyboardButton("🧠 Добавить в память"),
        types.KeyboardButton("👥 Команда / сотрудники"),
        types.KeyboardButton("🧹 Очистить диалог"),
        types.KeyboardButton("📌 Текущий режим"),
        types.KeyboardButton("🆔 Мой ID"),
        types.KeyboardButton("⬅️ Главное меню")
    ]

    markup.add(*buttons)
    return markup


def get_event_checklist():
    return """
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


@bot.message_handler(commands=["start", "help", "menu"])
def start_command(message):
    text = """
Quattro Space AI Assistant

Я помощник сотрудников Quattro Space в ежедневных задачах.

Выбери, что нужно сделать:
"""
    bot.send_message(
        message.chat.id,
        text,
        reply_markup=main_menu()
    )


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


@bot.message_handler(commands=["eventcheck"])
def eventcheck_command(message):
    bot.reply_to(message, get_event_checklist())


@bot.message_handler(func=lambda message: message.text == "⬅️ Главное меню")
def menu_back(message):
    bot.send_message(
        message.chat.id,
        "Главное меню:",
        reply_markup=main_menu()
    )


@bot.message_handler(func=lambda message: message.text == "⚙️ Админ")
def menu_admin(message):
    bot.send_message(
        message.chat.id,
        "Админ-меню:",
        reply_markup=admin_menu()
    )


@bot.message_handler(func=lambda message: message.text == "💬 Клиент / заявка")
def menu_client(message):
    set_user_mode(message.from_user.id, "client")
    text = """
Режим: клиент / заявка.

Пришли заявку клиента или опиши ситуацию.

Что можно попросить:
— написать ответ клиенту
— сделать дожим
— обработать возражение
— составить вопросы клиенту
— предложить следующий шаг

Лучше прислать:
— формат мероприятия
— количество гостей
— дату
— бюджет, если есть
— пожелания клиента
"""
    bot.reply_to(message, text)


@bot.message_handler(func=lambda message: message.text == "📍 Подобрать зал")
def menu_hall(message):
    set_user_mode(message.from_user.id, "hall")
    text = """
Режим: подбор зала.

Пришли вводные:
— количество гостей
— формат мероприятия
— банкет / фуршет / конференция
— нужна ли сцена, экран, звук
— важна ли приватность
— дата, если есть

Я предложу подходящий зал, альтернативу и следующий шаг для клиента.
"""
    bot.reply_to(message, text)


@bot.message_handler(func=lambda message: message.text == "📄 Сделать КП")
def menu_proposal(message):
    set_user_mode(message.from_user.id, "proposal")
    text = """
Режим: КП / предложение.

Пришли вводные:
— формат мероприятия
— дата
— количество гостей
— выбранный зал или “подобрать”
— еда / бар
— техника
— пожелания клиента

Я подготовлю структуру КП или готовый текст сообщения клиенту.
"""
    bot.reply_to(message, text)


@bot.message_handler(func=lambda message: message.text == "🎬 Реализация")
def menu_producer(message):
    set_user_mode(message.from_user.id, "producer")
    text = """
Режим: реализация мероприятия.

Что можно сделать:
— чек-лист мероприятия
— тайминг
— список вопросов клиенту
— задачи подрядчикам
— риски мероприятия
— контроль перед стартом

Пришли вводные:
— дата
— зал
— формат
— количество гостей
— тайминг
— пожелания клиента
— подрядчики
"""
    bot.reply_to(message, text)


@bot.message_handler(func=lambda message: message.text == "✅ Задачи на день")
def menu_tasks(message):
    set_user_mode(message.from_user.id, "tasks")
    text = """
Режим: задачи на день.

Напиши роль и ситуацию.

Примеры:
— менеджер продаж, мало заявок
— реализатор, мероприятие через 3 дня
— операционный сотрудник, нужно проверить площадку
— руководитель, нужно проконтролировать команду

Я составлю конкретный план задач.
"""
    bot.reply_to(message, text)


@bot.message_handler(func=lambda message: message.text == "📚 База знаний")
def menu_knowledge(message):
    set_user_mode(message.from_user.id, "knowledge")
    text = """
Режим: база знаний Quattro Space.

Что можно спросить:
— какие есть залы
— вместимость залов
— какой зал выбрать
— форматы мероприятий
— частые вопросы клиентов
— правила работы
— регламенты

Напиши, что нужно найти или объяснить.
"""
    bot.reply_to(message, text)


@bot.message_handler(func=lambda message: message.text == "👥 Команда / сотрудники")
def menu_team(message):
    set_user_mode(message.from_user.id, "team")
    text = """
Режим: команда / сотрудники.

Что можно сделать:
— разобрать сообщение сотрудника
— подготовить обратную связь
— поставить задачу
— составить KPI
— разобрать конфликт
— написать регламент

Пришли ситуацию или текст сообщения.
"""
    bot.reply_to(message, text)


@bot.message_handler(func=lambda message: message.text == "🧠 Добавить в память")
def menu_memory(message):
    text = """
Чтобы добавить информацию в память, напиши:

/remember текст, который нужно запомнить

Например:
/remember У Компаса отдельный вход и он лучше подходит для закрытых встреч на 40–60 человек.
"""
    bot.reply_to(message, text)


@bot.message_handler(func=lambda message: message.text == "🧹 Очистить диалог")
def menu_reset(message):
    user_histories[message.from_user.id] = []
    bot.reply_to(message, "Память текущего диалога очищена.")


@bot.message_handler(func=lambda message: message.text == "📌 Текущий режим")
def menu_mode(message):
    mode = get_user_mode(message.from_user.id)
    bot.reply_to(message, f"Текущий режим: {mode}")


@bot.message_handler(func=lambda message: message.text == "🆔 Мой ID")
def menu_myid(message):
    bot.reply_to(message, f"Твой Telegram ID: {message.from_user.id}")


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
