import random
import sqlite3

DB_PATH = "bot.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id         INTEGER PRIMARY KEY,
            first_name TEXT NOT NULL,
            last_name  TEXT NOT NULL,
            role       TEXT NOT NULL,
            group_num  TEXT,
            active     INTEGER NOT NULL DEFAULT 1,
            banned     INTEGER NOT NULL DEFAULT 0,
            last_topics TEXT
        );

        CREATE TABLE IF NOT EXISTS pairs (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            date     TEXT NOT NULL,
            user1_id INTEGER NOT NULL,
            user2_id INTEGER NOT NULL,
            status   TEXT NOT NULL DEFAULT 'active'
        );

        CREATE INDEX IF NOT EXISTS idx_pairs_date ON pairs(date);
        CREATE INDEX IF NOT EXISTS idx_pairs_user1 ON pairs(user1_id);
        CREATE INDEX IF NOT EXISTS idx_pairs_user2 ON pairs(user2_id);

        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT
        );
        """
    )
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
    if "active" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN active INTEGER NOT NULL DEFAULT 1")
    if "banned" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN banned INTEGER NOT NULL DEFAULT 0")
    if "last_topics" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN last_topics TEXT")
    conn.commit()
    conn.close()


def add_user(user_id, first_name, last_name, role, group_num):
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO users(id, first_name, last_name, role, group_num) "
        "VALUES (?, ?, ?, ?, ?)",
        (user_id, first_name, last_name, role, group_num),
    )
    conn.commit()
    conn.close()


def get_user(user_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_user_ids():
    conn = get_conn()
    rows = conn.execute("SELECT id FROM users WHERE active = 1 AND banned = 0").fetchall()
    conn.close()
    return [r["id"] for r in rows]


def get_all_users():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM users ORDER BY id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def set_active(user_id, active):
    conn = get_conn()
    conn.execute("UPDATE users SET active = ? WHERE id = ?", (1 if active else 0, user_id))
    conn.commit()
    conn.close()


def set_banned(user_id, banned):
    conn = get_conn()
    conn.execute("UPDATE users SET banned = ? WHERE id = ?", (1 if banned else 0, user_id))
    conn.commit()
    conn.close()


def get_last_topics(user_id):
    conn = get_conn()
    row = conn.execute("SELECT last_topics FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    if not row or not row["last_topics"]:
        return []
    return row["last_topics"].split("|")


def set_last_topics(user_id, topics):
    conn = get_conn()
    conn.execute(
        "UPDATE users SET last_topics = ? WHERE id = ?",
        ("|".join(topics), user_id),
    )
    conn.commit()
    conn.close()


def get_setting(key, default=None):
    conn = get_conn()
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key, value):
    conn = get_conn()
    conn.execute(
        "INSERT INTO settings(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()
    conn.close()


def get_active_partner(user_id, date_str):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM pairs WHERE date = ? AND status = 'active' "
        "AND (user1_id = ? OR user2_id = ?)",
        (date_str, user_id, user_id),
    ).fetchone()
    conn.close()
    if not row:
        return None
    partner_id = row["user1_id"] if row["user2_id"] == user_id else row["user2_id"]
    return get_user(partner_id)


def end_pair(user_id, date_str):
    conn = get_conn()
    conn.execute(
        "UPDATE pairs SET status = 'ended' WHERE date = ? AND status = 'active' "
        "AND (user1_id = ? OR user2_id = ?)",
        (date_str, user_id, user_id),
    )
    conn.commit()
    conn.close()


def do_matching(date_str):
    ids = get_all_user_ids()
    random.shuffle(ids)

    pairs = []
    leftover = None
    for i in range(0, len(ids) - 1, 2):
        pairs.append((ids[i], ids[i + 1]))
    if len(ids) % 2 == 1:
        leftover = ids[-1]

    if pairs:
        conn = get_conn()
        conn.executemany(
            "INSERT INTO pairs(date, user1_id, user2_id) VALUES (?, ?, ?)",
            [(date_str, a, b) for a, b in pairs],
        )
        conn.commit()
        conn.close()

    return pairs, leftover

