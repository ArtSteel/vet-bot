# storage.py — VET: Мульти-питомец + Админка + Регистрация (FIXED)

import sqlite3
from contextlib import closing
from pathlib import Path
from datetime import datetime, date, time
import logging

DB_PATH = Path("bot.db")

def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with closing(_get_conn()) as conn:
        cur = conn.cursor()
        
        # Таблица пользователей
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id         INTEGER PRIMARY KEY,
                username        TEXT,
                status          TEXT DEFAULT 'free',
                tier            TEXT DEFAULT 'free',
                active_pet_id   INTEGER, -- Какой питомец сейчас выбран
                daily_usage     INTEGER DEFAULT 0,
                last_usage_date TEXT,
                photos_month    INTEGER DEFAULT 0,
                last_photo_month TEXT,
                sub_end_date    TEXT,
                joined_at       TEXT
            )
        """)

        # Таблица ПИТОМЦЕВ (Много животных у одного юзера)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS pets (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER,
                name        TEXT,
                type        TEXT, -- dog/cat
                breed       TEXT,
                age         TEXT, 
                weight      REAL,
                chronic     TEXT,
                allergies   TEXT,
                meds        TEXT,
                
                -- Напоминания (Даты в формате YYYY-MM-DD)
                next_vaccine_date TEXT, 
                next_tick_date    TEXT,
                
                updated_at  TEXT
            )
        """)
        
        # История сообщений
        cur.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                created_at TEXT    NOT NULL,
                user_text  TEXT    NOT NULL,
                bot_text   TEXT    NOT NULL
            )
        """)

        # Платежи YooKassa (чтобы не активировать подписку дважды)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS yookassa_payments (
                payment_id TEXT PRIMARY KEY,
                user_id    INTEGER,
                tier       TEXT,
                created_at TEXT
            )
        """)

        # Фидбек (👍/👎) под ответами
        cur.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                entry_id   INTEGER,
                kind       TEXT    NOT NULL,  -- 'like' / 'dislike'
                source     TEXT,
                created_at TEXT    NOT NULL,
                UNIQUE(user_id, entry_id)
            )
        """)
        
        # Легкая миграция старых БД (если столбцов ещё нет)
        try:
            cur.execute("ALTER TABLE users ADD COLUMN photos_month INTEGER DEFAULT 0")
        except Exception:
            pass
        try:
            cur.execute("ALTER TABLE users ADD COLUMN last_photo_month TEXT")
        except Exception:
            pass

        conn.commit()
        logging.info("📂 БД готова (Мульти-питомец + Админка).")


def _parse_sub_end(sub_end_date: str | None) -> datetime | None:
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
        # ISO datetime
        return datetime.fromisoformat(s)
    except Exception:
        pass
    try:
        # Date only -> end of day
        d = date.fromisoformat(s)
        return datetime.combine(d, time(23, 59, 59))
    except Exception:
        return None

# ===== АДМИНКА И СТАТИСТИКА (ВЕРНУЛ ОБРАТНО) =====

def get_all_users():
    """Для рассылки"""
    with closing(_get_conn()) as conn:
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM users")
        return [row['user_id'] for row in cur.fetchall()]

def get_bot_stats() -> dict:
    """Для команды /stats (расширенная статистика)"""
    today = datetime.now().strftime("%Y-%m-%d")
    this_month = datetime.now().strftime("%Y-%m")
    stats = {}
    with closing(_get_conn()) as conn:
        cur = conn.cursor()
        stats["users_total"] = cur.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        stats["users_today"] = cur.execute("SELECT COUNT(*) FROM users WHERE joined_at LIKE ?", (f"{today}%",)).fetchone()[0]
        stats["msgs_total"] = cur.execute("SELECT COUNT(*) FROM history").fetchone()[0]
        stats["msgs_today"] = cur.execute("SELECT COUNT(*) FROM history WHERE created_at LIKE ?", (f"{today}%",)).fetchone()[0]

        stats["tier_free"] = cur.execute("SELECT COUNT(*) FROM users WHERE tier = 'free' OR tier IS NULL").fetchone()[0]
        stats["tier_plus"] = cur.execute("SELECT COUNT(*) FROM users WHERE tier = 'plus'").fetchone()[0]
        stats["tier_pro"] = cur.execute("SELECT COUNT(*) FROM users WHERE tier = 'pro'").fetchone()[0]
        stats["paid_total"] = cur.execute("SELECT COUNT(*) FROM users WHERE status = 'paid'").fetchone()[0]

        # Активные/истекшие подписки (безопасно через python-парсинг даты)
        rows = cur.execute("SELECT sub_end_date FROM users WHERE status = 'paid'").fetchall()
        active = 0
        expired = 0
        now = datetime.now()
        for r in rows:
            end_dt = _parse_sub_end(r["sub_end_date"])
            if end_dt and end_dt > now:
                active += 1
            else:
                expired += 1
        stats["paid_active"] = active
        stats["paid_expired"] = expired

        # Фото/документы: используемые в текущем месяце
        stats["photos_users_month"] = cur.execute(
            "SELECT COUNT(*) FROM users WHERE last_photo_month = ? AND photos_month > 0",
            (this_month,),
        ).fetchone()[0]
        stats["photos_total_month"] = cur.execute(
            "SELECT COALESCE(SUM(photos_month),0) FROM users WHERE last_photo_month = ?",
            (this_month,),
        ).fetchone()[0]

        # Фидбек
        stats["fb_total"] = cur.execute("SELECT COUNT(*) FROM feedback").fetchone()[0]
        stats["fb_today"] = cur.execute("SELECT COUNT(*) FROM feedback WHERE created_at LIKE ?", (f"{today}%",)).fetchone()[0]
        stats["fb_like_total"] = cur.execute("SELECT COUNT(*) FROM feedback WHERE kind='like'").fetchone()[0]
        stats["fb_dislike_total"] = cur.execute("SELECT COUNT(*) FROM feedback WHERE kind='dislike'").fetchone()[0]
        stats["fb_like_today"] = cur.execute(
            "SELECT COUNT(*) FROM feedback WHERE kind='like' AND created_at LIKE ?",
            (f"{today}%",),
        ).fetchone()[0]
        stats["fb_dislike_today"] = cur.execute(
            "SELECT COUNT(*) FROM feedback WHERE kind='dislike' AND created_at LIKE ?",
            (f"{today}%",),
        ).fetchone()[0]
    return stats

# ===== ПОЛЬЗОВАТЕЛИ =====

def register_user_if_new(user_id: int, username: str):
    """Регистрирует юзера при нажатии /start (ВЕРНУЛ ОБРАТНО)"""
    today = datetime.now().strftime("%Y-%m-%d")
    with closing(_get_conn()) as conn:
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        if not cur.fetchone():
            cur.execute(
                "INSERT INTO users (user_id, username, joined_at, last_usage_date, daily_usage, status, tier) VALUES (?, ?, ?, ?, 0, 'free', 'free')",
                (user_id, username, datetime.now().isoformat(), today)
            )
            conn.commit()


def _ensure_user_row(cur: sqlite3.Cursor, user_id: int, username: str):
    today = datetime.now().strftime("%Y-%m-%d")
    cur.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO users (user_id, username, joined_at, last_usage_date, daily_usage, status, tier, photos_month, last_photo_month) "
            "VALUES (?, ?, ?, ?, 0, 'free', 'free', 0, ?)",
            (user_id, username, datetime.now().isoformat(), today, datetime.now().strftime("%Y-%m")),
        )

def check_user_limits(user_id: int, username: str, limits_by_tier: dict, consume: bool = True) -> dict:
    today = datetime.now().strftime("%Y-%m-%d")
    with closing(_get_conn()) as conn:
        cur = conn.cursor()
        _ensure_user_row(cur, user_id, username)
        conn.commit()

        cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = cur.fetchone()
        
        user = dict(user)

        # Сброс лимитов
        if user["last_usage_date"] != today:
            cur.execute("UPDATE users SET daily_usage = 0, last_usage_date = ? WHERE user_id = ?", (today, user_id))
            conn.commit()
            user["daily_usage"] = 0
            user["last_usage_date"] = today

        # Проверка админа или подписки
        if user["status"] == "admin": 
             return {"allowed": True, "role": "admin", "tier": "pro", "limit": None, "remaining": None}
             
        now = datetime.now()
        sub_end = _parse_sub_end(user.get("sub_end_date"))
        is_paid_active = (user["status"] == "paid") and sub_end and (sub_end > now)
        tier = (user.get("tier") or "plus").strip().lower()
        if not is_paid_active:
            tier = "free"

        # Лимиты по тарифу (на день)
        limit = limits_by_tier.get(tier)
        if limit is None:
            # None = безлимит
            return {"allowed": True, "role": "paid" if is_paid_active else "free", "tier": tier, "limit": None, "remaining": None}

        # Проверка лимита
        if user["daily_usage"] >= int(limit):
            return {
                "allowed": False,
                "role": "paid" if is_paid_active else "free",
                "tier": tier,
                "limit": int(limit),
                "remaining": 0,
            }

        if consume:
            # Разрешено — списываем 1 запрос (MVP: любой AI-запрос = 1)
            cur.execute("UPDATE users SET daily_usage = daily_usage + 1 WHERE user_id = ?", (user_id,))
            conn.commit()
            used = user["daily_usage"] + 1
        else:
            used = user["daily_usage"]
        remaining = int(limit) - used
        return {
            "allowed": True,
            "role": "paid" if is_paid_active else "free",
            "tier": tier,
            "limit": int(limit),
            "remaining": max(0, remaining),
        }

def increment_usage(user_id: int):
    with closing(_get_conn()) as conn:
        cur = conn.cursor()
        cur.execute("UPDATE users SET daily_usage = daily_usage + 1 WHERE user_id = ?", (user_id,))
        conn.commit()

def set_user_paid(user_id: int, end_date_str: str, tier: str):
    with closing(_get_conn()) as conn:
        cur = conn.cursor()
        cur.execute("UPDATE users SET status = 'paid', sub_end_date = ?, tier = ? WHERE user_id = ?", (end_date_str, tier, user_id))
        conn.commit()


def get_user_subscription(user_id: int) -> dict | None:
    with closing(_get_conn()) as conn:
        cur = conn.cursor()
        cur.execute("SELECT user_id, username, status, tier, daily_usage, last_usage_date, sub_end_date FROM users WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def get_effective_tier(user_id: int) -> str:
    """
    Возвращает фактический тариф:
    - 'pro' / 'standard' если подписка активна
    - 'free' если подписки нет или истекла
    """
    u = get_user_subscription(user_id)
    if not u:
        return "free"
    if u.get("status") != "paid":
        return "free"
    sub_end = _parse_sub_end(u.get("sub_end_date"))
    if not sub_end or sub_end <= datetime.now():
        return "free"
    return (u.get("tier") or "plus").strip().lower() or "plus"


def check_photo_limits(user_id: int, username: str, photo_limits_by_tier: dict, consume: bool = True) -> dict:
    """
    Месячный лимит фото/PDF (vision/OCR).
    photo_limits_by_tier: {'free': 1, 'plus': 10, 'pro': 20} где None = безлимит
    """
    month = datetime.now().strftime("%Y-%m")
    with closing(_get_conn()) as conn:
        cur = conn.cursor()
        _ensure_user_row(cur, user_id, username)
        conn.commit()

        user = dict(cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone())

        # reset monthly counter
        if (user.get("last_photo_month") or "") != month:
            cur.execute("UPDATE users SET photos_month = 0, last_photo_month = ? WHERE user_id = ?", (month, user_id))
            conn.commit()
            user["photos_month"] = 0
            user["last_photo_month"] = month

        now = datetime.now()
        sub_end = _parse_sub_end(user.get("sub_end_date"))
        is_paid_active = (user.get("status") == "paid") and sub_end and (sub_end > now)
        tier = (user.get("tier") or "plus").strip().lower()
        if not is_paid_active:
            tier = "free"

        limit = photo_limits_by_tier.get(tier)
        if limit is None:
            return {"allowed": True, "tier": tier, "limit": None, "remaining": None}

        used = int(user.get("photos_month") or 0)
        if used >= int(limit):
            return {"allowed": False, "tier": tier, "limit": int(limit), "remaining": 0}

        if consume:
            cur.execute("UPDATE users SET photos_month = photos_month + 1 WHERE user_id = ?", (user_id,))
            conn.commit()
            used += 1

        return {"allowed": True, "tier": tier, "limit": int(limit), "remaining": max(0, int(limit) - used)}

# ===== УПРАВЛЕНИЕ ПИТОМЦАМИ (НОВОЕ) =====

def create_pet(user_id: int, pet_type: str = "dog"):
    """Создает пустую анкету и делает её активной"""
    with closing(_get_conn()) as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO pets (user_id, type, updated_at) VALUES (?, ?, ?)", (user_id, pet_type, datetime.now().isoformat()))
        pet_id = cur.lastrowid
        # Делаем активным
        cur.execute("UPDATE users SET active_pet_id = ? WHERE user_id = ?", (pet_id, user_id))
        conn.commit()
    return pet_id

def get_active_pet(user_id: int):
    """Возвращает словарь с данными активного питомца"""
    with closing(_get_conn()) as conn:
        cur = conn.cursor()
        # Узнаем ID активного
        cur.execute("SELECT active_pet_id FROM users WHERE user_id = ?", (user_id,))
        res = cur.fetchone()
        if not res or not res['active_pet_id']: return None
        
        pet_id = res['active_pet_id']
        cur.execute("SELECT * FROM pets WHERE id = ?", (pet_id,))
        row = cur.fetchone()
        return dict(row) if row else None

def get_user_pets(user_id: int):
    """Список всех питомцев юзера (id, name, type)"""
    with closing(_get_conn()) as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, name, type FROM pets WHERE user_id = ?", (user_id,))
        return [dict(r) for r in cur.fetchall()]

def set_active_pet(user_id: int, pet_id: int):
    with closing(_get_conn()) as conn:
        cur = conn.cursor()
        # Проверка, что пет принадлежит юзеру
        cur.execute("SELECT id FROM pets WHERE id = ? AND user_id = ?", (pet_id, user_id))
        if cur.fetchone():
            cur.execute("UPDATE users SET active_pet_id = ? WHERE user_id = ?", (pet_id, user_id))
            conn.commit()

def update_pet_field(user_id: int, field: str, value):
    """Обновляет поле у АКТИВНОГО питомца"""
    pet = get_active_pet(user_id)
    if not pet: return
    with closing(_get_conn()) as conn:
        cur = conn.cursor()
        # Безопасно только если field берется из нашего кода, а не от юзера напрямую
        cur.execute(f"UPDATE pets SET {field} = ?, updated_at = ? WHERE id = ?", (value, datetime.now().isoformat(), pet['id']))
        conn.commit()

def delete_active_pet(user_id: int):
    pet = get_active_pet(user_id)
    if not pet: return
    with closing(_get_conn()) as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM pets WHERE id = ?", (pet['id'],))
        cur.execute("UPDATE users SET active_pet_id = NULL WHERE user_id = ?", (user_id,))
        conn.commit()

# ===== ИСТОРИЯ И ПРОЧЕЕ =====

def save_entry(user_id: int, user_text: str, bot_text: str) -> int:
    with closing(_get_conn()) as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO history (user_id, created_at, user_text, bot_text) VALUES (?, ?, ?, ?)", (user_id, datetime.now().strftime("%Y-%m-%d %H:%M"), user_text, bot_text))
        conn.commit()
        return int(cur.lastrowid)

def get_last_entries(user_id: int, limit: int = 3):
    with closing(_get_conn()) as conn:
        cur = conn.cursor()
        cur.execute("SELECT created_at, user_text, bot_text FROM history WHERE user_id = ? ORDER BY id DESC LIMIT ?", (user_id, limit))
        return [(r["created_at"], r["user_text"], r["bot_text"]) for r in cur.fetchall()]

# ===== РАССЫЛКА НАПОМИНАНИЙ =====
def check_reminders_today():
    """Возвращает список (user_id, text) кому надо напомнить"""
    today = datetime.now().strftime("%Y-%m-%d")
    notifications = []
    with closing(_get_conn()) as conn:
        cur = conn.cursor()
        # Вакцинация
        try:
            cur.execute("SELECT user_id, name FROM pets WHERE next_vaccine_date = ?", (today,))
            for row in cur.fetchall():
                notifications.append((row['user_id'], f"💉 **Напоминание:** Сегодня у питомца **{row['name']}** плановая вакцинация!"))
        except: pass
        
        # Клещи
        try:
            cur.execute("SELECT user_id, name FROM pets WHERE next_tick_date = ?", (today,))
            for row in cur.fetchall():
                notifications.append((row['user_id'], f"🕷 **Напоминание:** Пора обработать **{row['name']}** от клещей и блох!"))
        except: pass
            
    return notifications


def mark_yookassa_payment_processed(payment_id: str, user_id: int, tier: str, created_at: str) -> bool:
    """
    Сохраняет payment_id, чтобы не активировать подписку повторно.
    Возвращает True, если это новый платеж (вставка прошла), иначе False.
    """
    with closing(_get_conn()) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT OR IGNORE INTO yookassa_payments (payment_id, user_id, tier, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (payment_id, user_id, tier, created_at),
        )
        conn.commit()
        return cur.rowcount > 0


def save_feedback(user_id: int, kind: str, source: str = "text", entry_id: int | None = None) -> None:
    kind = "like" if str(kind).lower() == "like" else "dislike"
    with closing(_get_conn()) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT OR REPLACE INTO feedback (user_id, entry_id, kind, source, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, entry_id, kind, source, datetime.now().strftime("%Y-%m-%d %H:%M")),
        )
        conn.commit()