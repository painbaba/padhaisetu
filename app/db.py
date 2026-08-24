"""SQLite helpers + schema init (DDL per brief section 5). Connection-per-call, IST timestamps."""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from . import config

_IST_FALLBACK = timezone(timedelta(hours=5, minutes=30))


def now_ist() -> datetime:
    """Current time in Asia/Kolkata (fixed +05:30 fallback when tzdata is absent)."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Asia/Kolkata"))
    except Exception:
        return datetime.now(_IST_FALLBACK)


def ist_tz():
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo("Asia/Kolkata")
    except Exception:
        return _IST_FALLBACK


def iso(dt: datetime | None = None) -> str:
    dt = dt or now_ist()
    return dt.isoformat(timespec="seconds")


DDL = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  phone TEXT UNIQUE,
  lang TEXT DEFAULT 'hi',
  name TEXT,
  grade INT,
  created_at TEXT
);
CREATE TABLE IF NOT EXISTS chat_sessions(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INT,
  state TEXT,
  context_json TEXT DEFAULT '{}',
  updated_at TEXT
);
CREATE TABLE IF NOT EXISTS questions(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  subject TEXT,
  grade INT,
  skill_id TEXT,
  difficulty INT CHECK(difficulty IN (1,2,3)),
  text_hi TEXT,
  text_en TEXT,
  options_json TEXT,
  correct_idx INT,
  hint_hi TEXT,
  hint_en TEXT,
  solution_hi TEXT,
  solution_en TEXT,
  gen_params_json TEXT,
  marks INT DEFAULT 1,
  qtype TEXT,
  active INT DEFAULT 1
);
CREATE TABLE IF NOT EXISTS attempts(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INT,
  question_id INT,
  correct INT,
  time_ms INT,
  mode TEXT,
  skill_id TEXT,
  created_at TEXT
);
CREATE TABLE IF NOT EXISTS mastery(
  user_id INT,
  skill_id TEXT,
  score REAL DEFAULT 0.5,
  seen INT DEFAULT 0,
  last_seen TEXT,
  due_after TEXT,
  PRIMARY KEY(user_id, skill_id)
);
CREATE TABLE IF NOT EXISTS streaks(
  user_id INTEGER PRIMARY KEY,
  current INT DEFAULT 0,
  best INT DEFAULT 0,
  last_day TEXT
);
CREATE TABLE IF NOT EXISTS reports(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INT,
  week_of TEXT,
  payload_json TEXT,
  sent INT DEFAULT 0
);
CREATE TABLE IF NOT EXISTS mock_attempts(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INT,
  subject TEXT,
  grade INT,
  started_at TEXT,
  finished_at TEXT,
  total_marks INT,
  earned_marks INT,
  pct REAL,
  detail_json TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_questions ON questions(subject, grade, skill_id, text_en);
CREATE UNIQUE INDEX IF NOT EXISTS ux_sessions_user ON chat_sessions(user_id);
"""


@contextmanager
def connect():
    conn = sqlite3.connect(config.db_path(), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(DDL)
        # Migration shim: pre-existing DBs lack the M7 marks/qtype columns.
        for stmt in ("ALTER TABLE questions ADD COLUMN marks INT DEFAULT 1",
                     "ALTER TABLE questions ADD COLUMN qtype TEXT"):
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError:
                pass  # column already exists


def query(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(sql, params).fetchall()


def query_one(sql: str, params: tuple = ()) -> sqlite3.Row | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: tuple = ()) -> int:
    with connect() as conn:
        cur = conn.execute(sql, params)
        return cur.lastrowid


def scalar(sql: str, params: tuple = ()) -> object:
    row = query_one(sql, params)
    return row[0] if row is not None else None
