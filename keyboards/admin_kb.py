# keyboards/admin_kb.py — АДМИН-КЛАВИАТУРА

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def admin_keyboard() -> ReplyKeyboardMarkup:
    """
    Админ-клавиатура для управления ботом.
    Доступна только администраторам.
    """
    return ReplyKeyboardMarkup(
        resize_keyboard=True,
        one_time_keyboard=False,
        keyboard=[
            [KeyboardButton(text="📊 Общая статистика"), KeyboardButton(text="💰 Финансы")],
            [KeyboardButton(text="🎟 Создать промокод"), KeyboardButton(text="📢 Рассылка")],
            [KeyboardButton(text="👥 Поиск юзера"), KeyboardButton(text="❌ Выйти")],
        ],
        input_field_placeholder="Админ-панель…",
    )
