# Migration: SQLite → PostgreSQL

This project can run with PostgreSQL (recommended for production) and can migrate existing data from `bot.db` (SQLite) into PostgreSQL.

## Important notes

- Storage selects database in this order:
  1) `POSTGRES_*` variables (highest priority)  
  2) `DATABASE_URL`  
  3) SQLite fallback (`bot.db`)
- Migration script: `migrate_db.py`
- Always create a backup of `bot.db` before migration.

---

## Option A (recommended): PostgreSQL via Docker Compose

### 1) Start PostgreSQL only

Because `docker-compose.yml` also starts `app` and `redis`, for migration you typically need only Postgres:

```bash
docker-compose up -d db
```

Check that it is running:

```bash
docker ps | grep vet-bot-postgres
```

### 2) Configure `.env`

Copy `.env.example` → `.env` and set PostgreSQL variables.

If PostgreSQL runs via docker-compose inside the same network, use:

```env
POSTGRES_HOST=db
POSTGRES_PORT=5432
```

If PostgreSQL runs on your host machine (outside Docker), use:

```env
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
```

### 3) Run migration

Run migration from your local Python environment:

```bash
python migrate_db.py
```

What it does:
- reads local SQLite `bot.db`
- creates tables in PostgreSQL (if missing)
- migrates data (users, pets, history, payments, feedback, etc.)

### 4) Start the full stack

```bash
docker-compose up -d --build
```

---

## Verification

```bash
docker exec -it vet-bot-postgres psql -U vetbot -d vetbot_db -c "SELECT COUNT(*) FROM users;"
docker exec -it vet-bot-postgres psql -U vetbot -d vetbot_db -c "SELECT COUNT(*) FROM pets;"
```

---

## Rollback to SQLite

To run on SQLite again:
- unset (or comment out) all `POSTGRES_*` variables in `.env`
- restart the app; it will fallback to `bot.db`

