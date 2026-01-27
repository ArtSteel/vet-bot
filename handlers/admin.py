# handlers/admin.py — АДМИН-ПАНЕЛЬ

import os
from aiogram import Router, F, Bot
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from dotenv import load_dotenv
import storage as st
from handlers.states import AdminPromoState, AdminBroadcastState, AdminSearchState
from keyboards.admin_kb import admin_keyboard
from keyboards.main_kb import main_reply_kb

load_dotenv()
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()]

router = Router()


# === ФИЛЬТР ДЛЯ ПРОВЕРКИ АДМИНА ===
def is_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь админом"""
    return user_id in ADMIN_IDS


# === КОМАНДА /ADMIN ===
@router.message(Command("admin"))
async def cmd_admin(message: Message):
    """Открывает админ-панель"""
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        await message.answer("❌ Доступ запрещен.")
        return
    
    await message.answer(
        "🔐 **Админ-панель**\n\n"
        "Выберите действие:",
        reply_markup=admin_keyboard(),
        parse_mode="Markdown"
    )


# === ОБЩАЯ СТАТИСТИКА ===
@router.message(F.text == "📊 Общая статистика")
async def btn_stats(message: Message):
    """Показывает расширенную статистику"""
    if not is_admin(message.from_user.id):
        return
    
    s = await st.get_bot_stats()
    user_stats = await st.get_detailed_user_stats()
    
    text = (
        "📊 **Общая статистика**\n\n"
        f"👥 **Пользователи:**\n"
        f"- всего: **{s['users_total']}**\n"
        f"- новых сегодня: **{s['users_today']}**\n"
        f"- новых за неделю: **{user_stats['users_week']}**\n"
        f"- новых за месяц: **{user_stats['users_month']}**\n"
        f"- активных за 24ч: **{user_stats['active_24h']}**\n\n"
        f"💬 **Сообщения:**\n"
        f"- всего: **{s['msgs_total']}**\n"
        f"- сегодня: **{s['msgs_today']}**\n\n"
        f"💎 **Тарифы (в базе):**\n"
        f"- free: **{s['tier_free']}**\n"
        f"- plus: **{s['tier_plus']}**\n"
        f"- pro: **{s['tier_pro']}**\n\n"
        f"💳 **Подписки:**\n"
        f"- paid всего: **{s['paid_total']}**\n"
        f"- активных: **{s['paid_active']}**\n"
        f"- истекших: **{s['paid_expired']}**\n\n"
        f"📸 **Фото/документы (текущий месяц):**\n"
        f"- пользователей отправляли: **{s['photos_users_month']}**\n"
        f"- всего файлов: **{s['photos_total_month']}**\n\n"
        f"👍👎 **Фидбек:**\n"
        f"- всего: **{s['fb_total']}** (👍 {s['fb_like_total']} / 👎 {s['fb_dislike_total']})\n"
        f"- сегодня: **{s['fb_today']}** (👍 {s['fb_like_today']} / 👎 {s['fb_dislike_today']})"
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=admin_keyboard())


# === ФИНАНСЫ ===
@router.message(F.text == "💰 Финансы")
async def btn_finances(message: Message):
    """Показывает финансовую статистику"""
    if not is_admin(message.from_user.id):
        return
    
    revenue = await st.get_revenue_stats()
    
    text = (
        "💰 **Выручка:**\n\n"
        f"📅 Сегодня: **{revenue['today_revenue']} ₽** ({revenue['today_transactions']} транзакций)\n"
        f"📊 Всего: **{revenue['total_revenue']} ₽** ({revenue['total_transactions']} транзакций)\n"
        f"💵 Средний чек: **{revenue['average_check']} ₽**"
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=admin_keyboard())


# === СОЗДАНИЕ ПРОМОКОДА (FSM) ===
@router.message(F.text == "🎟 Создать промокод")
async def btn_create_promo_start(message: Message, state: FSMContext):
    """Начинает процесс создания промокода"""
    if not is_admin(message.from_user.id):
        return
    
    cancel_kb = ReplyKeyboardMarkup(
        resize_keyboard=True,
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        one_time_keyboard=True
    )
    
    await message.answer(
        "🎟 **Создание промокода**\n\n"
        "✍️ Введите код промокода (например: `CORGI_LOVE`):",
        parse_mode="Markdown",
        reply_markup=cancel_kb
    )
    await state.set_state(AdminPromoState.waiting_for_code)


@router.message(AdminPromoState.waiting_for_code, F.text == "❌ Отмена")
async def cancel_admin_promo(message: Message, state: FSMContext):
    """Отмена создания промокода"""
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    await state.clear()
    await message.answer("❌ Создание промокода отменено.", reply_markup=admin_keyboard())


@router.message(AdminPromoState.waiting_for_code, F.text)
async def process_promo_code_input(message: Message, state: FSMContext):
    """Обработка кода промокода"""
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    code = message.text.strip().upper()
    await state.update_data(code=code)
    
    cancel_kb = ReplyKeyboardMarkup(
        resize_keyboard=True,
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        one_time_keyboard=True
    )
    
    await message.answer(
        "📝 Выберите тип промокода:\n\n"
        "• `subscription_days` — дни подписки\n"
        "• `balance_add` — добавление анализов",
        parse_mode="Markdown",
        reply_markup=cancel_kb
    )
    await state.set_state(AdminPromoState.waiting_for_type)


@router.message(AdminPromoState.waiting_for_type, F.text == "❌ Отмена")
async def cancel_admin_promo_type(message: Message, state: FSMContext):
    """Отмена на этапе выбора типа"""
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    await state.clear()
    await message.answer("❌ Создание промокода отменено.", reply_markup=admin_keyboard())


@router.message(AdminPromoState.waiting_for_type, F.text)
async def process_promo_type_input(message: Message, state: FSMContext):
    """Обработка типа промокода"""
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    promo_type = message.text.strip().lower()
    
    if promo_type not in ["subscription_days", "balance_add"]:
        await message.answer("❌ Неверный тип. Введите `subscription_days` или `balance_add`")
        return
    
    await state.update_data(type=promo_type)
    
    cancel_kb = ReplyKeyboardMarkup(
        resize_keyboard=True,
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        one_time_keyboard=True
    )
    
    type_name = "дней подписки" if promo_type == "subscription_days" else "анализов"
    await message.answer(
        f"💎 Введите значение (количество {type_name}):",
        reply_markup=cancel_kb
    )
    await state.set_state(AdminPromoState.waiting_for_value)


@router.message(AdminPromoState.waiting_for_value, F.text == "❌ Отмена")
async def cancel_admin_promo_value(message: Message, state: FSMContext):
    """Отмена на этапе ввода значения"""
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    await state.clear()
    await message.answer("❌ Создание промокода отменено.", reply_markup=admin_keyboard())


@router.message(AdminPromoState.waiting_for_value, F.text)
async def process_promo_value_input(message: Message, state: FSMContext):
    """Обработка значения промокода"""
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    try:
        value = int(message.text.strip())
        await state.update_data(value=value)
        
        cancel_kb = ReplyKeyboardMarkup(
            resize_keyboard=True,
            keyboard=[[KeyboardButton(text="❌ Отмена")]],
            one_time_keyboard=True
        )
        
        await message.answer(
            "🔢 Введите максимальное количество использований (0 = бесконечно):",
            reply_markup=cancel_kb
        )
        await state.set_state(AdminPromoState.waiting_for_uses)
    except ValueError:
        await message.answer("❌ Введите число.")


@router.message(AdminPromoState.waiting_for_uses, F.text == "❌ Отмена")
async def cancel_admin_promo_uses(message: Message, state: FSMContext):
    """Отмена на этапе ввода использований"""
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    await state.clear()
    await message.answer("❌ Создание промокода отменено.", reply_markup=admin_keyboard())


@router.message(AdminPromoState.waiting_for_uses, F.text)
async def process_promo_uses_input(message: Message, state: FSMContext):
    """Обработка количества использований и создание промокода"""
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    try:
        max_uses = int(message.text.strip())
        data = await state.get_data()
        
        code = data.get("code")
        promo_type = data.get("type")
        value = data.get("value")
        
        if not all([code, promo_type, value]):
            await message.answer("❌ Ошибка: данные неполные. Начните заново.")
            await state.clear()
            return
        
        # Создаем промокод
        result = await st.create_promo_code(code, promo_type, value, max_uses, None)
        
        await state.clear()
        await message.answer(result["message"], parse_mode="Markdown", reply_markup=admin_keyboard())
    except ValueError:
        await message.answer("❌ Введите число.")


# === РАССЫЛКА (FSM) ===
@router.message(F.text == "📢 Рассылка")
async def btn_broadcast_start(message: Message, state: FSMContext):
    """Начинает процесс рассылки"""
    if not is_admin(message.from_user.id):
        return
    
    cancel_kb = ReplyKeyboardMarkup(
        resize_keyboard=True,
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        one_time_keyboard=True
    )
    
    await message.answer(
        "📢 **Рассылка**\n\n"
        "✍️ Введите текст сообщения или отправьте фото с подписью:",
        parse_mode="Markdown",
        reply_markup=cancel_kb
    )
    await state.set_state(AdminBroadcastState.waiting_for_content)


@router.message(AdminBroadcastState.waiting_for_content, F.text == "❌ Отмена")
async def cancel_broadcast(message: Message, state: FSMContext):
    """Отмена рассылки"""
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    await state.clear()
    await message.answer("❌ Рассылка отменена.", reply_markup=admin_keyboard())


@router.message(AdminBroadcastState.waiting_for_content, F.text)
async def process_broadcast_text(message: Message, state: FSMContext):
    """Обработка текста для рассылки"""
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    content = message.text
    await state.update_data(content=content, has_photo=False)
    
    confirm_kb = ReplyKeyboardMarkup(
        resize_keyboard=True,
        keyboard=[
            [KeyboardButton(text="✅ Отправить"), KeyboardButton(text="❌ Отмена")]
        ],
        one_time_keyboard=True
    )
    
    users_count = len(await st.get_all_users())
    await message.answer(
        f"📋 **Превью рассылки:**\n\n{content}\n\n"
        f"👥 Будет отправлено **{users_count}** пользователям.\n\n"
        f"Подтвердите отправку:",
        parse_mode="Markdown",
        reply_markup=confirm_kb
    )
    await state.set_state(AdminBroadcastState.waiting_for_confirm)


@router.message(AdminBroadcastState.waiting_for_content, F.photo)
async def process_broadcast_photo(message: Message, state: FSMContext):
    """Обработка фото для рассылки"""
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    photo = message.photo[-1]  # Берем фото наибольшего размера
    caption = message.caption or ""
    
    await state.update_data(
        photo_file_id=photo.file_id,
        content=caption,
        has_photo=True
    )
    
    confirm_kb = ReplyKeyboardMarkup(
        resize_keyboard=True,
        keyboard=[
            [KeyboardButton(text="✅ Отправить"), KeyboardButton(text="❌ Отмена")]
        ],
        one_time_keyboard=True
    )
    
    users_count = len(await st.get_all_users())
    await message.answer(
        f"📋 **Превью рассылки:**\n\n"
        f"📸 Фото + текст: {caption or '(без текста)'}\n\n"
        f"👥 Будет отправлено **{users_count}** пользователям.\n\n"
        f"Подтвердите отправку:",
        parse_mode="Markdown",
        reply_markup=confirm_kb
    )
    await state.set_state(AdminBroadcastState.waiting_for_confirm)


@router.message(AdminBroadcastState.waiting_for_confirm, F.text == "❌ Отмена")
async def cancel_broadcast_confirm(message: Message, state: FSMContext):
    """Отмена рассылки на этапе подтверждения"""
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    await state.clear()
    await message.answer("❌ Рассылка отменена.", reply_markup=admin_keyboard())


@router.message(AdminBroadcastState.waiting_for_confirm, F.text == "✅ Отправить")
async def confirm_broadcast(message: Message, state: FSMContext, bot: Bot):
    """Подтверждение и отправка рассылки"""
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    data = await state.get_data()
    content = data.get("content", "")
    has_photo = data.get("has_photo", False)
    photo_file_id = data.get("photo_file_id")
    
    users = await st.get_all_users()
    sent = 0
    failed = 0
    
    await message.answer("📤 Начинаю рассылку...", reply_markup=admin_keyboard())
    
    for user_id in users:
        try:
            if has_photo and photo_file_id:
                await bot.send_photo(user_id, photo_file_id, caption=content, parse_mode="Markdown")
            else:
                await bot.send_message(user_id, content, parse_mode="Markdown")
            sent += 1
        except Exception:
            failed += 1
    
    await state.clear()
    await message.answer(
        f"✅ **Рассылка завершена!**\n\n"
        f"✅ Отправлено: **{sent}**\n"
        f"❌ Ошибок: **{failed}**",
        parse_mode="Markdown",
        reply_markup=admin_keyboard()
    )


# === ПОИСК ЮЗЕРА ===
@router.message(F.text == "👥 Поиск юзера")
async def btn_search_user(message: Message, state: FSMContext):
    """Начинает поиск пользователя"""
    if not is_admin(message.from_user.id):
        return
    
    cancel_kb = ReplyKeyboardMarkup(
        resize_keyboard=True,
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        one_time_keyboard=True
    )
    
    await message.answer(
        "👥 **Поиск пользователя**\n\n"
        "✍️ Введите ID пользователя:",
        parse_mode="Markdown",
        reply_markup=cancel_kb
    )
    await state.set_state(AdminSearchState.searching_user)


@router.message(AdminSearchState.searching_user, F.text == "❌ Отмена")
async def cancel_search(message: Message, state: FSMContext):
    """Отмена поиска"""
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    await state.clear()
    await message.answer("❌ Поиск отменен.", reply_markup=admin_keyboard())


@router.message(AdminSearchState.searching_user, F.text)
async def process_user_search(message: Message, state: FSMContext):
    """Обработка поиска пользователя"""
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    try:
        user_id = int(message.text.strip())
        user_info = await st.get_user_subscription(user_id)
        
        if not user_info:
            await message.answer("❌ Пользователь не найден.", reply_markup=admin_keyboard())
            await state.clear()
            return
        
        balance = await st.get_user_balance_analyses(user_id)
        
        text = (
            f"👤 **Пользователь #{user_id}**\n\n"
            f"📝 Username: `{user_info.get('username', 'N/A')}`\n"
            f"💎 Тариф: **{user_info.get('tier', 'free').upper()}**\n"
            f"📊 Статус: **{user_info.get('status', 'free')}**\n"
            f"💵 Баланс анализов: **{balance}**\n"
        )
        
        if user_info.get('sub_end_date'):
            text += f"📅 Подписка до: **{str(user_info['sub_end_date'])[:10]}**\n"
        
        await message.answer(text, parse_mode="Markdown", reply_markup=admin_keyboard())
        await state.clear()
    except ValueError:
        await message.answer("❌ Введите числовой ID.")


# === ВЫХОД ИЗ АДМИНКИ ===
@router.message(F.text == "❌ Выйти")
async def btn_exit_admin(message: Message):
    """Выход из админ-панели"""
    if not is_admin(message.from_user.id):
        return
    
    await message.answer(
        "✅ Вы вышли из админ-панели.",
        reply_markup=main_reply_kb()
    )
