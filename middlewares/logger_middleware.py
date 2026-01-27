# middlewares/logger_middleware.py — ЛОГИРОВАНИЕ ДЕЙСТВИЙ ПОЛЬЗОВАТЕЛЕЙ

import logging
from datetime import datetime
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, Update

import storage as st

logger = logging.getLogger("VetBot.UserAction")


def _parse_sub_end(s: str | None) -> datetime | None:
    """Парсит дату окончания подписки"""
    if not s:
        return None
    try:
        if "T" in s:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        d = datetime.strptime(s, "%Y-%m-%d")
        return datetime.combine(d.date(), datetime.max.time().replace(microsecond=0))
    except Exception:
        return None


def _get_user_tag(user_data: dict | None) -> str:
    """Определяет тег пользователя для логов"""
    if not user_data:
        return "[❓ UNKNOWN]"
    
    # Проверяем активную подписку
    sub_end_date = user_data.get("sub_end_date")
    if sub_end_date:
        sub_end = _parse_sub_end(sub_end_date)
        if sub_end and sub_end > datetime.now():
            return "[💎 SUB]"
    
    # Проверяем баланс анализов
    balance = user_data.get("balance_analyses", 0)
    if balance and balance > 0:
        return "[💰 1-TIME]"
    
    # По умолчанию FREE
    return "[🆓 FREE]"


def _get_action(event: Update) -> str:
    """Определяет действие пользователя"""
    if event.message:
        msg = event.message
        if msg.text:
            text = msg.text[:20] + "..." if len(msg.text) > 20 else msg.text
            return f'📝 Text: "{text}"'
        elif msg.photo:
            return "📸 Photo"
        elif msg.document:
            return "📄 Document"
        elif msg.video:
            return "🎥 Video"
        elif msg.voice:
            return "🎤 Voice"
        else:
            return "📨 Message (other)"
    
    if event.callback_query:
        cq = event.callback_query
        data = cq.data or ""
        # Обрезаем длинные callback_data
        if len(data) > 30:
            data = data[:30] + "..."
        return f'🔘 Button: "{data}"'
    
    return "❓ Unknown action"


class LoggingMiddleware(BaseMiddleware):
    """Middleware для логирования действий пользователей с информацией о тарифе"""
    
    async def __call__(
        self,
        handler: Callable[[Update, dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: dict[str, Any]
    ) -> Any:
        """Обрабатывает апдейт и логирует действие пользователя"""
        
        # Получаем user_id из события
        user_id = None
        if event.message and event.message.from_user:
            user_id = event.message.from_user.id
        elif event.callback_query and event.callback_query.from_user:
            user_id = event.callback_query.from_user.id
        
        if not user_id:
            # Если не удалось определить user_id, пропускаем логирование
            return await handler(event, data)
        
        # Получаем данные пользователя из базы
        user_data = await st.get_user_subscription(user_id)
        if user_data:
            # Добавляем баланс анализов в словарь (создаем копию, чтобы не изменять оригинал)
            balance = await st.get_user_balance_analyses(user_id)
            user_data = {**user_data, "balance_analyses": balance}
        
        # Определяем тег и действие
        tag = _get_user_tag(user_data)
        action = _get_action(event)
        
        # Логируем
        logger.info(f"👤 [ID:{user_id} | {tag}] -> {action}")
        
        # Вызываем следующий обработчик
        return await handler(event, data)
