# handlers/states.py — FSM состояния

from aiogram.fsm.state import State, StatesGroup


class PromoState(StatesGroup):
    """Состояния для работы с промокодами"""
    waiting_for_code = State()


class AdminPromoState(StatesGroup):
    """Состояния для создания промокода админом"""
    waiting_for_code = State()
    waiting_for_type = State()
    waiting_for_value = State()
    waiting_for_uses = State()
    waiting_for_expiry = State()


class AdminBroadcastState(StatesGroup):
    """Состояния для рассылки админом"""
    waiting_for_content = State()
    waiting_for_confirm = State()


class AdminSearchState(StatesGroup):
    """Состояния для поиска пользователя"""
    searching_user = State()
