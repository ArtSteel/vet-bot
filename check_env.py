import os
import sys
from dotenv import load_dotenv


REQUIRED_VARS = ("TELEGRAM_BOT_TOKEN", "AI_API_KEY", "REDIS_URL")


def validate_required_env() -> None:
    """
    Smoke-check required environment variables for local/dev startup.
    Stops process with clear message if any critical variable is missing.
    """
    load_dotenv()
    missing = [name for name in REQUIRED_VARS if not str(os.getenv(name, "")).strip()]
    if missing:
        formatted = ", ".join(missing)
        raise RuntimeError(
            "Missing required environment variables in .env: "
            f"{formatted}. Please fill them before starting the bot."
        )


if __name__ == "__main__":
    try:
        validate_required_env()
        print("Environment check passed.")
    except Exception as exc:
        print(f"Environment check failed: {exc}")
        sys.exit(1)

