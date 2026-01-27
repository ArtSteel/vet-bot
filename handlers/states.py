# handlers/states.py — FSM состояния

from aiogram.fsm.state import State, StatesGroup


class PromoState(StatesGroup):
    """Состояния для работы с промокодами"""
    waiting_for_code = State()
