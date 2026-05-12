from handlers.start import start_command
from handlers.help import help_command
from handlers.messages import handle_message
from services.ai import generate_ai_response
from services.memory import save_message, get_memory
from database.db import connect_db


def main():
    print(start_command())
    print(help_command())
    print(connect_db())

    user_message = "Привет, хочу узнать про площадку"
    save_message(user_message)

    response = generate_ai_response(user_message)
    print(handle_message(response))
    print("Memory:", get_memory())


if __name__ == "__main__":
    main()
