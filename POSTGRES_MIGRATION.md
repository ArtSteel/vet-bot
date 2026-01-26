# Миграция с SQLite на PostgreSQL

## Быстрый старт

### 1. Запусти PostgreSQL через Docker

```bash
docker-compose up -d
```

Проверь, что контейнер запущен:
```bash
docker ps | grep vet-bot-postgres
```

### 2. Настрой `.env` файл

Скопируй `.env.example` в `.env` и заполни параметры PostgreSQL:

```bash
cp .env.example .env
```

Или добавь в существующий `.env`:

```env
POSTGRES_USER=vetbot
POSTGRES_PASSWORD=vetbot_password
POSTGRES_DB=vetbot_db
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
```

### 3. Выполни миграцию данных

```bash
python migrate_db.py
```

Скрипт:
- ✅ Подключится к существующей SQLite БД (`bot.db`)
- ✅ Создаст таблицы в PostgreSQL
- ✅ Перенесет все данные (Users, Pets, History, Payments, Feedback)
- ✅ Обновит sequences для автоинкрементных полей

### 4. Перезапусти бота

```bash
python bot.py
```

Бот автоматически определит PostgreSQL по переменным в `.env` и переключится на него.

В логах должно появиться:
```
🐘 Используется PostgreSQL: localhost:5432/vetbot_db
📂 БД готова (PostgreSQL + Async SQLAlchemy 2.0)
```

## Проверка миграции

### Проверь данные в PostgreSQL:

```bash
docker exec -it vet-bot-postgres psql -U vetbot -d vetbot_db -c "SELECT COUNT(*) FROM users;"
docker exec -it vet-bot-postgres psql -U vetbot -d vetbot_db -c "SELECT COUNT(*) FROM pets;"
```

### Или через Python:

```python
import asyncio
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from models import User, Pet

async def check():
    engine = create_async_engine("postgresql+asyncpg://vetbot:vetbot_password@localhost:5432/vetbot_db")
    session_factory = async_sessionmaker(engine, class_=AsyncSession)
    
    async with session_factory() as session:
        users_count = await session.execute(select(func.count(User.user_id)))
        pets_count = await session.execute(select(func.count(Pet.id)))
        print(f"Users: {users_count.scalar()}, Pets: {pets_count.scalar()}")

asyncio.run(check())
```

## Откат на SQLite

Если нужно вернуться на SQLite:

1. Удали или закомментируй переменные PostgreSQL в `.env`:
   ```env
   # POSTGRES_USER=vetbot
   # POSTGRES_PASSWORD=vetbot_password
   # ...
   ```

2. Перезапусти бота - он автоматически переключится на SQLite

## Важные замечания

- ⚠️ **Резервная копия**: Перед миграцией сделай копию `bot.db`:
  ```bash
  cp bot.db bot.db.backup
  ```

- ✅ **Данные сохраняются**: Старый `bot.db` остается нетронутым, можно использовать как резервную копию

- 🔄 **Обратная совместимость**: Бот автоматически определяет, какую БД использовать по переменным окружения

- 🐘 **PostgreSQL в продакшене**: Для VPS можно использовать внешний PostgreSQL или запустить через docker-compose
