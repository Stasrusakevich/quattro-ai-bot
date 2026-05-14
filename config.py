from dotenv import load_dotenv
import os


load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
ADMIN_USER_ID = os.getenv("ADMIN_USER_ID")
