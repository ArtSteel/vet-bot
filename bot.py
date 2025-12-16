# bot.py — VET EDITION (V6.2: Stable Core + Fixed Tone)

import os
import asyncio
import logging
import json
from typing import List, Optional

from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, BotCommand, BotCommandScopeDefault
from aiogram.client.default import DefaultBotProperties
from dotenv import load_dotenv

# Подключаем модули проекта
import storage as st
from handlers.ocr import router as ocr_router, register_answer_callback
from handlers.core import router as core_router
from handlers.medcard import router as medcard_router
from handlers.menu import router as menu_router
from handlers.pay import router as pay_router, yookassa_polling_loop
from handlers.feedback import router as feedback_router
from ai_client import VseGPTClient, ModelConfig

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(name)s - %(message)s"
)
logger = logging.getLogger("VetBot")

load_dotenv()

# --- ГЛОБАЛЬНЫЕ ОБЪЕКТЫ ---
ai_router = Router()
client: VseGPTClient | None = None

# --- КОНФИГУРАЦИЯ ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

FREE_DAILY_LIMIT = int(os.getenv("FREE_DAILY_LIMIT", "5"))
PLUS_DAILY_LIMIT = os.getenv("PLUS_DAILY_LIMIT", os.getenv("STANDARD_DAILY_LIMIT", "50"))
PRO_DAILY_LIMIT = os.getenv("PRO_DAILY_LIMIT", None)  # None = безлимит

FREE_PHOTOS_PER_MONTH = int(os.getenv("FREE_PHOTOS_PER_MONTH", "1"))
PLUS_PHOTOS_PER_MONTH = int(os.getenv("PLUS_PHOTOS_PER_MONTH", "10"))
PRO_PHOTOS_PER_MONTH = os.getenv("PRO_PHOTOS_PER_MONTH", "20")

def _env_first(*keys: str, default: str = "") -> str:
    for k in keys:
        v = os.getenv(k, "")
        if v is not None and str(v).strip() != "":
            return str(v).strip()
    return default


# Совместимость с env из мед-бота:
# - VSEGPT_MODEL_TEXT_FREE / VSEGPT_MODEL_TEXT_MAX
# - VSEGPT_MODEL_VISION_PRO (и др.)
MODEL_FREE_CHAT = _env_first("MODEL_FREE_CHAT", "VSEGPT_MODEL_TEXT_FREE", default="gpt-4o-mini")
MODEL_PLUS_CHAT = _env_first("MODEL_PLUS_CHAT", "MODEL_STANDARD_CHAT", "VSEGPT_MODEL_TEXT_MAX", default="gpt-4o-mini")
MODEL_PRO_CHAT = _env_first("MODEL_PRO_CHAT", "VSEGPT_MODEL_TEXT_MAX", default="gpt-4o")
MODEL_FREE_VISION = _env_first("MODEL_FREE_VISION", "VSEGPT_MODEL_VISION_FREE", default="vis-openai/gpt-4o-mini")
MODEL_PLUS_VISION = _env_first("MODEL_PLUS_VISION", "VSEGPT_MODEL_VISION_PLUS", default="vis-openai/gpt-4o-mini")
MODEL_PRO_VISION = _env_first("MODEL_PRO_VISION", "VSEGPT_MODEL_VISION_PRO", default="vis-openai/gpt-4o-mini")

MAX_TOKENS_FREE = int(os.getenv("MAX_TOKENS_FREE", "500"))
MAX_TOKENS_STANDARD = int(os.getenv("MAX_TOKENS_STANDARD", "800"))
MAX_TOKENS_PRO = int(os.getenv("MAX_TOKENS_PRO", "1200"))
MAX_TOKENS_PRO_VISION = int(os.getenv("MAX_TOKENS_PRO_VISION", "1200"))

MAX_CHARS_FREE = int(os.getenv("MAX_CHARS_FREE", "2000"))
MAX_CHARS_STANDARD = int(os.getenv("MAX_CHARS_STANDARD", "6000"))
MAX_CHARS_PRO = int(os.getenv("MAX_CHARS_PRO", "12000"))

VSEGPT_API_KEY = os.getenv("VSEGPT_API_KEY", "")
VSEGPT_BASE_URL = os.getenv("VSEGPT_BASE_URL", "https://api.vsegpt.ru/v1")

raw_admins = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = []
if raw_admins:
    for x in raw_admins.split(","):
        if x.strip().isdigit(): ADMIN_IDS.append(int(x.strip()))

LEGAL_DISCLAIMER = "\n\n_⚠️ Я ИИ-ассистент. В экстренных случаях (кровотечение, удушье, судороги) немедленно обратитесь к врачу._"

# === ИСПРАВЛЕННЫЙ СИСТЕМНЫЙ ПРОМПТ (БЕЗ ВОДЫ И ДУБЛЕЙ) ===
DEFAULT_PROMPT = """
Ты — «ВетСоветник», профессиональный ветеринар. 🐶
Твоя цель: дать четкий медицинский совет.

🛑 ЖЕСТКИЕ ПРАВИЛА:
1. **БЕЗ ВОДЫ:** Не пиши фразы "Я понимаю вашу тревогу", "Мне жаль", "Это серьезный вопрос". Начинай ответ сразу с анализа симптомов.
2. **БЕЗ ДУБЛЕЙ:** В конце ответа ЗАПРЕЩЕНО писать "Я искусственный интеллект, обратитесь к врачу". Это делает система.
3. **ОФОРМЛЕНИЕ:** Используй списки и смайлики. Таблицы ЗАПРЕЩЕНЫ.
4. **КОНТЕКСТ:** Вес и вид пациента есть в [SYSTEM DATA]. Не спрашивай их заново.

🧠 АЛГОРИТМ ОТВЕТА:
- Если данных мало: Задай 3 конкретных вопроса и закончи фразой "Жду ответ 👇".
- Если данных достаточно:
  1. Краткая гипотеза (что это может быть).
  2. Первая помощь (препараты с дозировками на вес).
  3. Диета/Уход.
  4. Когда срочно к врачу.
""".strip()

def _limits_by_tier() -> dict:
    limits = {"free": int(FREE_DAILY_LIMIT), "plus": int(PLUS_DAILY_LIMIT)}
    if PRO_DAILY_LIMIT is None or str(PRO_DAILY_LIMIT).strip() == "":
        limits["pro"] = None
    else:
        limits["pro"] = int(PRO_DAILY_LIMIT)
    return limits


def _model_cfg_for(tier: str, has_image: bool) -> ModelConfig:
    tier = (tier or "free").lower()
    if has_image:
        if tier == "pro":
            model = MODEL_PRO_VISION
        elif tier == "plus":
            model = MODEL_PLUS_VISION
        else:
            model = MODEL_FREE_VISION
        return ModelConfig(model=model, temperature=0.2, max_tokens=MAX_TOKENS_PRO_VISION)
    if tier == "pro":
        return ModelConfig(model=MODEL_PRO_CHAT, temperature=0.3, max_tokens=MAX_TOKENS_PRO)
    if tier == "plus":
        return ModelConfig(model=MODEL_PLUS_CHAT, temperature=0.3, max_tokens=MAX_TOKENS_STANDARD)
    return ModelConfig(model=MODEL_FREE_CHAT, temperature=0.3, max_tokens=MAX_TOKENS_FREE)


def _max_chars_for(tier: str) -> int:
    tier = (tier or "free").lower()
    if tier == "pro":
        return MAX_CHARS_PRO
    if tier == "standard":
        return MAX_CHARS_STANDARD
    return MAX_CHARS_FREE

# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===

def feedback_kb(entry_id: int, source: str):
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="👍", callback_data=f"fb:like:{source}:{entry_id}"),
                InlineKeyboardButton(text="👎", callback_data=f"fb:dislike:{source}:{entry_id}"),
            ]
        ]
    )


async def send_long_message(message: Message, text: str) -> Message | None:
    if not text: return
    chunk_size = 3500
    last_msg: Message | None = None
    for i in range(0, len(text), chunk_size):
        chunk = text[i:i + chunk_size]
        try:
            last_msg = await message.answer(chunk, parse_mode="Markdown")
        except:
            last_msg = await message.answer(chunk, parse_mode=None)
    return last_msg

def build_context(user_id: int) -> List[dict]:
    context = []
    pet = st.get_active_pet(user_id)
    
    if pet:
        info = (
            f"АКТИВНЫЙ ПАЦИЕНТ:\n"
            f"Имя: {pet['name']}\n"
            f"Вид: {pet['type']}\n"
            f"Порода: {pet['breed']}\n"
            f"Вес: {pet['weight']} кг\n"
            f"Возраст: {pet['age']}\n"
            f"Хроника: {pet['chronic']}"
        )
        context.append({"role": "system", "content": f"[SYSTEM DATA] {info}"})
    
    for _, u, b in reversed(st.get_last_entries(user_id, 3)):
        context.extend([{"role": "user", "content": u}, {"role": "assistant", "content": b}])
    
    return context

# === ОБРАБОТЧИК СООБЩЕНИЙ ===

async def unified_ai_entry(message: Message, prompt: str, image_bytes: Optional[bytes] = None):
    user_id = message.from_user.id
    pet = st.get_active_pet(user_id)
    if not pet:
        from handlers.medcard import show_medcard_menu
        await message.answer("⚠️ **Я не знаю, кого мы лечим.**\nПожалуйста, создайте профиль питомца.")
        await show_medcard_menu(message)
        return

    tier = "pro" if user_id in ADMIN_IDS else None
    if user_id not in ADMIN_IDS:
        limit = st.check_user_limits(
            user_id,
            message.from_user.username or "Unknown",
            _limits_by_tier(),
            consume=False,
        )
        if not limit["allowed"]:
            await message.answer("⛔ Лимит вопросов на сегодня исчерпан.\nОформите подписку: /buy")
            return
        tier = limit.get("tier") or "free"

        max_chars = _max_chars_for(tier)
        if prompt and len(prompt) > max_chars:
            await message.answer(
                f"⚠️ Сообщение слишком длинное для тарифа **{tier.upper()}**.\n"
                f"Максимум: **{max_chars}** символов.\n\n"
                "Сократите текст или оформите подписку: /buy"
            )
            return
        # Теперь списываем (после всех валидаций) — только для ТЕКСТА
        if not image_bytes:
            st.check_user_limits(
                user_id,
                message.from_user.username or "Unknown",
                _limits_by_tier(),
                consume=True,
            )

    await message.bot.send_chat_action(message.chat.id, "typing")
    cfg = _model_cfg_for(tier, bool(image_bytes))
    reply = await client.chat(DEFAULT_PROMPT, prompt, build_context(user_id), cfg, image_bytes=image_bytes)
    
    # === ОЧИСТКА ОТ ДУБЛЕЙ И ЗАГОЛОВКОВ ===
    # Убираем заголовки, если модель их сгенерировала
    reply = reply.replace("**Эмпатия**", "").replace("Эмпатия:", "")
    reply = reply.replace("**Анализ**", "").replace("Анализ:", "")
    
    # Убираем дубли дисклеймера (вариации)
    clean_phrases = [
        "Я ИИ-ассистент", 
        "Я искусственный интеллект", 
        "обратитесь к ветеринару", 
        "визит к врачу обязателен"
    ]
    
    # Если это не середина предложения, а конец — можно почистить, но аккуратно.
    # Проще просто добавить наш дисклеймер, модель в новом промпте должна молчать.
    
    reply = reply.replace("### ", "").replace("**", "*").strip()
    reply += LEGAL_DISCLAIMER
    
    entry_id = st.save_entry(user_id, prompt if not image_bytes else "[📸]", reply)

    last_msg = await send_long_message(message, reply)
    if last_msg:
        try:
            source = "vision" if image_bytes else "text"
            await last_msg.edit_reply_markup(reply_markup=feedback_kb(entry_id, source))
        except Exception:
            pass

@ai_router.message(F.text & ~F.text.startswith("/"))
async def free_text(message: Message):
    await unified_ai_entry(message, message.text)

async def reminder_loop(bot: Bot):
    while True:
        try:
            notifications = st.check_reminders_today()
            for uid, text in notifications:
                try: await bot.send_message(uid, text)
                except: pass
            await asyncio.sleep(60 * 60 * 24) 
        except:
            await asyncio.sleep(60)

# === ЗАПУСК ===
async def main():
    global client
    load_dotenv()
    st.init_db()

    client = VseGPTClient(VSEGPT_API_KEY, VSEGPT_BASE_URL)
    bot = Bot(token=os.getenv("TELEGRAM_BOT_TOKEN"), default=DefaultBotProperties(parse_mode="Markdown"))
    dp = Dispatcher()
    
    register_answer_callback(unified_ai_entry)
    
    dp.include_router(core_router)
    dp.include_router(pay_router)
    dp.include_router(medcard_router)
    dp.include_router(ocr_router)
    dp.include_router(menu_router)
    dp.include_router(feedback_router)
    dp.include_router(ai_router)
    
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(reminder_loop(bot))
    asyncio.create_task(yookassa_polling_loop(bot))
    
    print("✅ VET-BOT ЗАПУЩЕН! (v6.2 Stable + No Spam)")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass