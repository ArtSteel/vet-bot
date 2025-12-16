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
    "🆘 **СПРАВКА ПО БОТУ**\n\n"
    "1️⃣ **Анкета питомца (/medcard)**\n"
    "Заполните её обязательно! Без веса и вида животного я не смогу рассчитать дозировку лекарств.\n\n"
    "2️⃣ **Как общаться?**\n"
    "• Пишите подробно: *«Собака 5 лет, рвота пеной, вялая»*.\n"
    "• Если я задаю вопросы — **отвечайте на них**.\n"
    "• Я помню контекст диалога, но иногда могу уточнять детали.\n\n"
    "3️⃣ **Фото и Документы**\n"
    "В тарифе PRO вы можете присылать фото высыпаний, травм или PDF-файлы с анализами."
)

@router.message(CommandStart())
async def cmd_start(message: Message):
    user = message.from_user
    st.register_user_if_new(user.id, user.username or "Unknown")
    await message.answer(WELCOME_TEXT, reply_markup=main_reply_kb(), parse_mode="Markdown")


@router.message(Command("me"))
async def cmd_me(message: Message):
    user_id = message.from_user.id
    if user_id in ADMIN_IDS:
        await message.answer("👑 Вы админ. Тариф: **PRO** (без ограничений).")
        return

    limits_by_tier = {"free": FREE_DAILY_LIMIT, "plus": PLUS_DAILY_LIMIT, "pro": PRO_DAILY_LIMIT}
    info = st.check_user_limits(user_id, message.from_user.username or "Unknown", limits_by_tier, consume=False)
    sub = st.get_user_subscription(user_id) or {}

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
    pinfo = st.check_photo_limits(user_id, message.from_user.username or "Unknown", photo_limits, consume=False)
    if pinfo.get("limit") is None:
        text += "Фото/документы в месяц: **безлимит**\n"
    else:
        text += f"Фото/документы в месяц: **{pinfo.get('limit')}** | Осталось: **{pinfo.get('remaining')}**\n"
    if until:
        text += f"Подписка до: **{str(until)[:10]}**\n"
    text += "\nОформить/обновить: /buy"
    await message.answer(text, parse_mode="Markdown")


@router.message(Command("history"))
async def cmd_history(message: Message):
    items = st.get_last_entries(message.from_user.id, limit=5)
    if not items:
        await message.answer("Пока нет истории. Напишите вопрос 👇", reply_markup=main_reply_kb())
        return

    lines = ["🧾 **Последние диалоги:**\n"]
    for created_at, u, b in reversed(items):
        u_short = (u or "").strip()
        b_short = (b or "").strip()
        if len(u_short) > 120:
            u_short = u_short[:117] + "..."
        if len(b_short) > 160:
            b_short = b_short[:157] + "..."
        lines.append(f"**{created_at}**\n- Вы: {u_short}\n- Бот: {b_short}\n")

    await message.answer("\n".join(lines), parse_mode="Markdown", reply_markup=main_reply_kb())

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


@router.message(F.text == "👤 Мой тариф")
async def btn_me(message: Message):
    await cmd_me(message)


@router.message(F.text == "🩺 Медкарта")
async def btn_medcard(message: Message):
    from handlers.medcard import show_medcard_menu

    await show_medcard_menu(message)


@router.message(F.text == "🧾 История")
async def btn_history(message: Message):
    await cmd_history(message)


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
    s = st.get_bot_stats()

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
    users = st.get_all_users()
    for uid in users:
        try: await message.bot.send_message(uid, command.args, parse_mode="Markdown")
        except: pass
    await message.answer("Рассылка завершена.")