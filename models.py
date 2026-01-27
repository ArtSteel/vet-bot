"""
ORM Models для Vet-bot (SQLAlchemy 2.0 Async)
Готово к миграции на PostgreSQL без изменений кода.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, Float, Text, DateTime, func, UniqueConstraint, BigInteger, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Базовый класс для всех моделей"""
    pass


class User(Base):
    """Модель пользователя"""
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="free")  # 'free', 'paid', 'admin'
    tier: Mapped[str] = mapped_column(String, default="free")  # 'free', 'plus', 'pro'
    active_pet_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    daily_usage: Mapped[int] = mapped_column(Integer, default=0)
    last_usage_date: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # YYYY-MM-DD
    photos_month: Mapped[int] = mapped_column(Integer, default=0)
    last_photo_month: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # YYYY-MM
    sub_end_date: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # ISO datetime или YYYY-MM-DD
    joined_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # ISO datetime
    balance_analyses: Mapped[int] = mapped_column(Integer, default=0)  # Количество доступных разовых расшифровок
    is_trial_used: Mapped[bool] = mapped_column(Integer, default=0)  # 0 = не использован, 1 = использован (SQLite boolean)
    last_one_time_purchase: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # ISO datetime последней разовой покупки
    referrer_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)  # ID пользователя, который пригласил

    def to_dict(self) -> dict:
        """Преобразует объект в словарь (для обратной совместимости)"""
        return {
            "user_id": self.user_id,
            "username": self.username,
            "status": self.status,
            "tier": self.tier,
            "active_pet_id": self.active_pet_id,
            "daily_usage": self.daily_usage,
            "last_usage_date": self.last_usage_date,
            "photos_month": self.photos_month,
            "last_photo_month": self.last_photo_month,
            "sub_end_date": self.sub_end_date,
            "joined_at": self.joined_at,
            "balance_analyses": self.balance_analyses,
            "is_trial_used": bool(self.is_trial_used),
            "last_one_time_purchase": self.last_one_time_purchase,
            "referrer_id": self.referrer_id,
        }


class Pet(Base):
    """Модель питомца"""
    __tablename__ = "pets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    type: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # 'dog', 'cat'
    breed: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    age: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    weight: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    chronic: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Хронические болезни
    allergies: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    meds: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Текущие лекарства
    next_vaccine_date: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # YYYY-MM-DD
    next_tick_date: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # YYYY-MM-DD
    updated_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # ISO datetime

    def to_dict(self) -> dict:
        """Преобразует объект в словарь (для обратной совместимости)"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "type": self.type,
            "breed": self.breed,
            "age": self.age,
            "weight": self.weight,
            "chronic": self.chronic,
            "allergies": self.allergies,
            "meds": self.meds,
            "next_vaccine_date": self.next_vaccine_date,
            "next_tick_date": self.next_tick_date,
            "updated_at": self.updated_at,
        }


class History(Base):
    """Модель истории сообщений"""
    __tablename__ = "history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)  # YYYY-MM-DD HH:MM
    user_text: Mapped[str] = mapped_column(Text, nullable=False)
    bot_text: Mapped[str] = mapped_column(Text, nullable=False)


class YooKassaPayment(Base):
    """Модель платежей YooKassa (защита от повторной активации)"""
    __tablename__ = "yookassa_payments"

    payment_id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    tier: Mapped[str] = mapped_column(String, nullable=False)  # 'plus', 'pro'
    created_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class Feedback(Base):
    """Модель фидбека (👍/👎)"""
    __tablename__ = "feedback"
    __table_args__ = (
        UniqueConstraint("user_id", "entry_id", name="uq_user_entry"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    entry_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Ссылка на history.id
    kind: Mapped[str] = mapped_column(String, nullable=False)  # 'like', 'dislike'
    source: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # 'text', 'vision'
    created_at: Mapped[str] = mapped_column(String, nullable=False)  # YYYY-MM-DD HH:MM


class PromoCode(Base):
    """Модель промокода"""
    __tablename__ = "promo_codes"
    __table_args__ = (
        UniqueConstraint("code", name="uq_promo_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String, nullable=False, unique=True)  # Уникальный код промокода
    type: Mapped[str] = mapped_column(String, nullable=False)  # 'subscription_days' или 'balance_add'
    value: Mapped[int] = mapped_column(Integer, nullable=False)  # Значение (дни подписки или единицы баланса)
    max_uses: Mapped[int] = mapped_column(Integer, default=0)  # 0 = бесконечно
    current_uses: Mapped[int] = mapped_column(Integer, default=0)  # Текущее количество использований
    expiry_date: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # ISO datetime или YYYY-MM-DD
    created_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # ISO datetime


class PromoUsage(Base):
    """Модель использования промокода пользователем"""
    __tablename__ = "promo_usage"
    __table_args__ = (
        UniqueConstraint("user_id", "promo_code_id", name="uq_user_promo"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    promo_code_id: Mapped[int] = mapped_column(Integer, nullable=False)
    used_at: Mapped[str] = mapped_column(String, nullable=False)  # ISO datetime
