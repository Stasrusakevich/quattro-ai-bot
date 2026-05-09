import tempfile
from telebot import types

from config import (
    SECRET_ADMIN_COMMAND,
    SECRET_MEMORY_COMMAND,
    VOICE_MODEL
)
from menus import main_menu, admin_menu
from eventcheck import get_event_checklist
from memory import (
    save_memory,
    is_admin,
    can_edit_memory,
    grant_admin_access,
    grant_memory_access
)
from ai import (
    ask_ai,
    split_long_message,
    set_user_mode,
    get_user_mode,
    clear_user_history
)


def send_long_reply(bot, chat_id, text, reply_to_message_id=None):
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


def register_handlers(bot, client):

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
        clear_user_history(message.from_user.id)
        bot.reply_to(message, "Память текущего диалога очищена.")

    @bot.message_handler(commands=["remember"])
    def remember_command(message):
        if not can_edit_memory(message.from_user.id):
            bot.reply_to(
                message,
                "У тебя нет доступа к изменению памяти. Обратись к администратору."
            )
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

    @bot.message_handler(func=lambda message: message.text == SECRET_ADMIN_COMMAND)
    def secret_admin_access(message):
        grant_admin_access(message.from_user.id)

        bot.send_message(
            message.chat.id,
            "Админ-доступ открыт.",
            reply_markup=admin_menu()
        )

    @bot.message_handler(func=lambda message: message.text == SECRET_MEMORY_COMMAND)
    def secret_memory_access(message):
        grant_memory_access(message.from_user.id)

        bot.reply_to(
            message,
            "Доступ к добавлению памяти открыт. Теперь можно использовать команду /remember."
        )

    @bot.message_handler(func=lambda message: message.text == "⬅️ Главное меню")
    def menu_back(message):
        bot.send_message(
            message.chat.id,
            "Главное меню:",
            reply_markup=main_menu()
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
        if not is_admin(message.from_user.id):
            bot.reply_to(message, "Этот раздел доступен только администратору.")
            return

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
        if not can_edit_memory(message.from_user.id):
            bot.reply_to(
                message,
                "У тебя нет доступа к изменению памяти. Обратись к администратору."
            )
            return

        text = """
Чтобы добавить информацию в память, напиши:

/remember текст, который нужно запомнить

Например:
/remember У Компаса отдельный вход и он лучше подходит для закрытых встреч на 40–60 человек.
"""
        bot.reply_to(message, text)

    @bot.message_handler(func=lambda message: message.text == "🧹 Очистить диалог")
    def menu_reset(message):
        clear_user_history(message.from_user.id)
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

            answer = ask_ai(client, message.from_user.id, text)

            send_long_reply(
                bot=bot,
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

            answer = ask_ai(client, query.from_user.id, user_text)

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
                client=client,
                user_id=message.from_user.id,
                user_text=message.text
            )

            send_long_reply(
                bot=bot,
                chat_id=message.chat.id,
                text=answer,
                reply_to_message_id=message.message_id
            )

        except Exception as e:
            bot.reply_to(message, f"Ошибка: {e}")

    @bot.message_handler(func=lambda message: True)
    def handle_other(message):
        bot.reply_to(message, "Пока я понимаю текст и голосовые сообщения.")
