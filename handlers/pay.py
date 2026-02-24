# handlers/pay.py — Реальная подписка через YooKassa (polling без вебхуков)

from datetime import datetime, timedelta
import os
import asyncio
import logging

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters import Command
from dotenv import load_dotenv
from yookassa import Configuration, Payment

import storage as st

router = Router()
logger = logging.getLogger("VetBot.Pay")

load_dotenv()
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY") or os.getenv("YOOKASSA_TOKEN")
YOOKASSA_RETURN_URL = os.getenv("YOOKASSA_RETURN_URL", "https://t.me")

if YOOKASSA_SHOP_ID and YOOKASSA_SECRET_KEY:
    Configuration.account_id = YOOKASSA_SHOP_ID
    Configuration.secret_key = YOOKASSA_SECRET_KEY
    logger.info("💳 YOOKASSA: конфигурация загружена, shop_id=%s", YOOKASSA_SHOP_ID)
else:
    logger.warning("💳 YOOKASSA: нет SHOP_ID/SECRET_KEY, оплата не будет работать.")

TEXT_OFFER = (
    "💎 **Монетизация Vet‑bot**\n\n"
    "📄 **Разовый разбор (99 ₽)**\n"
    "• 1 расшифровка анализов/фото\n"
    "• Не сгорает, используйте когда нужно\n\n"
    "💙 **Подписка PLUS (299 ₽ / мес)**\n"
    "• больше вопросов в день\n"
    "• до 10 фото/документов в месяц\n\n"
    "💜 **Подписка PRO (590 ₽ / мес)**\n"
    "• всё из PLUS\n"
    "• до 20 фото/документов в месяц\n\n"
    "Нажмите кнопку ниже — откроется безопасная страница оплаты YooKassa."
)


def pay_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="📄 Разовый разбор (99₽)", callback_data="pay:create:one_time_analysis")
    kb.button(text="💙 Подписка PLUS (299₽/мес)", callback_data="pay:create:plus")
    kb.button(text="💜 Подписка PRO (590₽/мес)", callback_data="pay:create:pro")
    kb.adjust(1)
    return kb


@router.message(Command("buy"))
@router.message(F.text == "💎 Подписка")
@router.callback_query(lambda c: c.data == "buy")
async def cmd_buy(event):
    if isinstance(event, Message):
        await event.answer(TEXT_OFFER, reply_markup=pay_kb().as_markup(), parse_mode="Markdown")
    else:
        await event.message.answer(TEXT_OFFER, reply_markup=pay_kb().as_markup(), parse_mode="Markdown")
        await event.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("pay:create:"))
async def process_real_pay(cq: CallbackQuery):
    if not (YOOKASSA_SHOP_ID and YOOKASSA_SECRET_KEY):
        await cq.answer("Оплата временно недоступна. Попробуйте позже.", show_alert=True)
        return

    plan = cq.data.split(":")[2]  # 'one_time_analysis', 'plus' или 'pro'
    user_id = cq.from_user.id

    if plan == "one_time_analysis":
        amount = 99
        tier = "one_time_analysis"
        plan_name = "Разовый разбор 📄"
        description = f"Разовая расшифровка анализов для пользователя Telegram {user_id}"
        item_description = "Разовый разбор анализов/фото"
    elif plan == "plus":
        amount = 299
        tier = "plus"
        plan_name = "PLUS 💙"
        description = f"Подписка PLUS на 30 дней для пользователя Telegram {user_id}"
        item_description = f"Подписка PLUS на 30 дней"
    else:  # pro
        amount = 590
        tier = "pro"
        plan_name = "PRO 💜"
        description = f"Подписка PRO на 30 дней для пользователя Telegram {user_id}"
        item_description = f"Подписка PRO на 30 дней"

    payment_data = {
        "amount": {"value": f"{amount}.00", "currency": "RUB"},
        "confirmation": {"type": "redirect", "return_url": YOOKASSA_RETURN_URL},
        "capture": True,
        "description": description[:128],
        "metadata": {"user_id": user_id, "tier": tier, "plan": plan},
        # Минимальный чек (ФЗ‑54). В проде лучше подставлять email/телефон пользователя.
        "receipt": {
            "customer": {"email": f"user{user_id}@example.com"},
            "items": [
                {
                    "description": item_description[:128],
                    "quantity": "1.0",
                    "amount": {"value": f"{amount}.00", "currency": "RUB"},
                    "vat_code": 1,
                }
            ],
        },
    }

    try:
        payment = await asyncio.to_thread(Payment.create, payment_data)
    except Exception as e:
        logger.error("YOOKASSA create error: %r", e)
        await cq.answer("Ошибка при создании платежа. Попробуйте позже.", show_alert=True)
        return

    pay_url = payment.confirmation.confirmation_url

    if plan == "one_time_analysis":
        text = (
            f"💳 *Оплата {plan_name}*\n\n"
            f"Сумма: *{amount} ₽*\n\n"
            "Нажмите кнопку ниже, чтобы перейти на страницу оплаты.\n"
            "После успешной оплаты вам будет начислена 1 расшифровка анализов."
        )
    else:
        text = (
            f"💳 *Оплата тарифа {plan_name}*\n\n"
            f"Сумма: *{amount} ₽* за 30 дней.\n\n"
            "Нажмите кнопку ниже, чтобы перейти на страницу оплаты.\n"
            "После успешной оплаты доступ подключится автоматически в течение нескольких минут."
        )

    kb = InlineKeyboardBuilder()
    kb.button(text="Оплатить через YooKassa", url=pay_url)
    kb.adjust(1)

    await cq.message.edit_text(text, parse_mode="Markdown", reply_markup=kb.as_markup())
    await cq.answer()


async def yookassa_polling_loop(bot: Bot, poll_interval: int = 60):
    """
    Опрашивает YooKassa и активирует подписки по успешным платежам.
    Это упрощает запуск на VPS: не нужны вебхуки/HTTPS.
    """
    if not (YOOKASSA_SHOP_ID and YOOKASSA_SECRET_KEY):
        logger.warning("💳 YOOKASSA: нет ключей, polling отключён.")
        return

    logger.info("💳 YOOKASSA: polling каждые %s сек.", poll_interval)

    while True:
        try:
            payments = await asyncio.to_thread(Payment.list, {"status": "succeeded", "limit": 50})
            for payment in getattr(payments, "items", []):
                metadata = getattr(payment, "metadata", None) or {}
                user_id = metadata.get("user_id")
                tier = metadata.get("tier") or metadata.get("plan")
                payment_id = getattr(payment, "id", None)
                created_at = getattr(payment, "created_at", "")

                if not user_id or not tier or not payment_id:
                    continue

                is_new = await st.mark_yookassa_payment_processed(str(payment_id), int(user_id), str(tier), str(created_at))
                if not is_new:
                    continue

                # Обработка разовой покупки
                if str(tier) == "one_time_analysis":
                    await st.increment_balance_analyses(int(user_id), 1)
                    try:
                        text = (
                            f"🎉 *Покупка успешна!*\n\n"
                            f"Вам начислена *1 расшифровка* анализов.\n"
                            f"Используйте её, отправив фото или документ с анализами.\n\n"
                            "Спасибо за поддержку!"
                        )
                        await bot.send_message(int(user_id), text, parse_mode="Markdown")
                    except Exception as e_send:
                        logger.warning("Не удалось отправить уведомление: %r", e_send)
                    continue

                # Обработка подписки
                end_dt = (datetime.now() + timedelta(days=30)).replace(microsecond=0)
                await st.set_user_paid(int(user_id), end_dt.isoformat(), str(tier))

                plan_name = "PRO 💜" if str(tier) == "pro" else "PLUS 💙"
                try:
                    text = (
                        f"🎉 *Подписка активирована!*\n\n"
                        f"Тариф: *{plan_name}*\n"
                        f"Доступ активен до: *{end_dt.strftime('%Y-%m-%d')}*\n\n"
                        "Спасибо за поддержку — это помогает развивать бота."
                    )
                    await bot.send_message(int(user_id), text, parse_mode="Markdown")
                except Exception as e_send:
                    logger.warning("Не удалось отправить уведомление: %r", e_send)

            await asyncio.sleep(poll_interval)
        except Exception as e:
            logger.error("💳 YOOKASSA polling error: %r", e)
            await asyncio.sleep(poll_interval)