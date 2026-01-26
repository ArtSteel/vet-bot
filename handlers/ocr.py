# handlers/ocr.py — VET VERSION: Анализ фото (Только для PRO)

import io
import logging
from typing import Callable, Awaitable, Optional

from aiogram import Router, F
from aiogram.types import Message
from PIL import Image
import fitz  # PyMuPDF для PDF
import storage as st # Подключаем базу для проверки тарифа
import os

router = Router()
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()]
FREE_PHOTOS_PER_MONTH = int(os.getenv("FREE_PHOTOS_PER_MONTH", "1"))
PLUS_PHOTOS_PER_MONTH = int(os.getenv("PLUS_PHOTOS_PER_MONTH", "10"))
PRO_PHOTOS_PER_MONTH_RAW = os.getenv("PRO_PHOTOS_PER_MONTH", "20")
PRO_PHOTOS_PER_MONTH = None if not PRO_PHOTOS_PER_MONTH_RAW.strip() else int(PRO_PHOTOS_PER_MONTH_RAW)

AnswerCallback = Callable[[Message, str, Optional[bytes]], Awaitable[None]]
_ANSWER_CALLBACK: Optional[AnswerCallback] = None

def register_answer_callback(func: AnswerCallback):
    global _ANSWER_CALLBACK
    _ANSWER_CALLBACK = func

async def _prepare_file(message: Message, file_id: str, is_pdf: bool = False) -> Optional[bytes]:
    try:
        file_info = await message.bot.get_file(file_id)
        buf = io.BytesIO()
        await message.bot.download_file(file_info.file_path, buf)
        buf.seek(0)

        if is_pdf:
            doc = fitz.open(stream=buf, filetype="pdf")
            if doc.page_count < 1: return None
            page = doc.load_page(0)
            pix = page.get_pixmap(dpi=200)
            img_data = pix.tobytes("jpg")
            img = Image.open(io.BytesIO(img_data))
        else:
            img = Image.open(buf)
        
        if img.mode != 'RGB': img = img.convert('RGB')

        max_dim = 2048
        if max(img.size) > max_dim: img.thumbnail((max_dim, max_dim))

        out_buf = io.BytesIO()
        img.save(out_buf, format='JPEG', quality=85)
        return out_buf.getvalue()

    except Exception as e:
        logging.error(f"Error processing file: {e}")
        return None

# --- Хендлеры ---

@router.message(F.photo)
async def on_photo(message: Message):
    # 1. ПРОВЕРКА ДОСТУПА + ЛИМИТА (Tier + monthly photo limit)
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        photo_limits = {"free": FREE_PHOTOS_PER_MONTH, "plus": PLUS_PHOTOS_PER_MONTH, "pro": PRO_PHOTOS_PER_MONTH}
        chk = await st.check_photo_limits(user_id, message.from_user.username or "Unknown", photo_limits, consume=False)
        if not chk["allowed"]:
            await message.answer(
                "⛔ Лимит фото/документов на этот месяц исчерпан.\n\n"
                "Чтобы продолжить разбор снимков и анализов, подключите тариф PLUS/PRO: /buy"
            )
            return
        # списываем только если реально будем обрабатывать
        await st.check_photo_limits(user_id, message.from_user.username or "Unknown", photo_limits, consume=True)

    # 2. Основная логика
    if not _ANSWER_CALLBACK: return
    
    await message.bot.send_chat_action(message.chat.id, "upload_photo")
    img_bytes = await _prepare_file(message, message.photo[-1].file_id, is_pdf=False)
    
    if img_bytes:
        # ВЕТЕРИНАРНЫЙ ПРОМПТ ДЛЯ ФОТО
        caption = message.caption or (
            "Это изображение от владельца животного (симптом или документ). "
            "1. Если это анализы — выдели показатели, которые НЕ в норме для этого вида животного. "
            "2. Если это фото питомца — опиши, что видишь (травма, воспаление, стул) и насколько это выглядит опасно. "
            "3. НЕ ставь диагноз, но подскажи, нужен ли очный врач срочно."
        )
        
        await message.reply("🔎 Изучаю снимок...")
        await _ANSWER_CALLBACK(message, caption, img_bytes)

@router.message(F.document)
async def on_document(message: Message):
    # 1. ПРОВЕРКА ТИПА ФАЙЛА
    mime = (message.document.mime_type or "").lower()
    is_image = mime.startswith("image/")
    is_pdf = mime == "application/pdf"
    
    if not (is_image or is_pdf):
        await message.reply("Я понимаю только картинки (JPG/PNG) и PDF документы.")
        return

    # 2. ПРОВЕРКА ДОСТУПА + ЛИМИТА (Tier + monthly photo limit)
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        photo_limits = {"free": FREE_PHOTOS_PER_MONTH, "plus": PLUS_PHOTOS_PER_MONTH, "pro": PRO_PHOTOS_PER_MONTH}
        chk = await st.check_photo_limits(user_id, message.from_user.username or "Unknown", photo_limits, consume=False)
        if not chk["allowed"]:
            await message.answer(
                "⛔ Лимит фото/документов на этот месяц исчерпан.\n\n"
                "Чтобы продолжить разбор снимков и анализов, подключите тариф PLUS/PRO: /buy"
            )
            return
        await st.check_photo_limits(user_id, message.from_user.username or "Unknown", photo_limits, consume=True)

    # 3. Основная логика
    if not _ANSWER_CALLBACK: return

    await message.bot.send_chat_action(message.chat.id, "upload_photo")
    img_bytes = await _prepare_file(message, message.document.file_id, is_pdf=is_pdf)
    
    if img_bytes:
        caption = message.caption or (
            "Это ветеринарный документ (анализы или выписка). "
            "1. Кратко объясни простыми словами, что здесь написано. "
            "2. Выдели критические отклонения. "
            "3. Подскажи хозяину, о чем спросить врача на приеме."
        )
        
        await message.reply("🔎 Читаю документ...")
        await _ANSWER_CALLBACK(message, caption, img_bytes)
    else:
        await message.reply("Не удалось прочитать файл. Попробуйте прислать фото или скриншот.")