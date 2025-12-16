from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def main_reply_kb() -> ReplyKeyboardMarkup:
    """
    "Модная" reply-клавиатура в стиле скрина (крупные кнопки внизу).
    """
    return ReplyKeyboardMarkup(
        resize_keyboard=True,
        one_time_keyboard=False,
        keyboard=[
            [KeyboardButton(text="🩺 Задать вопрос"), KeyboardButton(text="📸 Анализ фото/документа")],
            [KeyboardButton(text="🧾 История"), KeyboardButton(text="👤 Мой тариф")],
            [KeyboardButton(text="🩺 Медкарта"), KeyboardButton(text="💎 Подписка")],
            [KeyboardButton(text="❓ Что умеет бот")],
        ],
        input_field_placeholder="Опишите симптомы питомца или отправьте фото…",
    )


