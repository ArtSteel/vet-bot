import os
from dotenv import load_dotenv


load_dotenv()


def _env_first(*keys: str, default: str = "") -> str:
    for key in keys:
        value = os.getenv(key, "")
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    return default


# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# AI provider (OpenAI-compatible)
# Keep backward compatibility with existing VSEGPT_* variables.
AI_API_KEY = _env_first("AI_API_KEY", "VSEGPT_API_KEY", "OPENAI_API_KEY", default="")
AI_BASE_URL = _env_first(
    "AI_BASE_URL",
    "VSEGPT_BASE_URL",
    "OPENAI_BASE_URL",
    default="https://api.vsegpt.ru/v1",
)

# Redis (FSM storage)
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

# Database
POSTGRES_USER = os.getenv("POSTGRES_USER", "")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")
POSTGRES_DB = os.getenv("POSTGRES_DB", "")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
DATABASE_URL = os.getenv("DATABASE_URL", "")

