# handlers/medcard.py — МУЛЬТИ-ПИТОМЕЦ (FIXED)

from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters import Command
import storage as st
from keyboards.main_kb import main_reply_kb

router = Router()
# Словарь для ожидания ввода: user_id -> поле (например 'name')
WAITING_FIELD: dict[int, str] = {}

# --- ГЛАВНОЕ МЕНЮ ---

@router.message(Command("medcard"))
async def cmd_medcard(message: Message):
    await show_medcard_menu(message)

@router.callback_query(lambda c: c.data == "main:medcard")
async def cb_medcard(cq: CallbackQuery):
    await show_medcard_menu(cq.message)
    await cq.answer()

@router.callback_query(lambda c: c.data == "medcard:back")
async def cb_medcard_back(cq: CallbackQuery):
    """Возврат в главное меню из медкарты"""
    await cq.answer("Возврат в главное меню")
    await cq.message.answer(
        "🏠 Вы вернулись в главное меню.",
        reply_markup=main_reply_kb()
    )

async def show_medcard_menu(message: Message):
    user_id = message.chat.id
    active_pet = await st.get_active_pet(user_id)
    
    kb = InlineKeyboardBuilder()
    
    if active_pet:
        text = render_pet_card(active_pet)
        kb.button(text="✍️ Изменить", callback_data="pet:edit_menu")
        kb.button(text="🔄 Сменить питомца", callback_data="pet:switch_list")
        kb.button(text="❌ Удалить", callback_data="pet:delete_confirm")
    else:
        pets = await st.get_user_pets(user_id)
        if not pets:
            text = "🐾 У вас нет активных питомцев. Давайте создадим!"
            kb.button(text="➕ Создать питомца", callback_data="pet:create_new")
        else:
            text = "🐾 Выберите питомца:"
            for p in pets:
                name = p['name'] if p['name'] else "Без имени"
                kb.button(text=f"{name} ({p['type']})", callback_data=f"pet:select:{p['id']}")
            kb.button(text="➕ Добавить нового", callback_data="pet:create_new")

    kb.button(text="⬅️ В меню", callback_data="medcard:back")
    kb.adjust(1)
    
    try: await message.edit_text(text, reply_markup=kb.as_markup())
    except: await message.answer(text, reply_markup=kb.as_markup())

def render_pet_card(pet: dict) -> str:
    icon = "🐶" if pet['type'] == 'dog' else "🐱"
    name = pet['name'] or "⌛ (Нет имени)"
    return (
        f"{icon} **{name}**\n"
        f"Вид: {pet['type']}\n"
        f"Порода: {pet['breed'] or '—'}\n"
        f"Возраст: {pet['age'] or '—'}\n"
        f"Вес: **{pet['weight'] or '—'} кг**\n\n"
        f"Хроника: {pet['chronic'] or 'Нет'}"
    )

# --- СОЗДАНИЕ И ВЫБОР ---

@router.callback_query(lambda c: c.data == "pet:switch_list")
async def pet_switch_list(cq: CallbackQuery):
    pets = await st.get_user_pets(cq.from_user.id)
    kb = InlineKeyboardBuilder()
    for p in pets:
        name = p['name'] if p['name'] else "???"
        kb.button(text=f"{name}", callback_data=f"pet:select:{p['id']}")
    kb.button(text="➕ Новый", callback_data="pet:create_new")
    kb.adjust(1)
    await cq.message.edit_text("Кого выбрать?", reply_markup=kb.as_markup())

@router.callback_query(lambda c: c.data and c.data.startswith("pet:select:"))
async def pet_select(cq: CallbackQuery):
    pet_id = int(cq.data.split(":")[2])
    await st.set_active_pet(cq.from_user.id, pet_id)
    await show_medcard_menu(cq.message)

@router.callback_query(lambda c: c.data == "pet:create_new")
async def pet_create_new(cq: CallbackQuery):
    kb = InlineKeyboardBuilder()
    kb.button(text="🐶 Собака", callback_data="pet:init:dog")
    kb.button(text="🐱 Кошка", callback_data="pet:init:cat")
    await cq.message.edit_text("Кто это?", reply_markup=kb.as_markup())

@router.callback_query(lambda c: c.data and c.data.startswith("pet:init:"))
async def pet_init(cq: CallbackQuery):
    ptype = cq.data.split(":")[2]
    await st.create_pet(cq.from_user.id, ptype)
    
    # ВАЖНО: Ставим флаг, что ждем имя
    WAITING_FIELD[cq.from_user.id] = "name"
    
    await cq.message.edit_text(f"✅ Питомец создан!\n\n**Напишите в чат его кличку:**")

# --- РЕДАКТИРОВАНИЕ ---

@router.callback_query(lambda c: c.data == "pet:edit_menu")
async def pet_edit_menu(cq: CallbackQuery):
    kb = InlineKeyboardBuilder()
    kb.button(text="Имя", callback_data="pedit:name")
    kb.button(text="Порода", callback_data="pedit:breed")
    kb.button(text="Возраст", callback_data="pedit:age")
    kb.button(text="Вес", callback_data="pedit:weight")
    kb.button(text="Хроника", callback_data="pedit:chronic")
    kb.button(text="Назад", callback_data="main:medcard")
    kb.adjust(2)
    await cq.message.edit_text("Что меняем?", reply_markup=kb.as_markup())

@router.callback_query(lambda c: c.data and c.data.startswith("pedit:"))
async def pet_ask_field(cq: CallbackQuery):
    field = cq.data.split(":")[1]
    WAITING_FIELD[cq.from_user.id] = field
    msgs = {
        "name": "Введите кличку:",
        "weight": "Введите вес (числом, например 5.5):",
        "age": "Введите возраст:"
    }
    await cq.message.edit_text(msgs.get(field, "Введите значение:"))

# --- ЛОВУШКА ДЛЯ ТЕКСТА (Самое важное место) ---
@router.message(F.text, lambda m: m.from_user.id in WAITING_FIELD)
async def process_pet_input(message: Message):
    user_id = message.from_user.id
    field = WAITING_FIELD.pop(user_id) # Забираем ожидание
    val = message.text.strip()

    if field == "weight":
        try: val = float(val.replace(",", "."))
        except: 
            await message.reply("⚠️ Вес должен быть числом!")
            return

    await st.update_pet_field(user_id, field, val)
    
    active = await st.get_active_pet(user_id)
    kb = InlineKeyboardBuilder()
    kb.button(text="Продолжить", callback_data="pet:edit_menu")
    kb.button(text="Ок, в меню", callback_data="medcard:back")
    kb.adjust(2)
    
    await message.answer(f"✅ Сохранено!\n\n{render_pet_card(active)}", reply_markup=kb.as_markup())

# --- УДАЛЕНИЕ ---
@router.callback_query(lambda c: c.data == "pet:delete_confirm")
async def delete_confirm(cq: CallbackQuery):
    kb = InlineKeyboardBuilder()
    kb.button(text="🗑 Удалить", callback_data="pet:delete_yes")
    kb.button(text="Отмена", callback_data="main:medcard")
    await cq.message.edit_text("Точно удалить?", reply_markup=kb.as_markup())

@router.callback_query(lambda c: c.data == "pet:delete_yes")
async def delete_yes(cq: CallbackQuery):
    await st.delete_active_pet(cq.from_user.id)
    await cq.message.edit_text("Удалено.", reply_markup=InlineKeyboardBuilder().button(text="Меню", callback_data="main:medcard").as_markup())