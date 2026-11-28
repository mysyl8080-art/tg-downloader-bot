"""SQLite persistence: users, settings, downloads, favorites, bans, stats.

Stdlib sqlite3, one connection guarded by a lock (the bot is async but the
queries are milliseconds; a lock keeps it simple and safe).
"""
import sqlite3
import threading
import time

from config import settings

_lock = threading.RLock()
_conn = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id     INTEGER PRIMARY KEY,
    username    TEXT,
    first_name  TEXT,
    lang        TEXT NOT NULL DEFAULT 'ar',
    def_quality INTEGER NOT NULL DEFAULT 720,
    def_audio   TEXT NOT NULL DEFAULT 'mp3',
    joined_at   REAL NOT NULL,
    last_seen   REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS downloads (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    url         TEXT NOT NULL,
    platform    TEXT,
    kind        TEXT,
    title       TEXT,
    status      TEXT NOT NULL,
    error       TEXT,
    bytes       INTEGER,
    ts          REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_downloads_user ON downloads(user_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_downloads_ts ON downloads(ts DESC);
CREATE TABLE IF NOT EXISTS favorites (
    user_id INTEGER NOT NULL,
    url     TEXT NOT NULL,
    title   TEXT,
    ts      REAL NOT NULL,
    PRIMARY KEY (user_id, url)
);
CREATE TABLE IF NOT EXISTS banned (
    user_id INTEGER PRIMARY KEY,
    reason  TEXT,
    ts      REAL NOT NULL
);
"""


def conn():
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(settings.DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        with _lock:
            _conn.executescript(SCHEMA)
    return _conn


def _q(sql, args=(), one=False, write=False):
    with _lock:
        cur = conn().execute(sql, args)
        if write:
            conn().commit()
            return cur.lastrowid
        rows = cur.fetchall()
    return (rows[0] if rows else None) if one else rows


def upsert_user(user):
    now = time.time()
    _q("""INSERT INTO users (user_id, username, first_name, joined_at, last_seen)
          VALUES (?,?,?,?,?)
          ON CONFLICT(user_id) DO UPDATE SET username=excluded.username,
              first_name=excluded.first_name, last_seen=excluded.last_seen""",
       (user.id, user.username, user.first_name, now, now), write=True)


def get_user(user_id):
    return _q("SELECT * FROM users WHERE user_id=?", (user_id,), one=True)


def set_lang(user_id, lang):
    _q("UPDATE users SET lang=? WHERE user_id=?", (lang, user_id), write=True)


def set_def_quality(user_id, q):
    _q("UPDATE users SET def_quality=? WHERE user_id=?", (q, user_id), write=True)


def set_def_audio(user_id, fmt):
    _q("UPDATE users SET def_audio=? WHERE user_id=?", (fmt, user_id), write=True)


def log_download(user_id, url, platform, kind, title, status, error=None, nbytes=None):
    return _q("""INSERT INTO downloads (user_id,url,platform,kind,title,status,error,bytes,ts)
                 VALUES (?,?,?,?,?,?,?,?,?)""",
              (user_id, url, platform, kind, title, status, error, nbytes, time.time()),
              write=True)


def history(user_id, limit=10):
    return _q("SELECT * FROM downloads WHERE user_id=? ORDER BY ts DESC LIMIT ?",
              (user_id, limit))


def add_favorite(user_id, url, title):
    _q("INSERT OR REPLACE INTO favorites (user_id,url,title,ts) VALUES (?,?,?,?)",
       (user_id, url, title, time.time()), write=True)


def favorites(user_id, limit=20):
    return _q("SELECT * FROM favorites WHERE user_id=? ORDER BY ts DESC LIMIT ?",
              (user_id, limit))


def remove_favorite(user_id, url):
    _q("DELETE FROM favorites WHERE user_id=? AND url=?", (user_id, url), write=True)


def ban(user_id, reason=None):
    _q("INSERT OR REPLACE INTO banned (user_id,reason,ts) VALUES (?,?,?)",
       (user_id, reason, time.time()), write=True)


def unban(user_id):
    _q("DELETE FROM banned WHERE user_id=?", (user_id,), write=True)


def is_banned(user_id):
    return _q("SELECT 1 FROM banned WHERE user_id=?", (user_id,), one=True) is not None


def stats():
    day = time.time() - 86400
    r = {
        "users": _q("SELECT COUNT(*) c FROM users", one=True)["c"],
        "active_24h": _q("SELECT COUNT(*) c FROM users WHERE last_seen>?", (day,), one=True)["c"],
        "downloads": _q("SELECT COUNT(*) c FROM downloads", one=True)["c"],
        "downloads_24h": _q("SELECT COUNT(*) c FROM downloads WHERE ts>?", (day,), one=True)["c"],
        "failed": _q("SELECT COUNT(*) c FROM downloads WHERE status='failed'", one=True)["c"],
        "platforms": _q("""SELECT platform, COUNT(*) c FROM downloads
                           WHERE platform IS NOT NULL GROUP BY platform ORDER BY c DESC LIMIT 5"""),
    }
    return r
