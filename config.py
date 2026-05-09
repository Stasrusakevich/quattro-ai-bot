import os

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not TELEGRAM_TOKEN:
    raise ValueError("Не найден TELEGRAM_TOKEN")

if not GROQ_API_KEY:
    raise ValueError("Не найден GROQ_API_KEY")

GROQ_BASE_URL = "https://api.groq.com/openai/v1"

TEXT_MODEL = "llama-3.1-8b-instant"
VOICE_MODEL = "whisper-large-v3"

MAX_HISTORY_MESSAGES = 12

SECRET_ADMIN_COMMAND = "/qs_root_91472x"
SECRET_MEMORY_COMMAND = "/qs_sync_58391k"

ADMIN_IDS = set()
MEMORY_ALLOWED_IDS = set()
