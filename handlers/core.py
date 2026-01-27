# handlers/core.py — КОРРЕКТНАЯ ПОМОЩЬ

import os
import asyncio
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, Command, CommandObject
from dotenv import load_dotenv
import storage as st
from keyboards.main_kb import main_reply_kb

router = Router()

load_dotenv()
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()]
FREE_DAILY_LIMIT = int(os.getenv("FREE_DAILY_LIMIT", "5"))
FREE_DAILY_TEXT_LIMIT = int(os.getenv("FREE_DAILY_TEXT_LIMIT", "3"))
PLUS_DAILY_LIMIT = int(os.getenv("PLUS_DAILY_LIMIT", os.getenv("STANDARD_DAILY_LIMIT", "50")))
PRO_DAILY_LIMIT_RAW = os.getenv("PRO_DAILY_LIMIT", "")
PRO_DAILY_LIMIT = None if not PRO_DAILY_LIMIT_RAW.strip() else int(PRO_DAILY_LIMIT_RAW)
FREE_PHOTOS_PER_MONTH = int(os.getenv("FREE_PHOTOS_PER_MONTH", "1"))
PLUS_PHOTOS_PER_MONTH = int(os.getenv("PLUS_PHOTOS_PER_MONTH", "10"))
PRO_PHOTOS_PER_MONTH_RAW = os.getenv("PRO_PHOTOS_PER_MONTH", "20")
PRO_PHOTOS_PER_MONTH = None if not PRO_PHOTOS_PER_MONTH_RAW.strip() else int(PRO_PHOTOS_PER_MONTH_RAW)

WELCOME_TEXT = (
    "👋 **Привет! Я — ВетСоветник AI.**\n"
    "Твой карманный помощник по здоровью питомцев.\n\n"
    "🐾 **ЧЕМ Я МОГУ ПОМОЧЬ?**\n"
    "• 🚑 **Симптомы:** Оценю срочность и дам первую помощь.\n"
    "• 💊 **Лекарства:** Рассчитаю дозировку на вес.\n"
    "• 🔬 **Анализы:** Расшифрую фото бланков (в тарифе PRO).\n\n"
    "👇 **Начните с создания анкеты питомца:**"
)

HELP_TEXT = (
    "🤖 **ЧТО Я УМЕЮ?**\n\n"
    "Я — твой карманный ветеринарный ассистент. Моя цель — перевести сложные медицинские термины на человеческий язык.\n\n"
    "📸 **1. Расшифровка анализов (Хит!)**\n"
    "Пришли мне фото результатов крови, УЗИ или PDF из клиники.\n"
    "Я проанализирую их по системе «Светофор»:\n"
    "🔴 Критично (срочно к врачу!)\n"
    "🟡 Обратить внимание\n"
    "🟢 В норме\n"
    "🎁 Первая расшифровка — БЕСПЛАТНО.\n\n"
    "💬 **2. Консультации 24/7**\n"
    "Отвечаю на вопросы о здоровье, питании и уходе.\n"
    "• Использую контекст (помню, что мы обсуждали 5 минут назад).\n"
    "• В платных тарифах подключается более мощная модель (Qwen-Max) для глубокого анализа.\n\n"
    "📋 **3. Медкарта (/medcard)**\n"
    "Заполни профиль питомца! Зная вид, возраст и вес, я смогу точнее рассчитывать дозировки и давать советы.\n\n"
    "💎 **Тарифы**\n"
    "• Разовый разбор анализов — 99₽ (идеально, если нужно срочно).\n"
    "• Подписка PLUS/PRO — для тех, кто хочет держать здоровье под контролем постоянно.\n\n"
    "⚠️ **Важно:** Я — искусственный интеллект. Я помогаю разобраться в ситуации, но не заменяю очный визит к врачу в экстренных случаях."
)

@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject):
    user = message.from_user
    bot = message.bot
    
    # Обработка deep-linking аргументов
    referrer_id = None
    promo_code = None
    
    if command.args:
        args = command.args.strip()
        # Проверяем реферальную ссылку: ref_USER_ID
        if args.startswith("ref_"):
            try:
                referrer_id = int(args.replace("ref_", ""))
                # Проверяем, что реферал существует и не является самим пользователем
                if referrer_id == user.id:
                    referrer_id = None
                else:
                    # Проверяем существование реферала
                    referrer_user = await st.get_user_subscription(referrer_id)
                    if not referrer_user:
                        referrer_id = None
            except ValueError:
                referrer_id = None
        # Проверяем промокод: promo_CODE
        elif args.startswith("promo_"):
            promo_code = args.replace("promo_", "").strip()
    
    # Регистрируем пользователя (если новый) с рефералом
    is_new_user = await st.register_user_if_new(user.id, user.username or "Unknown", referrer_id)
    
    # Если новый пользователь и есть реферал, отправляем уведомление пригласившему
    if is_new_user and referrer_id:
        try:
            referrer_name = user.username or f"Пользователь {user.id}"
            await bot.send_message(
                referrer_id,
                f"🎉 **По вашей ссылке пришел друг!**\n\n"
                f"Вам начислен бонус: +1 анализ.\n"
                f"Вашему другу тоже начислен бонус: +1 анализ.",
                parse_mode="Markdown"
            )
        except Exception as e:
            # Если не удалось отправить уведомление (пользователь заблокировал бота и т.д.), игнорируем
            pass
    
    # Если указан промокод, пытаемся его активировать
    if promo_code:
        result = await st.activate_promo_code(user.id, promo_code)
        await message.answer(result["message"], parse_mode="Markdown")
    
    await message.answer(WELCOME_TEXT, reply_markup=main_reply_kb(), parse_mode="Markdown")


@router.message(Command("me"))
async def cmd_me(message: Message):
    user_id = message.from_user.id
    if user_id in ADMIN_IDS:
        await message.answer("👑 Вы админ. Тариф: **PRO** (без ограничений).")
        return

    limits_by_tier = {"free": FREE_DAILY_LIMIT, "plus": PLUS_DAILY_LIMIT, "pro": PRO_DAILY_LIMIT}
    info = await st.check_user_limits(user_id, message.from_user.username or "Unknown", limits_by_tier, consume=False)
    sub = (await st.get_user_subscription(user_id)) or {}

    tier = info.get("tier", "free")
    limit = info.get("limit")
    remaining = info.get("remaining")
    until = sub.get("sub_end_date") if sub.get("status") == "paid" else None

    text = f"👤 Ваш тариф: **{tier.upper()}**\n"
    if limit is None:
        text += "Лимит: **безлимит**\n"
    else:
        text += f"Лимит в день: **{limit}** | Осталось сегодня: **{remaining}**\n"

    photo_limits = {"free": FREE_PHOTOS_PER_MONTH, "plus": PLUS_PHOTOS_PER_MONTH, "pro": PRO_PHOTOS_PER_MONTH}
    pinfo = await st.check_photo_limits(user_id, message.from_user.username or "Unknown", photo_limits, consume=False)
    if pinfo.get("limit") is None:
        text += "Фото/документы в месяц: **безлимит**\n"
    else:
        text += f"Фото/документы в месяц: **{pinfo.get('limit')}** | Осталось: **{pinfo.get('remaining')}**\n"
    if until:
        text += f"Подписка до: **{str(until)[:10]}**\n"
    text += "\nОформить/обновить: /buy"
    await message.answer(text, parse_mode="Markdown")



# Ловим и команду, и кнопку
@router.message(Command("help"))
@router.callback_query(lambda c: c.data == "main:help")
async def cmd_help(event):
    if isinstance(event, Message):
        await event.answer(HELP_TEXT, parse_mode="Markdown", reply_markup=main_reply_kb())
    else:
        # Если нажали кнопку "Помощь" — редактируем сообщение на текст помощи
        # Или отправляем новым, если редактировать нечего
        await event.message.answer(HELP_TEXT, parse_mode="Markdown", reply_markup=main_reply_kb())
        await event.answer()


# ===== Reply-кнопки (как на скрине) =====
@router.message(F.text == "💎 Подписка")
async def btn_buy(message: Message):
    from handlers.pay import cmd_buy as pay_cmd_buy

    await pay_cmd_buy(message)




@router.message(F.text == "🐕 Медкарта")
async def btn_medcard(message: Message):
    from handlers.medcard import show_medcard_menu

    await show_medcard_menu(message)


@router.message(F.text == "🎁 Бонусы / Друзья")
async def btn_bonuses(message: Message):
    """Показывает профиль пользователя с балансом и реферальной ссылкой"""
    user_id = message.from_user.id
    
    # Получаем информацию о пользователе
    user_info = await st.get_user_subscription(user_id)
    if not user_info:
        await message.answer("❌ Пользователь не найден.", reply_markup=main_reply_kb())
        return
    
    # Получаем баланс анализов
    balance = await st.get_user_balance_analyses(user_id)
    
    # Получаем реферальную ссылку
    referral_code = await st.get_referral_link(user_id)
    bot_username = (await message.bot.get_me()).username
    referral_link = f"https://t.me/{bot_username}?start={referral_code}"
    
    # Формируем сообщение
    text = (
        f"👤 **Твой профиль**\n\n"
        f"🆔 ID: `{user_id}`\n"
        f"💎 Баланс анализов: **{balance}**\n\n"
        f"🤝 **Твоя реферальная ссылка:**\n"
        f"`{referral_link}`\n\n"
        f"💡 Пригласи друга по этой ссылке — вы оба получите +1 анализ!"
    )
    
    await message.answer(text, parse_mode="Markdown", reply_markup=main_reply_kb())


@router.message(F.text == "❓ Что умеет бот")
async def btn_help(message: Message):
    await message.answer(HELP_TEXT, parse_mode="Markdown", reply_markup=main_reply_kb())


@router.message(F.text == "📸 Анализ фото/документа")
async def btn_vision_hint(message: Message):
    await message.answer(
        "📸 Пришлите фото/скрин или PDF анализов/симптомов.\n"
        "К фото можно добавить подпись: что за питомец и что беспокоит.",
        reply_markup=main_reply_kb(),
    )


@router.message(F.text == "🩺 Задать вопрос")
async def btn_question_hint(message: Message):
    await message.answer(
        "Напишите, что случилось:\n"
        "- симптомы\n"
        "- как давно\n"
        "- что менялось\n"
        "- аппетит/температура/стул\n\n"
        "Я отвечу и подскажу, когда срочно к врачу.",
        reply_markup=main_reply_kb(),
    )

# --- АДМИНКА ---
@router.message(Command("stats"))
async def cmd_stats(message: Message):
    if message.from_user.id not in ADMIN_IDS: return
    s = await st.get_bot_stats()

    text = (
        "📊 **Статистика Vet‑bot**\n\n"
        f"👥 **Пользователи:**\n"
        f"- всего: **{s['users_total']}**\n"
        f"- новых сегодня: **{s['users_today']}**\n\n"
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
        f"- сегодня: **{s['fb_today']}** (👍 {s['fb_like_today']} / 👎 {s['fb_dislike_today']})\n"
    )
    await message.answer(text, parse_mode="Markdown")

@router.message(Command("post"))
async def cmd_broadcast(message: Message, command: CommandObject):
    if message.from_user.id not in ADMIN_IDS: return
    if not command.args: return
    users = await st.get_all_users()
    for uid in users:
        try: await message.bot.send_message(uid, command.args, parse_mode="Markdown")
        except: pass
    await message.answer("Рассылка завершена.")