"""
Скрипт миграции данных из SQLite в PostgreSQL.
Запускать один раз после настройки PostgreSQL.

Использование:
    1. docker-compose up -d  # Запустить PostgreSQL
    2. python migrate_db.py  # Выполнить миграцию
"""

import asyncio
import logging
from pathlib import Path
from dotenv import load_dotenv
import os

from sqlalchemy import select, text, func
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from models import Base, User, Pet, History, YooKassaPayment, Feedback

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Migration")

# Загружаем переменные окружения
load_dotenv()

# Путь к существующей SQLite БД
SQLITE_DB_PATH = Path("bot.db")

# PostgreSQL параметры из .env
PG_USER = os.getenv("POSTGRES_USER", "vetbot")
PG_PASSWORD = os.getenv("POSTGRES_PASSWORD", "vetbot_password")
PG_DB = os.getenv("POSTGRES_DB", "vetbot_db")
PG_HOST = os.getenv("POSTGRES_HOST", "localhost")
PG_PORT = os.getenv("POSTGRES_PORT", "5432")

SQLITE_URL = f"sqlite+aiosqlite:///{SQLITE_DB_PATH}"
PG_URL = f"postgresql+asyncpg://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DB}"


async def migrate_table(
    sqlite_session: AsyncSession,
    pg_session: AsyncSession,
    model_class,
    table_name: str,
    has_auto_increment: bool = False,
):
    """Мигрирует одну таблицу из SQLite в PostgreSQL"""
    logger.info(f"📦 Миграция таблицы: {table_name}")

    # Читаем все данные из SQLite
    result = await sqlite_session.execute(select(model_class))
    rows = result.scalars().all()

    if not rows:
        logger.info(f"   ⚠️  Таблица {table_name} пуста, пропускаем")
        return 0

    count = 0
    for row in rows:
        try:
            # Создаем словарь из объекта
            if hasattr(row, "to_dict"):
                row_dict = row.to_dict()
            else:
                row_dict = {
                    col.name: getattr(row, col.name) 
                    for col in model_class.__table__.columns
                }
            
            # Создаем новый объект для PostgreSQL
            new_row = model_class(**row_dict)
            pg_session.add(new_row)
            count += 1
        except Exception as e:
            logger.warning(f"   ⚠️  Пропущена запись из-за ошибки: {e}")
            continue

    await pg_session.commit()
    logger.info(f"   ✅ Перенесено записей: {count}")

    # Если есть автоинкремент, обновляем sequence
    if has_auto_increment:
        try:
            # Получаем максимальный ID
            max_id_result = await pg_session.execute(
                select(func.max(getattr(model_class, "id")))
            )
            max_id = max_id_result.scalar()
            if max_id:
                # Обновляем sequence для PostgreSQL
                sequence_name = f"{table_name}_id_seq"
                await pg_session.execute(
                    text(f"SELECT setval('{sequence_name}', {max_id}, true)")
                )
                await pg_session.commit()
                logger.info(f"   🔄 Обновлен sequence: {sequence_name} -> {max_id}")
        except Exception as e:
            logger.warning(f"   ⚠️  Не удалось обновить sequence для {table_name}: {e}")

    return count


async def main():
    """Основная функция миграции"""
    logger.info("🚀 Начинаю миграцию из SQLite в PostgreSQL...")

    # Проверяем наличие SQLite БД
    if not SQLITE_DB_PATH.exists():
        logger.error(f"❌ Файл {SQLITE_DB_PATH} не найден!")
        return

    # Создаем движки
    sqlite_engine = create_async_engine(SQLITE_URL, echo=False)
    pg_engine = create_async_engine(PG_URL, echo=False)

    # Проверяем подключение к PostgreSQL
    try:
        async with pg_engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("✅ Подключение к PostgreSQL успешно")
    except Exception as e:
        logger.error(f"❌ Не удалось подключиться к PostgreSQL: {e}")
        logger.error("   Убедитесь, что PostgreSQL запущен: docker-compose up -d")
        return

    # Создаем таблицы в PostgreSQL
    logger.info("📋 Создание таблиц в PostgreSQL...")
    async with pg_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("✅ Таблицы созданы")

    # Создаем сессии
    sqlite_session_factory = async_sessionmaker(sqlite_engine, class_=AsyncSession, expire_on_commit=False)
    pg_session_factory = async_sessionmaker(pg_engine, class_=AsyncSession, expire_on_commit=False)

    total_migrated = 0

    try:
        async with sqlite_session_factory() as sqlite_session, pg_session_factory() as pg_session:
            # Мигрируем таблицы в правильном порядке (с учетом foreign keys)
            # 1. Users (нет зависимостей, primary key = user_id, не автоинкремент)
            count = await migrate_table(sqlite_session, pg_session, User, "users", has_auto_increment=False)
            total_migrated += count

            # 2. Pets (зависит от users, primary key = id, автоинкремент)
            count = await migrate_table(sqlite_session, pg_session, Pet, "pets", has_auto_increment=True)
            total_migrated += count

            # 3. History (зависит от users, primary key = id, автоинкремент)
            count = await migrate_table(sqlite_session, pg_session, History, "history", has_auto_increment=True)
            total_migrated += count

            # 4. YooKassaPayment (зависит от users, primary key = payment_id, не автоинкремент)
            count = await migrate_table(sqlite_session, pg_session, YooKassaPayment, "yookassa_payments", has_auto_increment=False)
            total_migrated += count

            # 5. Feedback (зависит от users и history, primary key = id, автоинкремент)
            count = await migrate_table(sqlite_session, pg_session, Feedback, "feedback", has_auto_increment=True)
            total_migrated += count

    except Exception as e:
        logger.error(f"❌ Ошибка во время миграции: {e}")
        import traceback
        traceback.print_exc()
        return

    finally:
        await sqlite_engine.dispose()
        await pg_engine.dispose()

    logger.info(f"✅ Миграция завершена успешно!")
    logger.info(f"📊 Всего перенесено записей: {total_migrated}")
    logger.info("")
    logger.info("💡 Теперь обновите .env файл, добавив DATABASE_URL или параметры PostgreSQL")
    logger.info("   Бот автоматически переключится на PostgreSQL при следующем запуске")


if __name__ == "__main__":
    asyncio.run(main())
