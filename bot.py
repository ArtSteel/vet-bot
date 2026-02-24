# bot.py — VET EDITION (V6.2: Stable Core + Fixed Tone)

import os
import asyncio
import logging
import json
import re
from typing import List, Optional

from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, BotCommand, BotCommandScopeDefault
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.redis import RedisStorage
from dotenv import load_dotenv

# Подключаем модули проекта
import storage as st
import config
from handlers.ocr import router as ocr_router, register_answer_callback
from handlers.core import router as core_router
from handlers.medcard import router as medcard_router
from handlers.menu import router as menu_router
from handlers.pay import router as pay_router, yookassa_polling_loop
from handlers.feedback import router as feedback_router
from handlers.promo import router as promo_router
from handlers.admin import router as admin_router
from middlewares.logger_middleware import LoggingMiddleware
from ai_client import VseGPTClient, ModelConfig
from check_env import validate_required_env

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(name)s - %(message)s"
)
logger = logging.getLogger("VetBot")

# Отключаем шумные логи aiogram
logging.getLogger("aiogram.event").setLevel(logging.WARNING)

load_dotenv()

# --- ГЛОБАЛЬНЫЕ ОБЪЕКТЫ ---
ai_router = Router()
client: VseGPTClient | None = None

# --- КОНФИГУРАЦИЯ ---
TELEGRAM_BOT_TOKEN = config.TELEGRAM_BOT_TOKEN

FREE_DAILY_LIMIT = int(os.getenv("FREE_DAILY_LIMIT", "5"))
FREE_DAILY_TEXT_LIMIT = int(os.getenv("FREE_DAILY_TEXT_LIMIT", "3"))
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

VSEGPT_API_KEY = config.AI_API_KEY
VSEGPT_BASE_URL = config.AI_BASE_URL

raw_admins = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = []
if raw_admins:
    for x in raw_admins.split(","):
        if x.strip().isdigit(): ADMIN_IDS.append(int(x.strip()))

LEGAL_DISCLAIMER = "\n\n_⚠️ Я ИИ-ассистент. В экстренных случаях немедленно обратитесь к врачу._"

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

# === ПРОМПТ ДЛЯ АНАЛИЗА АНАЛИЗОВ (СИСТЕМА "СВЕТОФОР") ===
ANALYSIS_PROMPT = """
Ты — опытный ветеринарный AI-ассистент. Твоя задача — интерпретировать результаты анализов.

📋 ФОРМАТ ОТВЕТА (система "Светофор"):

Используй эмодзи для визуальной оценки показателей:
- 🔴 (Красный круг) — показатели, которые критически выходят за норму и требуют срочного внимания.
- 🟡 (Желтый круг) — пограничные значения или незначительные отклонения.
- 🟢 (Зеленый круг) — показатели в норме (упоминай кратко, если важны для контекста, или группируй).

📝 СТРУКТУРА ОТВЕТА:

1. **Краткое резюме:** (1-2 предложения о состоянии питомца на основе анализов).

2. **Детальный разбор:** 
   - Список показателей с эмодзи 🔴/🟡/🟢
   - Для каждого отклонения: название показателя, значение, норма для вида/возраста, что это может означать.

3. **Рекомендации:** 
   - Что спросить у врача на приеме
   - Какие дополнительные симптомы проверить
   - Нужны ли дополнительные анализы

⚠️ **ВАЖНО:** 
- Если ситуация выглядит жизнеугрожающей, начни ответ с жирного текста: **⚠️ СРОЧНО ОБРАТИТЕСЬ В КЛИНИКУ!**
- Не ставь диагноз, но четко указывай на критические отклонения.
- Используй простой язык, понятный владельцу животного.
""".strip()

def _limits_by_tier() -> dict:
    limits = {"free": int(FREE_DAILY_LIMIT), "plus": int(PLUS_DAILY_LIMIT)}
    if PRO_DAILY_LIMIT is None or str(PRO_DAILY_LIMIT).strip() == "":
        limits["pro"] = None
    else:
        limits["pro"] = int(PRO_DAILY_LIMIT)
    return limits


async def get_model_for_user(user_id: int, has_image: bool) -> ModelConfig:
    """
    Определяет модель для пользователя:
    - Free: deepseek/deepseek-v3.2-alt
    - Paid (Подписка ИЛИ была разовая покупка за последние 24ч): qwen/qwen3-max
    - Vision везде: vis-openai/gpt-4o-mini
    """
    if has_image:
        # Vision везде используем vis-openai/gpt-4o-mini
        return ModelConfig(model="vis-openai/gpt-4o-mini", temperature=0.2, max_tokens=MAX_TOKENS_PRO_VISION)
    
    # Проверяем, является ли пользователь платным
    has_sub = await st.has_active_subscription(user_id)
    had_recent_purchase = await st.had_recent_one_time_purchase(user_id, hours=24)
    is_paid = has_sub or had_recent_purchase
    
    if is_paid:
        # Paid: qwen/qwen3-max
        return ModelConfig(model="qwen/qwen3-max", temperature=0.3, max_tokens=MAX_TOKENS_PRO)
    else:
        # Free: deepseek/deepseek-v3.2-alt
        return ModelConfig(model="deepseek/deepseek-v3.2-alt", temperature=0.3, max_tokens=MAX_TOKENS_FREE)


def _model_cfg_for(tier: str, has_image: bool) -> ModelConfig:
    """Старая функция для обратной совместимости (используется в некоторых местах)"""
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
        except Exception as e:
            logger.error(f"Error in send_long_message: {e}")
            last_msg = await message.answer(chunk, parse_mode=None)
    return last_msg

async def build_context(user_id: int) -> List[dict]:
    context = []
    pet = await st.get_active_pet(user_id)
    
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
    
    entries = await st.get_last_entries(user_id, 3)
    for _, u, b in reversed(entries):
        context.extend([{"role": "user", "content": u}, {"role": "assistant", "content": b}])
    
    return context

# === ОБРАБОТЧИК СООБЩЕНИЙ ===

async def unified_ai_entry(message: Message, prompt: str, image_bytes: Optional[bytes] = None, is_analysis_document: bool = False):
    user_id = message.from_user.id
    pet = await st.get_active_pet(user_id)
    if not pet:
        from handlers.medcard import show_medcard_menu
        await message.answer("⚠️ **Я не знаю, кого мы лечим.**\nПожалуйста, создайте профиль питомца.")
        await show_medcard_menu(message)
        return

    tier = "pro" if user_id in ADMIN_IDS else None
    if user_id not in ADMIN_IDS:
        # Для текстовых сообщений используем новую логику check_text_limits
        if not image_bytes:
            text_limit = await st.check_text_limits(
                user_id,
                message.from_user.username or "Unknown",
                FREE_DAILY_TEXT_LIMIT,
                consume=False,
            )
            if not text_limit["allowed"]:
                await message.answer(
                    "⛔ Лимит текстовых сообщений на сегодня исчерпан.\n\n"
                    "💎 Доступные варианты:\n"
                    "• 📄 Разовый разбор анализов — 99₽\n"
                    "• 🔄 Подписка PLUS/PRO — безлимит\n\n"
                    "Оформить: /buy"
                )
                return
            
            # Определяем tier для проверки длины сообщения
            # Используем get_effective_tier, который проверяет активную подписку
            effective_tier = await st.get_effective_tier(user_id)
            if effective_tier != "free":
                tier = effective_tier  # plus или pro
            elif text_limit.get("reason") == "one_time_purchase":
                # Разовая покупка дает доступ к более мощной модели, но tier остается free для лимитов
                tier = "free"
            else:
                tier = "free"
        else:
            # Для фото/OCR используем старую логику
            limit = await st.check_user_limits(
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
        
        # Списываем лимит (после всех валидаций)
        if not image_bytes:
            # Для текстовых сообщений используем check_text_limits
            await st.check_text_limits(
                user_id,
                message.from_user.username or "Unknown",
                FREE_DAILY_TEXT_LIMIT,
                consume=True,
            )
        else:
            # Для фото/OCR используем старую логику
            await st.check_user_limits(
                user_id,
                message.from_user.username or "Unknown",
                _limits_by_tier(),
                consume=True,
            )

    await message.bot.send_chat_action(message.chat.id, "typing")
    
    # Используем новую функцию выбора модели
    cfg = await get_model_for_user(user_id, bool(image_bytes))
    
    # Выбираем промпт: для анализов используем "Светофор", иначе обычный
    system_prompt = ANALYSIS_PROMPT if is_analysis_document else DEFAULT_PROMPT
    
    reply = await client.chat(system_prompt, prompt, await build_context(user_id), cfg, image_bytes=image_bytes)
    
    # === ОЧИСТКА ОТ ДУБЛЕЙ И ЗАГОЛОВКОВ ===
    # Убираем заголовки, если модель их сгенерировала
    reply = reply.replace("**Эмпатия**", "").replace("Эмпатия:", "")
    reply = reply.replace("**Анализ**", "").replace("Анализ:", "")
    
    # Убираем дубли дисклеймера (вариации) - более агрессивная очистка
    # Паттерны для поиска предупреждений в конце текста (более точные)
    # Ищем предупреждения, которые обычно идут в конце ответа
    disclaimer_patterns = [
        r"\n\n*Я ИИ-ассистент[^.]*\.",  # "Я ИИ-ассистент..." после переноса строки
        r"\n\n*Я искусственный интеллект[^.]*\.",  # "Я искусственный интеллект..." после переноса
        r"\n\n*⚠️[^.]*\.",  # Любые предупреждения с эмодзи
        r"\n\n*В экстренных случаях[^.]*\.",  # "В экстренных случаях..." после переноса
        r"\n\n*обратитесь к врачу[^.]*\.",  # "обратитесь к врачу..." после переноса
        r"\n\n*обратитесь к ветеринару[^.]*\.",  # "обратитесь к ветеринару..." после переноса
        r"\(кровотечение[^)]*\)",  # Убираем скобки с пугающими словами
        r"\(удушье[^)]*\)",  # Убираем скобки с пугающими словами
        r"\(судороги[^)]*\)",  # Убираем скобки с пугающими словами
        r"кровотечение, удушье, судороги",  # Конкретная фраза
    ]
    
    # Удаляем все найденные паттерны
    for pattern in disclaimer_patterns:
        reply = re.sub(pattern, "", reply, flags=re.IGNORECASE)
    
    # Убираем множественные переносы строк и пробелы
    reply = re.sub(r'\n{3,}', '\n\n', reply)  # Максимум 2 переноса подряд
    reply = re.sub(r' {2,}', ' ', reply)  # Убираем множественные пробелы
    reply = reply.replace("### ", "").replace("**", "*").strip()
    
    # Добавляем наш дисклеймер только один раз в конце
    # Проверяем, что его еще нет в тексте
    if "⚠️ Я ИИ-ассистент" not in reply:
        reply += LEGAL_DISCLAIMER
    
    entry_id = await st.save_entry(user_id, prompt if not image_bytes else "[📸]", reply)

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
            notifications = await st.check_reminders_today()
            for uid, text in notifications:
                try:
                    await bot.send_message(uid, text)
                except Exception as e:
                    logger.error(f"Error in reminder_loop send_message: {e}")
            await asyncio.sleep(60 * 60 * 24) 
        except Exception as e:
            logger.error(f"Error in reminder_loop: {e}")
            await asyncio.sleep(60)

# === ЗАПУСК ===
async def main():
    global client
    load_dotenv()
    validate_required_env()
    await st.init_db()  # Async инициализация БД

    client = VseGPTClient(VSEGPT_API_KEY, VSEGPT_BASE_URL)
    bot = Bot(token=TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode="Markdown"))
    storage = RedisStorage.from_url(config.REDIS_URL)
    dp = Dispatcher(storage=storage)
    
    # Подключаем middleware для логирования действий пользователей
    dp.update.outer_middleware(LoggingMiddleware())
    
    register_answer_callback(unified_ai_entry)
    
    dp.include_router(core_router)
    dp.include_router(pay_router)
    dp.include_router(medcard_router)
    dp.include_router(ocr_router)
    dp.include_router(menu_router)
    dp.include_router(feedback_router)
    dp.include_router(promo_router)
    dp.include_router(admin_router)
    dp.include_router(ai_router)
    
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(reminder_loop(bot))
    asyncio.create_task(yookassa_polling_loop(bot))
    
    print("✅ VET-BOT ЗАПУЩЕН! (v6.2 Stable + Async Storage)")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by KeyboardInterrupt")