from config import ADMIN_IDS, MEMORY_ALLOWED_IDS


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
    return user_id in ADMIN_IDS


def can_edit_memory(user_id):
    return user_id in ADMIN_IDS or user_id in MEMORY_ALLOWED_IDS


def grant_admin_access(user_id):
    ADMIN_IDS.add(user_id)
    MEMORY_ALLOWED_IDS.add(user_id)


def grant_memory_access(user_id):
    MEMORY_ALLOWED_IDS.add(user_id)
