# handlers/ocr.py — VET VERSION: Анализ фото (Асинхронная обработка)

import asyncio
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
logger = logging.getLogger("VetBot.OCR")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()]
FREE_PHOTOS_PER_MONTH = int(os.getenv("FREE_PHOTOS_PER_MONTH", "1"))
PLUS_PHOTOS_PER_MONTH = int(os.getenv("PLUS_PHOTOS_PER_MONTH", "10"))
PRO_PHOTOS_PER_MONTH_RAW = os.getenv("PRO_PHOTOS_PER_MONTH", "20")
PRO_PHOTOS_PER_MONTH = None if not PRO_PHOTOS_PER_MONTH_RAW.strip() else int(PRO_PHOTOS_PER_MONTH_RAW)

AnswerCallback = Callable[[Message, str, Optional[bytes], bool], Awaitable[None]]
_ANSWER_CALLBACK: Optional[AnswerCallback] = None

def register_answer_callback(func: AnswerCallback):
    global _ANSWER_CALLBACK
    _ANSWER_CALLBACK = func

def _process_pdf_sync(buf: io.BytesIO) -> Optional[Image.Image]:
    """Синхронная обработка PDF (выполняется в отдельном потоке)"""
    try:
        doc = fitz.open(stream=buf, filetype="pdf")
        if doc.page_count < 1:
            doc.close()
            return None
        page = doc.load_page(0)
        pix = page.get_pixmap(dpi=200)
        img_data = pix.tobytes("jpg")
        doc.close()
        return Image.open(io.BytesIO(img_data))
    except Exception as e:
        logger.error(f"Error in _process_pdf_sync: {e}")
        return None


def _process_image_sync(img: Image.Image) -> Optional[bytes]:
    """Синхронная обработка изображения (выполняется в отдельном потоке)"""
    try:
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        max_dim = 2048
        if max(img.size) > max_dim:
            img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
        
        out_buf = io.BytesIO()
        img.save(out_buf, format='JPEG', quality=85, optimize=True)
        return out_buf.getvalue()
    except Exception as e:
        logger.error(f"Error in _process_image_sync: {e}")
        return None


async def _prepare_file(message: Message, file_id: str, is_pdf: bool = False) -> Optional[bytes]:
    """Асинхронная подготовка файла с неблокирующей обработкой"""
    try:
        file_info = await message.bot.get_file(file_id)
        buf = io.BytesIO()
        await message.bot.download_file(file_info.file_path, buf)
        buf.seek(0)

        if is_pdf:
            # PDF обработка в отдельном потоке
            img = await asyncio.to_thread(_process_pdf_sync, buf)
            if not img:
                return None
        else:
            # Открытие изображения в отдельном потоке
            img = await asyncio.to_thread(Image.open, buf)
        
        # Обработка изображения в отдельном потоке
        result = await asyncio.to_thread(_process_image_sync, img)
        return result

    except Exception as e:
        logger.error(f"Error in _prepare_file: {e}")
        return None

# --- Хендлеры ---

@router.message(F.photo)
async def on_photo(message: Message):
    # 1. НОВАЯ ЛОГИКА ПРОВЕРКИ ДОСТУПА (Trial -> Подписка -> Balance)
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        # Проверка 1: Trial (первый раз бесплатно)
        is_trial = not await st.is_trial_used(user_id)
        if is_trial:
            await st.mark_trial_used(user_id)
            # Пропускаем дальше без проверок
        else:
            # Проверка 2: Активная подписка
            has_sub = await st.has_active_subscription(user_id)
            if has_sub:
                # Проверяем месячные лимиты подписки
                photo_limits = {"free": FREE_PHOTOS_PER_MONTH, "plus": PLUS_PHOTOS_PER_MONTH, "pro": PRO_PHOTOS_PER_MONTH}
                chk = await st.check_photo_limits(user_id, message.from_user.username or "Unknown", photo_limits, consume=False)
                if not chk["allowed"]:
                    await message.answer(
                        "⛔ Лимит фото/документов на этот месяц исчерпан.\n\n"
                        "Чтобы продолжить разбор снимков и анализов, подключите тариф PLUS/PRO: /buy"
                    )
                    return
                # Списываем месячный лимит
                await st.check_photo_limits(user_id, message.from_user.username or "Unknown", photo_limits, consume=True)
            else:
                # Проверка 3: Balance (разовые покупки)
                balance = await st.get_user_balance_analyses(user_id)
                if balance > 0:
                    # Списываем 1 единицу баланса
                    await st.decrement_balance_analyses(user_id)
                else:
                    # Нет баланса - предлагаем купить
                    from aiogram.utils.keyboard import InlineKeyboardBuilder
                    kb = InlineKeyboardBuilder()
                    kb.button(text="📄 Купить 1 разбор (99₽)", callback_data="pay:create:one_time_analysis")
                    kb.button(text="💙 Подписка PLUS (299₽/мес)", callback_data="pay:create:plus")
                    kb.button(text="💜 Подписка PRO (590₽/мес)", callback_data="pay:create:pro")
                    kb.adjust(1)
                    await message.answer(
                        "⛔ У вас нет доступных расшифровок.\n\n"
                        "Выберите вариант оплаты:",
                        reply_markup=kb.as_markup()
                    )
                    return

    # 2. Основная логика
    if not _ANSWER_CALLBACK: return
    
    # Индикация загрузки
    await message.bot.send_chat_action(message.chat.id, "upload_photo")
    status_msg = await message.reply("🔎 Загружаю и обрабатываю изображение...")
    
    img_bytes = await _prepare_file(message, message.photo[-1].file_id, is_pdf=False)
    
    if img_bytes:
        # Обновляем статус
        await status_msg.edit_text("🔎 Анализирую снимок...")
        
        # ВЕТЕРИНАРНЫЙ ПРОМПТ ДЛЯ ФОТО
        caption = message.caption or (
            "Это изображение от владельца животного (симптом или документ). "
            "1. Если это анализы — выдели показатели, которые НЕ в норме для этого вида животного. "
            "2. Если это фото питомца — опиши, что видишь (травма, воспаление, стул) и насколько это выглядит опасно. "
            "3. НЕ ставь диагноз, но подскажи, нужен ли очный врач срочно."
        )
        
        # Определяем, это анализ или фото симптома (по caption или по умолчанию - фото симптома)
        is_analysis = "анализ" in (message.caption or "").lower() or "анализы" in (message.caption or "").lower()
        
        try:
            await _ANSWER_CALLBACK(message, caption, img_bytes, is_analysis_document=is_analysis)
        finally:
            # Удаляем статус-сообщение после обработки
            try:
                await status_msg.delete()
            except Exception as e:
                logger.error(f"Error in on_photo status cleanup: {e}")

@router.message(F.document)
async def on_document(message: Message):
    # 1. ПРОВЕРКА ТИПА ФАЙЛА
    mime = (message.document.mime_type or "").lower()
    is_image = mime.startswith("image/")
    is_pdf = mime == "application/pdf"
    
    if not (is_image or is_pdf):
        await message.reply("Я понимаю только картинки (JPG/PNG) и PDF документы.")
        return

    # 2. НОВАЯ ЛОГИКА ПРОВЕРКИ ДОСТУПА (Trial -> Подписка -> Balance)
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        # Проверка 1: Trial (первый раз бесплатно)
        is_trial = not await st.is_trial_used(user_id)
        if is_trial:
            await st.mark_trial_used(user_id)
            # Пропускаем дальше без проверок
        else:
            # Проверка 2: Активная подписка
            has_sub = await st.has_active_subscription(user_id)
            if has_sub:
                # Проверяем месячные лимиты подписки
                photo_limits = {"free": FREE_PHOTOS_PER_MONTH, "plus": PLUS_PHOTOS_PER_MONTH, "pro": PRO_PHOTOS_PER_MONTH}
                chk = await st.check_photo_limits(user_id, message.from_user.username or "Unknown", photo_limits, consume=False)
                if not chk["allowed"]:
                    await message.answer(
                        "⛔ Лимит фото/документов на этот месяц исчерпан.\n\n"
                        "Чтобы продолжить разбор снимков и анализов, подключите тариф PLUS/PRO: /buy"
                    )
                    return
                # Списываем месячный лимит
                await st.check_photo_limits(user_id, message.from_user.username or "Unknown", photo_limits, consume=True)
            else:
                # Проверка 3: Balance (разовые покупки)
                balance = await st.get_user_balance_analyses(user_id)
                if balance > 0:
                    # Списываем 1 единицу баланса
                    await st.decrement_balance_analyses(user_id)
                else:
                    # Нет баланса - предлагаем купить
                    from aiogram.utils.keyboard import InlineKeyboardBuilder
                    kb = InlineKeyboardBuilder()
                    kb.button(text="📄 Купить 1 разбор (99₽)", callback_data="pay:create:one_time_analysis")
                    kb.button(text="💙 Подписка PLUS (299₽/мес)", callback_data="pay:create:plus")
                    kb.button(text="💜 Подписка PRO (590₽/мес)", callback_data="pay:create:pro")
                    kb.adjust(1)
                    await message.answer(
                        "⛔ У вас нет доступных расшифровок.\n\n"
                        "Выберите вариант оплаты:",
                        reply_markup=kb.as_markup()
                    )
                    return

    # 3. Основная логика
    if not _ANSWER_CALLBACK: return

    # Индикация загрузки
    await message.bot.send_chat_action(message.chat.id, "upload_document")
    status_msg = await message.reply("📄 Загружаю и обрабатываю документ...")
    
    img_bytes = await _prepare_file(message, message.document.file_id, is_pdf=is_pdf)
    
    if img_bytes:
        # Обновляем статус
        await status_msg.edit_text("🔎 Анализирую документ...")
        
        caption = message.caption or (
            "Интерпретируй результаты анализов из этого ветеринарного документа. "
            "Используй систему 'Светофор' для оценки показателей: 🔴 критично, 🟡 погранично, 🟢 норма. "
            "Начни с краткого резюме, затем детальный разбор с эмодзи, и рекомендации."
        )
        
        # Документы (PDF/изображения документов) всегда считаются анализами
        is_analysis = True
        
        try:
            await _ANSWER_CALLBACK(message, caption, img_bytes, is_analysis_document=is_analysis)
        finally:
            # Удаляем статус-сообщение после обработки
            try:
                await status_msg.delete()
            except Exception as e:
                logger.error(f"Error in on_document status cleanup: {e}")
    else:
        await status_msg.edit_text("❌ Не удалось прочитать файл. Попробуйте прислать фото или скриншот.")