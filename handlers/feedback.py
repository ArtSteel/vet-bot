from aiogram import Router, F
from aiogram.types import CallbackQuery
import logging

import storage as st

router = Router()
logger = logging.getLogger("VetBot.Feedback")


@router.callback_query(F.data.startswith("fb:"))
async def cb_feedback(cq: CallbackQuery):
    # format: fb:<like|dislike>:<source>:<entry_id>
    parts = (cq.data or "").split(":")
    if len(parts) < 4:
        await cq.answer()
        return

    _, kind, source, entry_id_raw = parts[0], parts[1], parts[2], parts[3]
    try:
        entry_id = int(entry_id_raw)
    except Exception:
        entry_id = None

    await st.save_feedback(cq.from_user.id, kind=kind, source=source, entry_id=entry_id)

    # Убираем клавиатуру, чтобы не кликали бесконечно
    try:
        await cq.message.edit_reply_markup(reply_markup=None)
    except Exception as e:
        logger.error(f"Error in cb_feedback: {e}")

    if kind == "like":
        await cq.answer("Спасибо! 👍", show_alert=False)
    else:
        await cq.answer("Принял. 👎", show_alert=False)


