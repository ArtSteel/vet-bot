# handlers/promo.py — ПРОМОКОДЫ И РЕФЕРАЛЫ

import os
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command, CommandObject
from dotenv import load_dotenv
import storage as st

load_dotenv()
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()]

router = Router()


@router.message(Command("promo"))
async def cmd_promo(message: Message, command: CommandObject):
    """Активация промокода: /promo CODE"""
    user_id = message.from_user.id
    
    if not command.args:
        await message.answer(
            "💎 **Активация промокода**\n\n"
            "Использование: `/promo КОД`\n\n"
            "Пример: `/promo CORGI_LOVE`",
            parse_mode="Markdown"
        )
        return
    
    code = command.args.strip()
    result = await st.activate_promo_code(user_id, code)
    
    await message.answer(result["message"], parse_mode="Markdown")


@router.message(Command("create_promo"))
async def cmd_create_promo(message: Message, command: CommandObject):
    """Создание промокода (только для админов): /create_promo CODE TYPE VALUE USES [EXPIRY]"""
    user_id = message.from_user.id
    
    if user_id not in ADMIN_IDS:
        await message.answer("❌ Доступ запрещен.")
        return
    
    if not command.args:
        await message.answer(
            "🔧 **Создание промокода**\n\n"
            "Формат: `/create_promo CODE TYPE VALUE USES [EXPIRY]`\n\n"
            "Параметры:\n"
            "• `CODE` — код промокода (например, CORGI_LOVE)\n"
            "• `TYPE` — тип: `subscription_days` или `balance_add`\n"
            "• `VALUE` — значение (дни подписки или количество анализов)\n"
            "• `USES` — максимальное количество использований (0 = бесконечно)\n"
            "• `EXPIRY` — дата окончания (опционально, формат: YYYY-MM-DD)\n\n"
            "Примеры:\n"
            "• `/create_promo CORGI_LOVE subscription_days 7 100`\n"
            "• `/create_promo BONUS_10 balance_add 10 0`\n"
            "• `/create_promo TEST subscription_days 30 50 2025-12-31`",
            parse_mode="Markdown"
        )
        return
    
    args = command.args.strip().split()
    if len(args) < 4:
        await message.answer("❌ Недостаточно параметров. Нужно минимум: CODE TYPE VALUE USES")
        return
    
    code = args[0].upper()
    promo_type = args[1].lower()
    try:
        value = int(args[2])
        max_uses = int(args[3])
    except ValueError:
        await message.answer("❌ VALUE и USES должны быть числами.")
        return
    
    expiry_date = None
    if len(args) >= 5:
        expiry_date = args[4]
    
    if promo_type not in ["subscription_days", "balance_add"]:
        await message.answer("❌ TYPE должен быть `subscription_days` или `balance_add`")
        return
    
    result = await st.create_promo_code(code, promo_type, value, max_uses, expiry_date)
    await message.answer(result["message"], parse_mode="Markdown")
