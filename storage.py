"""
Async Storage для Vet-bot (SQLAlchemy 2.0 + aiosqlite)
Все методы асинхронные, не блокируют Event Loop.
"""

import logging
from datetime import datetime, date, time
from pathlib import Path
from typing import Optional

from sqlalchemy import select, update, insert, func, and_, or_
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from models import Base, User, Pet, History, YooKassaPayment, Feedback

logger = logging.getLogger("VetBot.Storage")

DB_PATH = Path("bot.db")
DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"

# Глобальные объекты (инициализируются в init_db)
_engine = None
_async_session: Optional[async_sessionmaker[AsyncSession]] = None


async def init_db():
    """
    Инициализация БД: создание движка, сессий и таблиц.
    Вызывается один раз при старте бота.
    """
    global _engine, _async_session

    _engine = create_async_engine(
        DATABASE_URL,
        echo=False,  # Включить для отладки SQL-запросов
        future=True,
    )

    _async_session = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    # Создание всех таблиц
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("📂 БД готова (Async SQLAlchemy 2.0)")


def _get_session() -> AsyncSession:
    """Получить новую сессию (для использования в async context managers)"""
    if _async_session is None:
        raise RuntimeError("Storage not initialized. Call init_db() first.")
    return _async_session()


def _parse_sub_end(sub_end_date: Optional[str]) -> Optional[datetime]:
    """
    Поддерживаем оба формата:
    - 'YYYY-MM-DD' (старый) -> считаем до конца дня
    - ISO datetime (новый)  -> datetime.fromisoformat
    """
    if not sub_end_date:
        return None
    s = sub_end_date.strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except Exception:
        pass
    try:
        d = date.fromisoformat(s)
        return datetime.combine(d, time(23, 59, 59))
    except Exception:
        return None


# ===== АДМИНКА И СТАТИСТИКА =====

async def get_all_users() -> list[int]:
    """Для рассылки: возвращает список всех user_id"""
    async with _get_session() as session:
        result = await session.execute(select(User.user_id))
        return [row[0] for row in result.fetchall()]


async def get_bot_stats() -> dict:
    """Для команды /stats (расширенная статистика)"""
    today = datetime.now().strftime("%Y-%m-%d")
    this_month = datetime.now().strftime("%Y-%m")
    stats = {}

    async with _get_session() as session:
        # Пользователи
        stats["users_total"] = (await session.execute(select(func.count(User.user_id)))).scalar() or 0
        stats["users_today"] = (
            await session.execute(
                select(func.count(User.user_id)).where(User.joined_at.like(f"{today}%"))
            )
        ).scalar() or 0

        # Сообщения
        stats["msgs_total"] = (await session.execute(select(func.count(History.id)))).scalar() or 0
        stats["msgs_today"] = (
            await session.execute(
                select(func.count(History.id)).where(History.created_at.like(f"{today}%"))
            )
        ).scalar() or 0

        # Тарифы
        stats["tier_free"] = (
            await session.execute(
                select(func.count(User.user_id)).where(or_(User.tier == "free", User.tier.is_(None)))
            )
        ).scalar() or 0
        stats["tier_plus"] = (
            await session.execute(select(func.count(User.user_id)).where(User.tier == "plus"))
        ).scalar() or 0
        stats["tier_pro"] = (
            await session.execute(select(func.count(User.user_id)).where(User.tier == "pro"))
        ).scalar() or 0
        stats["paid_total"] = (
            await session.execute(select(func.count(User.user_id)).where(User.status == "paid"))
        ).scalar() or 0

        # Активные/истекшие подписки
        paid_users = await session.execute(select(User.sub_end_date).where(User.status == "paid"))
        rows = paid_users.fetchall()
        active = 0
        expired = 0
        now = datetime.now()
        for row in rows:
            end_dt = _parse_sub_end(row[0])
            if end_dt and end_dt > now:
                active += 1
            else:
                expired += 1
        stats["paid_active"] = active
        stats["paid_expired"] = expired

        # Фото/документы за месяц
        stats["photos_users_month"] = (
            await session.execute(
                select(func.count(User.user_id)).where(
                    and_(User.last_photo_month == this_month, User.photos_month > 0)
                )
            )
        ).scalar() or 0
        stats["photos_total_month"] = (
            await session.execute(
                select(func.coalesce(func.sum(User.photos_month), 0)).where(
                    User.last_photo_month == this_month
                )
            )
        ).scalar() or 0

        # Фидбек
        stats["fb_total"] = (await session.execute(select(func.count(Feedback.id)))).scalar() or 0
        stats["fb_today"] = (
            await session.execute(
                select(func.count(Feedback.id)).where(Feedback.created_at.like(f"{today}%"))
            )
        ).scalar() or 0
        stats["fb_like_total"] = (
            await session.execute(select(func.count(Feedback.id)).where(Feedback.kind == "like"))
        ).scalar() or 0
        stats["fb_dislike_total"] = (
            await session.execute(select(func.count(Feedback.id)).where(Feedback.kind == "dislike"))
        ).scalar() or 0
        stats["fb_like_today"] = (
            await session.execute(
                select(func.count(Feedback.id)).where(
                    and_(Feedback.kind == "like", Feedback.created_at.like(f"{today}%"))
                )
            )
        ).scalar() or 0
        stats["fb_dislike_today"] = (
            await session.execute(
                select(func.count(Feedback.id)).where(
                    and_(Feedback.kind == "dislike", Feedback.created_at.like(f"{today}%"))
                )
            )
        ).scalar() or 0

    return stats


# ===== ПОЛЬЗОВАТЕЛИ =====

async def register_user_if_new(user_id: int, username: str):
    """Регистрирует юзера при нажатии /start"""
    today = datetime.now().strftime("%Y-%m-%d")
    async with _get_session() as session:
        result = await session.execute(select(User).where(User.user_id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            new_user = User(
                user_id=user_id,
                username=username,
                joined_at=datetime.now().isoformat(),
                last_usage_date=today,
                daily_usage=0,
                status="free",
                tier="free",
            )
            session.add(new_user)
            await session.commit()


async def check_user_limits(
    user_id: int, username: str, limits_by_tier: dict, consume: bool = True
) -> dict:
    """Проверяет и списывает дневной лимит запросов"""
    today = datetime.now().strftime("%Y-%m-%d")
    async with _get_session() as session:
        # Создаём юзера, если его нет
        result = await session.execute(select(User).where(User.user_id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            user = User(
                user_id=user_id,
                username=username,
                joined_at=datetime.now().isoformat(),
                last_usage_date=today,
                daily_usage=0,
                status="free",
                tier="free",
                photos_month=0,
                last_photo_month=datetime.now().strftime("%Y-%m"),
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

        # Сброс лимитов
        if user.last_usage_date != today:
            user.daily_usage = 0
            user.last_usage_date = today
            await session.commit()
            await session.refresh(user)

        # Проверка админа
        if user.status == "admin":
            return {"allowed": True, "role": "admin", "tier": "pro", "limit": None, "remaining": None}

        # Проверка подписки
        now = datetime.now()
        sub_end = _parse_sub_end(user.sub_end_date)
        is_paid_active = (user.status == "paid") and sub_end and (sub_end > now)
        tier = (user.tier or "plus").strip().lower()
        if not is_paid_active:
            tier = "free"

        # Лимиты по тарифу
        limit = limits_by_tier.get(tier)
        if limit is None:
            return {
                "allowed": True,
                "role": "paid" if is_paid_active else "free",
                "tier": tier,
                "limit": None,
                "remaining": None,
            }

        # Проверка лимита
        if user.daily_usage >= int(limit):
            return {
                "allowed": False,
                "role": "paid" if is_paid_active else "free",
                "tier": tier,
                "limit": int(limit),
                "remaining": 0,
            }

        if consume:
            user.daily_usage += 1
            await session.commit()
            await session.refresh(user)
            used = user.daily_usage
        else:
            used = user.daily_usage

        remaining = int(limit) - used
        return {
            "allowed": True,
            "role": "paid" if is_paid_active else "free",
            "tier": tier,
            "limit": int(limit),
            "remaining": max(0, remaining),
        }


async def increment_usage(user_id: int):
    """Увеличивает счётчик использования (устаревший метод, используется check_user_limits с consume=True)"""
    async with _get_session() as session:
        result = await session.execute(select(User).where(User.user_id == user_id))
        user = result.scalar_one_or_none()
        if user:
            user.daily_usage += 1
            await session.commit()


async def set_user_paid(user_id: int, end_date_str: str, tier: str):
    """Активирует подписку для пользователя"""
    async with _get_session() as session:
        result = await session.execute(select(User).where(User.user_id == user_id))
        user = result.scalar_one_or_none()
        if user:
            user.status = "paid"
            user.sub_end_date = end_date_str
            user.tier = tier
            await session.commit()


async def get_user_subscription(user_id: int) -> Optional[dict]:
    """Возвращает информацию о подписке пользователя"""
    async with _get_session() as session:
        result = await session.execute(select(User).where(User.user_id == user_id))
        user = result.scalar_one_or_none()
        if user:
            return {
                "user_id": user.user_id,
                "username": user.username,
                "status": user.status,
                "tier": user.tier,
                "daily_usage": user.daily_usage,
                "last_usage_date": user.last_usage_date,
                "sub_end_date": user.sub_end_date,
            }
        return None


async def get_effective_tier(user_id: int) -> str:
    """Возвращает фактический тариф: 'pro'/'plus' если подписка активна, иначе 'free'"""
    u = await get_user_subscription(user_id)
    if not u:
        return "free"
    if u.get("status") != "paid":
        return "free"
    sub_end = _parse_sub_end(u.get("sub_end_date"))
    if not sub_end or sub_end <= datetime.now():
        return "free"
    return (u.get("tier") or "plus").strip().lower() or "plus"


async def check_photo_limits(
    user_id: int, username: str, photo_limits_by_tier: dict, consume: bool = True
) -> dict:
    """Месячный лимит фото/PDF (vision/OCR)"""
    month = datetime.now().strftime("%Y-%m")
    async with _get_session() as session:
        # Создаём юзера, если его нет
        result = await session.execute(select(User).where(User.user_id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            user = User(
                user_id=user_id,
                username=username,
                joined_at=datetime.now().isoformat(),
                last_usage_date=datetime.now().strftime("%Y-%m-%d"),
                daily_usage=0,
                status="free",
                tier="free",
                photos_month=0,
                last_photo_month=month,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

        # Сброс месячного счётчика
        if (user.last_photo_month or "") != month:
            user.photos_month = 0
            user.last_photo_month = month
            await session.commit()
            await session.refresh(user)

        # Определяем тариф
        now = datetime.now()
        sub_end = _parse_sub_end(user.sub_end_date)
        is_paid_active = (user.status == "paid") and sub_end and (sub_end > now)
        tier = (user.tier or "plus").strip().lower()
        if not is_paid_active:
            tier = "free"

        limit = photo_limits_by_tier.get(tier)
        if limit is None:
            return {"allowed": True, "tier": tier, "limit": None, "remaining": None}

        used = int(user.photos_month or 0)
        if used >= int(limit):
            return {"allowed": False, "tier": tier, "limit": int(limit), "remaining": 0}

        if consume:
            user.photos_month += 1
            await session.commit()
            await session.refresh(user)
            used += 1

        return {"allowed": True, "tier": tier, "limit": int(limit), "remaining": max(0, int(limit) - used)}


# ===== УПРАВЛЕНИЕ ПИТОМЦАМИ =====

async def create_pet(user_id: int, pet_type: str = "dog") -> int:
    """Создает пустую анкету и делает её активной"""
    async with _get_session() as session:
        new_pet = Pet(user_id=user_id, type=pet_type, updated_at=datetime.now().isoformat())
        session.add(new_pet)
        await session.flush()  # Получаем pet.id

        # Делаем активным
        result = await session.execute(select(User).where(User.user_id == user_id))
        user = result.scalar_one_or_none()
        if user:
            user.active_pet_id = new_pet.id
        await session.commit()
        return new_pet.id


async def get_active_pet(user_id: int) -> Optional[dict]:
    """Возвращает словарь с данными активного питомца"""
    async with _get_session() as session:
        result = await session.execute(select(User).where(User.user_id == user_id))
        user = result.scalar_one_or_none()
        if not user or not user.active_pet_id:
            return None

        pet_result = await session.execute(select(Pet).where(Pet.id == user.active_pet_id))
        pet = pet_result.scalar_one_or_none()
        return pet.to_dict() if pet else None


async def get_user_pets(user_id: int) -> list[dict]:
    """Список всех питомцев юзера (id, name, type)"""
    async with _get_session() as session:
        result = await session.execute(
            select(Pet.id, Pet.name, Pet.type).where(Pet.user_id == user_id)
        )
        return [{"id": row[0], "name": row[1], "type": row[2]} for row in result.fetchall()]


async def set_active_pet(user_id: int, pet_id: int):
    """Устанавливает активного питомца (с проверкой принадлежности)"""
    async with _get_session() as session:
        # Проверка, что пет принадлежит юзеру
        pet_result = await session.execute(
            select(Pet).where(and_(Pet.id == pet_id, Pet.user_id == user_id))
        )
        if pet_result.scalar_one_or_none():
            result = await session.execute(select(User).where(User.user_id == user_id))
            user = result.scalar_one_or_none()
            if user:
                user.active_pet_id = pet_id
                await session.commit()


async def update_pet_field(user_id: int, field: str, value):
    """Обновляет поле у АКТИВНОГО питомца"""
    pet = await get_active_pet(user_id)
    if not pet:
        return

    async with _get_session() as session:
        result = await session.execute(select(Pet).where(Pet.id == pet["id"]))
        pet_obj = result.scalar_one_or_none()
        if pet_obj:
            # Безопасно: field проверяется в коде хендлеров
            setattr(pet_obj, field, value)
            pet_obj.updated_at = datetime.now().isoformat()
            await session.commit()


async def delete_active_pet(user_id: int):
    """Удаляет активного питомца"""
    pet = await get_active_pet(user_id)
    if not pet:
        return

    async with _get_session() as session:
        # Убираем активного питомца у пользователя
        result = await session.execute(select(User).where(User.user_id == user_id))
        user = result.scalar_one_or_none()
        if user:
            user.active_pet_id = None

        # Удаляем питомца
        pet_result = await session.execute(select(Pet).where(Pet.id == pet["id"]))
        pet_obj = pet_result.scalar_one_or_none()
        if pet_obj:
            session.delete(pet_obj)
        await session.commit()


# ===== ИСТОРИЯ =====

async def save_entry(user_id: int, user_text: str, bot_text: str) -> int:
    """Сохраняет запись в историю, возвращает entry_id"""
    async with _get_session() as session:
        entry = History(
            user_id=user_id,
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
            user_text=user_text,
            bot_text=bot_text,
        )
        session.add(entry)
        await session.commit()
        await session.refresh(entry)
        return entry.id


async def get_last_entries(user_id: int, limit: int = 3) -> list[tuple[str, str, str]]:
    """Возвращает последние записи истории: [(created_at, user_text, bot_text), ...]"""
    async with _get_session() as session:
        result = await session.execute(
            select(History.created_at, History.user_text, History.bot_text)
            .where(History.user_id == user_id)
            .order_by(History.id.desc())
            .limit(limit)
        )
        return [(row[0], row[1], row[2]) for row in result.fetchall()]


# ===== РАССЫЛКА НАПОМИНАНИЙ =====

async def check_reminders_today() -> list[tuple[int, str]]:
    """Возвращает список (user_id, text) кому надо напомнить"""
    today = datetime.now().strftime("%Y-%m-%d")
    notifications = []

    async with _get_session() as session:
        # Вакцинация
        result = await session.execute(
            select(Pet.user_id, Pet.name).where(Pet.next_vaccine_date == today)
        )
        for row in result.fetchall():
            notifications.append(
                (row[0], f"💉 **Напоминание:** Сегодня у питомца **{row[1]}** плановая вакцинация!")
            )

        # Клещи
        result = await session.execute(
            select(Pet.user_id, Pet.name).where(Pet.next_tick_date == today)
        )
        for row in result.fetchall():
            notifications.append(
                (row[0], f"🕷 **Напоминание:** Пора обработать **{row[1]}** от клещей и блох!")
            )

    return notifications


# ===== ПЛАТЕЖИ И ФИДБЕК =====

async def mark_yookassa_payment_processed(
    payment_id: str, user_id: int, tier: str, created_at: str
) -> bool:
    """
    Сохраняет payment_id, чтобы не активировать подписку повторно.
    Возвращает True, если это новый платеж (вставка прошла), иначе False.
    """
    async with _get_session() as session:
        # Проверяем, существует ли уже
        result = await session.execute(
            select(YooKassaPayment).where(YooKassaPayment.payment_id == payment_id)
        )
        if result.scalar_one_or_none():
            return False

        # Вставляем новый
        payment = YooKassaPayment(
            payment_id=payment_id, user_id=user_id, tier=tier, created_at=created_at
        )
        session.add(payment)
        try:
            await session.commit()
            return True
        except Exception:
            await session.rollback()
            return False


async def save_feedback(
    user_id: int, kind: str, source: str = "text", entry_id: Optional[int] = None
) -> None:
    """Сохраняет фидбек (👍/👎)"""
    kind = "like" if str(kind).lower() == "like" else "dislike"
    async with _get_session() as session:
        # Используем INSERT OR REPLACE через merge
        feedback = Feedback(
            user_id=user_id,
            entry_id=entry_id,
            kind=kind,
            source=source,
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        )
        # Проверяем существование
        result = await session.execute(
            select(Feedback).where(
                and_(Feedback.user_id == user_id, Feedback.entry_id == entry_id)
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            existing.kind = kind
            existing.source = source
            existing.created_at = datetime.now().strftime("%Y-%m-%d %H:%M")
        else:
            session.add(feedback)
        await session.commit()
