from telebot import types


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
        types.KeyboardButton("📚 База знаний")
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
