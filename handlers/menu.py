# handlers/menu.py — Только меню (без старта)

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from keyboards.main_kb import main_reply_kb

router = Router()

MAIN_MENU_TEXT = (
    "🏠 **Главное меню**\n\n"
    "Здесь вы можете управлять своими данными и подпиской."
)

def main_menu_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="🩺 Медкарта", callback_data="main:medcard")
    kb.button(text="💎 Подписка", callback_data="buy") # Ведет на хендлер оплаты
    kb.button(text="❓ Помощь", callback_data="main:help")
    kb.adjust(1)
    return kb

# УБРАЛИ @router.message(Command("start")), чтобы не мешал core.py

@router.message(Command("menu"))
async def cmd_menu(message: Message):
    await message.answer(MAIN_MENU_TEXT, reply_markup=main_reply_kb(), parse_mode="Markdown")

@router.callback_query(lambda c: c.data == "main:help")
async def cb_help(cq: CallbackQuery):
    # Текст помощи берем из core.py, здесь просто перенаправление или краткая справка
    # Но чтобы не дублировать, направим пользователя на команду /help
    await cq.message.edit_text(
        "Нажмите /help чтобы прочитать подробную инструкцию.",
        reply_markup=main_menu_kb().as_markup()
    )
    await cq.answer()