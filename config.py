from dataclasses import dataclass, field
import os
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Settings:
    token: str
    owner_id: int
    data_dir: Path
    openai_key: str = field(default="", repr=False)
    openai_model: str = "gpt-5-mini"
    allowed_user_ids: frozenset[int] = frozenset()
    allowed_chat_ids: frozenset[int] = frozenset()
    # Opt-in even when an old environment already contains provider keys.
    ai_enabled: bool = False
    ai_provider: str = "deepseek"
    ai_model: str = ""
    deepseek_key: str = field(default="", repr=False)
    anthropic_key: str = field(default="", repr=False)

    @property
    def ai_model_id(self):
        return self.ai_model or {
            "deepseek": "deepseek-flash",
            "openai": self.openai_model,
            "anthropic": "claude-sonnet-4-6",
        }.get(self.ai_provider, "")

    @property
    def ai_key_name(self):
        return {
            "deepseek": "DEEPSEEK_API_KEY",
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
        }.get(self.ai_provider, "")

    @property
    def ai_key(self):
        return {
            "deepseek": self.deepseek_key,
            "openai": self.openai_key,
            "anthropic": self.anthropic_key,
        }.get(self.ai_provider, "")


def load_settings():
    load_dotenv(ROOT / ".env")
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    owner = os.getenv("ADMIN_USER_ID", "").strip()
    if not token or not owner.isdecimal() or int(owner) <= 0:
        raise ValueError("Задайте TELEGRAM_BOT_TOKEN и положительный ADMIN_USER_ID.")
    owner_id = int(owner)
    users = frozenset(
        int(value.strip())
        for value in os.getenv("ALLOWED_USER_IDS", "").split(",")
        if value.strip()
    ) | {owner_id}
    chats = frozenset(
        int(value.strip())
        for value in os.getenv("ALLOWED_CHAT_IDS", "").split(",")
        if value.strip()
    )
    if any(value <= 0 for value in users) or any(value >= 0 for value in chats):
        raise ValueError("ID пользователей должны быть положительными, ID групп — отрицательными.")
    data_dir = Path(os.getenv("DATA_DIR", str(ROOT / "data"))).expanduser()
    if not data_dir.is_absolute():
        data_dir = ROOT / data_dir
    return Settings(
        token=token,
        owner_id=owner_id,
        data_dir=data_dir,
        openai_key=os.getenv("OPENAI_API_KEY", "").strip(),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5-mini").strip(),
        allowed_user_ids=frozenset(users),
        allowed_chat_ids=chats,
        # Unrecognized values fail closed without preventing notes/tasks.
        ai_enabled=os.getenv("AI_ENABLED", "false").strip().lower() == "true",
        ai_provider=os.getenv("AI_PROVIDER", "deepseek").strip().lower(),
        ai_model=os.getenv("AI_MODEL", "").strip(),
        deepseek_key=os.getenv("DEEPSEEK_API_KEY", "").strip(),
        anthropic_key=os.getenv("ANTHROPIC_API_KEY", "").strip(),
    )
