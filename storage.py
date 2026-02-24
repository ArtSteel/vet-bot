"""
Async Storage для Vet-bot (SQLAlchemy 2.0)
Поддерживает SQLite (aiosqlite) и PostgreSQL (asyncpg)
Все методы асинхронные, не блокируют Event Loop.
"""

import logging
import os
from datetime import datetime, date, time, timedelta
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from sqlalchemy import select, update, insert, func, and_, or_
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from models import Base, User, Pet, History, YooKassaPayment, Feedback, PromoCode, PromoUsage
import config

# Загружаем переменные окружения
load_dotenv()

logger = logging.getLogger("VetBot.Storage")

# Автоматическое определение БД
def _get_database_url() -> str:
    """
    Определяет, какую БД использовать:
    - Если указан DATABASE_URL -> используем его
    - Если указаны параметры PostgreSQL -> формируем URL для PostgreSQL
    - Иначе -> используем SQLite (fallback)
    """
    # Приоритет 1: параметры PostgreSQL
    pg_user = config.POSTGRES_USER
    pg_password = config.POSTGRES_PASSWORD
    pg_db = config.POSTGRES_DB
    pg_host = config.POSTGRES_HOST
    pg_port = config.POSTGRES_PORT

    if pg_user and pg_password and pg_db:
        pg_url = f"postgresql+asyncpg://{pg_user}:{pg_password}@{pg_host}:{pg_port}/{pg_db}"
        logger.info(f"🐘 Используется PostgreSQL: {pg_host}:{pg_port}/{pg_db}")
        return pg_url

    # Приоритет 2: полный DATABASE_URL
    database_url = config.DATABASE_URL
    if database_url:
        if database_url.startswith("postgresql://"):
            database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif not database_url.startswith(("postgresql+asyncpg://", "sqlite+aiosqlite://")):
            database_url = f"postgresql+asyncpg://{database_url}"
        logger.info("🔗 Используется DATABASE_URL из .env")
        return database_url

    # Fallback на SQLite
    db_path = Path("bot.db")
    sqlite_url = f"sqlite+aiosqlite:///{db_path}"
    logger.info(f"💾 Используется SQLite: {db_path}")
    return sqlite_url

DATABASE_URL = _get_database_url()

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
        
        # Миграция: добавление новых колонок для монетизации (если их нет)
        if "postgresql" in DATABASE_URL:
            from sqlalchemy import text
            try:
                # Проверяем существующие колонки
                check_sql = """
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'users' 
                    AND column_name IN ('balance_analyses', 'is_trial_used', 'last_one_time_purchase', 'referrer_id')
                """
                result = await conn.execute(text(check_sql))
                existing_columns = {row[0] for row in result.fetchall()}
                
                if 'balance_analyses' not in existing_columns:
                    await conn.execute(text("ALTER TABLE users ADD COLUMN balance_analyses INTEGER DEFAULT 0"))
                    logger.info("✅ Миграция: добавлена колонка balance_analyses")
                
                if 'is_trial_used' not in existing_columns:
                    await conn.execute(text("ALTER TABLE users ADD COLUMN is_trial_used INTEGER DEFAULT 0"))
                    logger.info("✅ Миграция: добавлена колонка is_trial_used")
                
                if 'last_one_time_purchase' not in existing_columns:
                    await conn.execute(text("ALTER TABLE users ADD COLUMN last_one_time_purchase VARCHAR"))
                    logger.info("✅ Миграция: добавлена колонка last_one_time_purchase")
                
                # Миграция для рефералов
                if 'referrer_id' not in existing_columns:
                    await conn.execute(text("ALTER TABLE users ADD COLUMN referrer_id BIGINT"))
                    logger.info("✅ Миграция: добавлена колонка referrer_id")
            except Exception as e:
                logger.warning(f"⚠️ Ошибка при миграции колонок (возможно, они уже существуют): {e}")

    db_type = "PostgreSQL" if "postgresql" in DATABASE_URL else "SQLite"
    logger.info(f"📂 БД готова ({db_type} + Async SQLAlchemy 2.0)")


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


async def get_revenue_stats() -> dict:
    """
    Финансовая статистика: выручка из платежей YooKassa.
    Использует фиксированные цены для расчета.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    stats = {
        "total_revenue": 0,
        "today_revenue": 0,
        "average_check": 0,
        "total_transactions": 0,
        "today_transactions": 0
    }
    
    # Цены по тарифам
    PRICES = {
        "one_time_analysis": 99,
        "plus": 299,
        "pro": 590
    }
    
    async with _get_session() as session:
        # Получаем все платежи как объекты модели
        result = await session.execute(select(YooKassaPayment))
        payments = result.scalars().all()
        
        total_revenue = 0
        today_revenue = 0
        total_count = 0
        today_count = 0
        
        for payment in payments:
            tier = payment.tier
            price = PRICES.get(tier, 0)
            
            if price > 0:
                total_revenue += price
                total_count += 1
                
                # Проверяем, был ли платеж сегодня
                if payment.created_at and payment.created_at.startswith(today):
                    today_revenue += price
                    today_count += 1
        
        stats["total_revenue"] = total_revenue
        stats["today_revenue"] = today_revenue
        stats["total_transactions"] = total_count
        stats["today_transactions"] = today_count
        stats["average_check"] = round(total_revenue / total_count, 2) if total_count > 0 else 0
    
    return stats


async def get_detailed_user_stats() -> dict:
    """Детальная статистика по пользователям"""
    today = datetime.now().strftime("%Y-%m-%d")
    now = datetime.now()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)
    day_ago = now - timedelta(hours=24)
    
    stats = {
        "users_total": 0,
        "users_today": 0,
        "users_week": 0,
        "users_month": 0,
        "active_24h": 0
    }
    
    async with _get_session() as session:
        # Общее количество пользователей
        stats["users_total"] = (await session.execute(select(func.count(User.user_id)))).scalar() or 0
        
        # Новые пользователи
        stats["users_today"] = (
            await session.execute(
                select(func.count(User.user_id)).where(User.joined_at.like(f"{today}%"))
            )
        ).scalar() or 0
        
        # За неделю (используем строковое сравнение для совместимости)
        week_str = week_ago.strftime("%Y-%m-%d")
        # Для SQLite и PostgreSQL используем строковое сравнение
        stats["users_week"] = (
            await session.execute(
                select(func.count(User.user_id)).where(
                    User.joined_at >= week_str
                )
            )
        ).scalar() or 0
        
        # За месяц
        month_str = month_ago.strftime("%Y-%m-%d")
        stats["users_month"] = (
            await session.execute(
                select(func.count(User.user_id)).where(
                    User.joined_at >= month_str
                )
            )
        ).scalar() or 0
        
        # Активные за последние 24 часа (те, кто отправлял сообщения)
        day_str = day_ago.strftime("%Y-%m-%d")
        stats["active_24h"] = (
            await session.execute(
                select(func.count(func.distinct(History.user_id))).where(
                    History.created_at >= day_str
                )
            )
        ).scalar() or 0
    
    return stats


# ===== ПОЛЬЗОВАТЕЛИ =====

async def register_user_if_new(user_id: int, username: str, referrer_id: Optional[int] = None) -> bool:
    """
    Регистрирует юзера при нажатии /start.
    Возвращает True если пользователь был новым, False если уже существовал.
    """
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
                referrer_id=referrer_id,
            )
            session.add(new_user)
            await session.commit()
            await session.refresh(new_user)
            
            # Если есть реферал, начисляем бонусы (в отдельной транзакции)
            if referrer_id:
                await _process_referral_bonus(new_user_id, referrer_id)
            
            return True
        return False


async def _process_referral_bonus(new_user_id: int, referrer_id: int):
    """Обрабатывает бонусы за реферала: начисляет +1 анализ пригласившему и новичку"""
    async with _get_session() as session:
        try:
            # Начисляем бонус пригласившему
            referrer_result = await session.execute(select(User).where(User.user_id == referrer_id))
            referrer = referrer_result.scalar_one_or_none()
            if referrer:
                referrer.balance_analyses = (referrer.balance_analyses or 0) + 1
                await session.commit()
            
            # Начисляем бонус новичку
            new_user_result = await session.execute(select(User).where(User.user_id == new_user_id))
            new_user = new_user_result.scalar_one_or_none()
            if new_user:
                new_user.balance_analyses = (new_user.balance_analyses or 0) + 1
                await session.commit()
        except Exception as e:
            logger.error(f"Ошибка при начислении реферальных бонусов: {e}")


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


async def get_user_balance_analyses(user_id: int) -> int:
    """Возвращает баланс разовых расшифровок пользователя"""
    async with _get_session() as session:
        result = await session.execute(select(User.balance_analyses).where(User.user_id == user_id))
        balance = result.scalar_one_or_none()
        return balance if balance is not None else 0


async def increment_balance_analyses(user_id: int, amount: int = 1):
    """Увеличивает баланс разовых расшифровок и обновляет дату последней покупки"""
    async with _get_session() as session:
        result = await session.execute(select(User).where(User.user_id == user_id))
        user = result.scalar_one_or_none()
        if user:
            user.balance_analyses = (user.balance_analyses or 0) + amount
            user.last_one_time_purchase = datetime.now().isoformat()
            await session.commit()


async def decrement_balance_analyses(user_id: int) -> bool:
    """Уменьшает баланс на 1. Возвращает True если баланс был > 0, иначе False"""
    async with _get_session() as session:
        result = await session.execute(select(User).where(User.user_id == user_id))
        user = result.scalar_one_or_none()
        if user:
            if (user.balance_analyses or 0) > 0:
                user.balance_analyses = user.balance_analyses - 1
                await session.commit()
                return True
        return False


async def is_trial_used(user_id: int) -> bool:
    """Проверяет, использован ли trial для первого анализа"""
    async with _get_session() as session:
        result = await session.execute(select(User.is_trial_used).where(User.user_id == user_id))
        is_used = result.scalar_one_or_none()
        return bool(is_used) if is_used is not None else False


async def mark_trial_used(user_id: int):
    """Помечает trial как использованный"""
    async with _get_session() as session:
        result = await session.execute(select(User).where(User.user_id == user_id))
        user = result.scalar_one_or_none()
        if user:
            user.is_trial_used = 1
            await session.commit()


async def has_active_subscription(user_id: int) -> bool:
    """Проверяет, есть ли активная подписка"""
    async with _get_session() as session:
        result = await session.execute(select(User).where(User.user_id == user_id))
        user = result.scalar_one_or_none()
        if not user or user.status != "paid":
            return False
        sub_end = _parse_sub_end(user.sub_end_date)
        if not sub_end:
            return False
        return sub_end > datetime.now()


async def had_recent_one_time_purchase(user_id: int, hours: int = 24) -> bool:
    """Проверяет, была ли разовая покупка за последние N часов"""
    async with _get_session() as session:
        result = await session.execute(select(User.last_one_time_purchase).where(User.user_id == user_id))
        last_purchase_str = result.scalar_one_or_none()
        if not last_purchase_str:
            return False
        try:
            last_purchase = datetime.fromisoformat(last_purchase_str)
            time_diff = datetime.now() - last_purchase
            return time_diff.total_seconds() < (hours * 3600)
        except Exception:
            return False


async def check_text_limits(
    user_id: int, username: str, free_daily_text_limit: int, consume: bool = True
) -> dict:
    """
    Проверяет лимиты на текстовые сообщения (не OCR).
    
    Логика:
    1. Если активная подписка (sub_end_date > now) -> безлимит
    2. Если разовая покупка < 24 часов назад -> безлимит (бонус)
    3. Иначе проверяем FREE_DAILY_TEXT_LIMIT
    """
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

        # Сброс дневного счетчика
        if user.last_usage_date != today:
            user.daily_usage = 0
            user.last_usage_date = today
            await session.commit()
            await session.refresh(user)

        # Проверка админа
        if user.status == "admin":
            return {"allowed": True, "limit": None, "remaining": None, "reason": "admin"}

        # Проверка 1: Активная подписка
        now = datetime.now()
        sub_end = _parse_sub_end(user.sub_end_date)
        is_paid_active = (user.status == "paid") and sub_end and (sub_end > now)
        if is_paid_active:
            return {"allowed": True, "limit": None, "remaining": None, "reason": "subscription"}

        # Проверка 2: Разовая покупка за последние 24 часа
        if user.last_one_time_purchase:
            try:
                last_purchase = datetime.fromisoformat(user.last_one_time_purchase)
                time_diff = datetime.now() - last_purchase
                if time_diff.total_seconds() < (24 * 3600):  # 24 часа
                    return {"allowed": True, "limit": None, "remaining": None, "reason": "one_time_purchase"}
            except Exception:
                pass

        # Проверка 3: FREE тариф - проверяем лимит
        if user.daily_usage >= free_daily_text_limit:
            return {
                "allowed": False,
                "limit": free_daily_text_limit,
                "remaining": 0,
                "reason": "free_limit_exceeded"
            }

        if consume:
            user.daily_usage += 1
            await session.commit()
            await session.refresh(user)
            used = user.daily_usage
        else:
            used = user.daily_usage

        remaining = free_daily_text_limit - used
        return {
            "allowed": True,
            "limit": free_daily_text_limit,
            "remaining": max(0, remaining),
            "reason": "free"
        }


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


# ===== ПРОМОКОДЫ И РЕФЕРАЛЫ =====

async def activate_promo_code(user_id: int, code_text: str) -> dict:
    """
    Активирует промокод для пользователя.
    Возвращает dict с результатом: {"success": bool, "message": str, "type": str, "value": int}
    """
    code_text = code_text.strip().upper()
    now = datetime.now()
    
    async with _get_session() as session:
        # Проверяем существование промокода
        promo_result = await session.execute(select(PromoCode).where(PromoCode.code == code_text))
        promo = promo_result.scalar_one_or_none()
        
        if not promo:
            return {"success": False, "message": "❌ Промокод не найден."}
        
        # Проверка срока действия
        if promo.expiry_date:
            try:
                expiry = datetime.fromisoformat(promo.expiry_date.replace("Z", "+00:00"))
                if expiry < now:
                    return {"success": False, "message": "❌ Промокод истек."}
            except Exception:
                # Если не удалось распарсить, считаем что срок не истек
                pass
        
        # Проверка лимита использований
        if promo.max_uses > 0 and promo.current_uses >= promo.max_uses:
            return {"success": False, "message": "❌ Промокод больше недействителен (лимит использований исчерпан)."}
        
        # Проверка: использовал ли этот пользователь этот промокод ранее
        usage_result = await session.execute(
            select(PromoUsage).where(
                and_(PromoUsage.user_id == user_id, PromoUsage.promo_code_id == promo.id)
            )
        )
        existing_usage = usage_result.scalar_one_or_none()
        if existing_usage:
            return {"success": False, "message": "❌ Вы уже использовали этот промокод."}
        
        # Начисляем бонус
        user_result = await session.execute(select(User).where(User.user_id == user_id))
        user = user_result.scalar_one_or_none()
        if not user:
            return {"success": False, "message": "❌ Пользователь не найден."}
        
        try:
            if promo.type == "subscription_days":
                # Продлеваем подписку
                current_sub_end = _parse_sub_end(user.sub_end_date)
                if current_sub_end and current_sub_end > now:
                    # Если подписка активна, продлеваем от текущей даты окончания
                    new_sub_end = current_sub_end
                else:
                    # Если подписки нет, начинаем с сегодня
                    new_sub_end = now
                
                from datetime import timedelta
                new_sub_end = new_sub_end + timedelta(days=promo.value)
                user.sub_end_date = new_sub_end.isoformat()
                user.status = "paid"
                if not user.tier or user.tier == "free":
                    user.tier = "plus"  # По умолчанию plus при активации промокода
                
            elif promo.type == "balance_add":
                # Увеличиваем баланс анализов
                user.balance_analyses = (user.balance_analyses or 0) + promo.value
            else:
                return {"success": False, "message": "❌ Неизвестный тип промокода."}
            
            # Увеличиваем счетчик использований
            promo.current_uses += 1
            
            # Записываем использование
            usage = PromoUsage(
                user_id=user_id,
                promo_code_id=promo.id,
                used_at=now.isoformat()
            )
            session.add(usage)
            
            await session.commit()
            
            type_name = "дней подписки" if promo.type == "subscription_days" else "анализов"
            return {
                "success": True,
                "message": f"✅ Промокод активирован! Вам начислено: {promo.value} {type_name}.",
                "type": promo.type,
                "value": promo.value
            }
            
        except Exception as e:
            await session.rollback()
            logger.error(f"Ошибка при активации промокода: {e}")
            return {"success": False, "message": "❌ Ошибка при активации промокода. Попробуйте позже."}


async def create_promo_code(
    code: str,
    promo_type: str,
    value: int,
    max_uses: int = 0,
    expiry_date: Optional[str] = None
) -> dict:
    """
    Создает новый промокод (только для админов).
    Возвращает dict с результатом: {"success": bool, "message": str}
    """
    code = code.strip().upper()
    now = datetime.now().isoformat()
    
    async with _get_session() as session:
        # Проверяем, не существует ли уже такой код
        existing_result = await session.execute(select(PromoCode).where(PromoCode.code == code))
        existing = existing_result.scalar_one_or_none()
        if existing:
            return {"success": False, "message": f"❌ Промокод {code} уже существует."}
        
        # Создаем промокод
        promo = PromoCode(
            code=code,
            type=promo_type,
            value=value,
            max_uses=max_uses,
            current_uses=0,
            expiry_date=expiry_date,
            created_at=now
        )
        session.add(promo)
        await session.commit()
        
        return {
            "success": True,
            "message": f"✅ Промокод {code} создан! Тип: {promo_type}, Значение: {value}, Макс. использований: {max_uses if max_uses > 0 else '∞'}"
        }


async def get_referral_link(user_id: int) -> str:
    """Возвращает реферальную ссылку для пользователя"""
    # Формат: https://t.me/BOT_USERNAME?start=ref_USER_ID
    # Но мы вернем только параметр для команды /start
    return f"ref_{user_id}"
