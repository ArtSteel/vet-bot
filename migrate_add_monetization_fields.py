"""
Миграция: Добавление полей для гибридной монетизации
Добавляет колонки balance_analyses, is_trial_used, last_one_time_purchase в таблицу users
"""

import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

load_dotenv()

def _get_database_url() -> str:
    """Определяет URL базы данных"""
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        if database_url.startswith("postgresql://"):
            database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif not database_url.startswith(("postgresql+asyncpg://", "sqlite+aiosqlite://")):
            database_url = f"postgresql+asyncpg://{database_url}"
        return database_url

    pg_user = os.getenv("POSTGRES_USER")
    pg_password = os.getenv("POSTGRES_PASSWORD")
    pg_db = os.getenv("POSTGRES_DB")
    pg_host = os.getenv("POSTGRES_HOST", "localhost")
    pg_port = os.getenv("POSTGRES_PORT", "5432")

    if pg_user and pg_password and pg_db:
        return f"postgresql+asyncpg://{pg_user}:{pg_password}@{pg_host}:{pg_port}/{pg_db}"

    db_path = Path("bot.db")
    return f"sqlite+aiosqlite:///{db_path}"

async def migrate():
    """Выполняет миграцию"""
    database_url = _get_database_url()
    
    if "sqlite" in database_url:
        print("⚠️ SQLite: миграция не требуется (SQLAlchemy создаст колонки автоматически)")
        return
    
    print(f"🔗 Подключение к PostgreSQL...")
    engine = create_async_engine(database_url, echo=False)
    
    async with engine.begin() as conn:
        # Проверяем, существуют ли колонки
        check_sql = """
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'users' 
            AND column_name IN ('balance_analyses', 'is_trial_used', 'last_one_time_purchase')
        """
        result = await conn.execute(text(check_sql))
        existing_columns = {row[0] for row in result.fetchall()}
        
        migrations = []
        
        if 'balance_analyses' not in existing_columns:
            migrations.append(("balance_analyses", "ALTER TABLE users ADD COLUMN balance_analyses INTEGER DEFAULT 0"))
        
        if 'is_trial_used' not in existing_columns:
            migrations.append(("is_trial_used", "ALTER TABLE users ADD COLUMN is_trial_used INTEGER DEFAULT 0"))
        
        if 'last_one_time_purchase' not in existing_columns:
            migrations.append(("last_one_time_purchase", "ALTER TABLE users ADD COLUMN last_one_time_purchase VARCHAR"))
        
        if not migrations:
            print("✅ Все колонки уже существуют, миграция не требуется")
            return
        
        print(f"📝 Найдено {len(migrations)} колонок для добавления...")
        
        for col_name, sql in migrations:
            try:
                print(f"  ➕ Добавляю колонку: {col_name}")
                await conn.execute(text(sql))
                print(f"  ✅ Колонка {col_name} добавлена")
            except Exception as e:
                print(f"  ❌ Ошибка при добавлении {col_name}: {e}")
                raise
        
        print("\n✅ Миграция завершена успешно!")
    
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(migrate())
