"""
database/db.py – SQLite database (يشتغل على Railway بدون إعداد)
"""
import sqlite3
import logging
from datetime import date
from utils.config import DB_PATH

logger = logging.getLogger(__name__)


def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """أنشئ الجداول إذا ما موجودة"""
    conn = get_conn()
    c = conn.cursor()

    c.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id     INTEGER PRIMARY KEY,
            username    TEXT,
            full_name   TEXT,
            joined_at   TEXT DEFAULT (date('now')),
            is_banned   INTEGER DEFAULT 0,
            total_dl    INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS downloads (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER,
            platform    TEXT,
            url         TEXT,
            status      TEXT,   -- success | failed
            file_size   INTEGER DEFAULT 0,
            created_at  TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS daily_usage (
            user_id     INTEGER,
            usage_date  TEXT,
            count       INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, usage_date)
        );

        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT
        );
    """)

    # قيم افتراضية
    c.execute("INSERT OR IGNORE INTO settings VALUES ('maintenance', '0')")
    c.execute("INSERT OR IGNORE INTO settings VALUES ('welcome_msg', 'مرحباً بك في MediaDrop! 🎉')")
    conn.commit()
    conn.close()
    logger.info("✅ Database initialized")


# ── Users ─────────────────────────────────────────────────────────────────────

def upsert_user(user_id: int, username: str, full_name: str):
    conn = get_conn()
    conn.execute("""
        INSERT INTO users (user_id, username, full_name)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            username  = excluded.username,
            full_name = excluded.full_name
    """, (user_id, username or "", full_name or ""))
    conn.commit()
    conn.close()


def is_banned(user_id: int) -> bool:
    conn = get_conn()
    row = conn.execute("SELECT is_banned FROM users WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return bool(row and row["is_banned"])


def ban_user(user_id: int):
    conn = get_conn()
    conn.execute("UPDATE users SET is_banned=1 WHERE user_id=?", (user_id,))
    conn.commit(); conn.close()


def unban_user(user_id: int):
    conn = get_conn()
    conn.execute("UPDATE users SET is_banned=0 WHERE user_id=?", (user_id,))
    conn.commit(); conn.close()


def get_all_users():
    conn = get_conn()
    rows = conn.execute("SELECT user_id, username, full_name, is_banned, total_dl FROM users").fetchall()
    conn.close()
    return rows


# ── Downloads ─────────────────────────────────────────────────────────────────

def log_download(user_id: int, platform: str, url: str, status: str, file_size: int = 0):
    conn = get_conn()
    conn.execute("""
        INSERT INTO downloads (user_id, platform, url, status, file_size)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, platform, url, status, file_size))
    if status == "success":
        conn.execute("UPDATE users SET total_dl = total_dl + 1 WHERE user_id=?", (user_id,))
    conn.commit(); conn.close()


def get_daily_count(user_id: int) -> int:
    today = str(date.today())
    conn = get_conn()
    row = conn.execute(
        "SELECT count FROM daily_usage WHERE user_id=? AND usage_date=?",
        (user_id, today)
    ).fetchone()
    conn.close()
    return row["count"] if row else 0


def increment_daily(user_id: int):
    today = str(date.today())
    conn = get_conn()
    conn.execute("""
        INSERT INTO daily_usage (user_id, usage_date, count) VALUES (?, ?, 1)
        ON CONFLICT(user_id, usage_date) DO UPDATE SET count = count + 1
    """, (user_id, today))
    conn.commit(); conn.close()


# ── Stats ─────────────────────────────────────────────────────────────────────

def get_stats() -> dict:
    conn = get_conn()
    total_users   = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    total_dl      = conn.execute("SELECT COUNT(*) FROM downloads WHERE status='success'").fetchone()[0]
    today_dl      = conn.execute(
        "SELECT COUNT(*) FROM downloads WHERE date(created_at)=date('now') AND status='success'"
    ).fetchone()[0]
    top_platform  = conn.execute(
        "SELECT platform, COUNT(*) as c FROM downloads WHERE status='success' GROUP BY platform ORDER BY c DESC LIMIT 1"
    ).fetchone()
    banned_count  = conn.execute("SELECT COUNT(*) FROM users WHERE is_banned=1").fetchone()[0]
    conn.close()
    return {
        "total_users":  total_users,
        "total_dl":     total_dl,
        "today_dl":     today_dl,
        "top_platform": top_platform["platform"] if top_platform else "—",
        "banned":       banned_count,
    }


# ── Settings ──────────────────────────────────────────────────────────────────

def get_setting(key: str) -> str:
    conn = get_conn()
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else ""


def set_setting(key: str, value: str):
    conn = get_conn()
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit(); conn.close()
