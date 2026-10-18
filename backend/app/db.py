"""SQLite storage. Same tables as backend_plan.md, kept in one file so the demo needs no Docker."""
import json
import os
import sqlite3
import threading
import time

DB_PATH = os.environ.get("DATABASE_PATH", os.path.join(os.path.dirname(__file__), "..", "night_ledger.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS calls (
  call_id TEXT PRIMARY KEY,
  source TEXT NOT NULL DEFAULT 'retell',
  scenario TEXT,
  status TEXT NOT NULL DEFAULT 'live',
  from_number TEXT,
  started_at REAL NOT NULL,
  ended_at REAL,
  duration_ms INTEGER,
  disconnection_reason TEXT,
  lane TEXT,
  red_flags TEXT NOT NULL DEFAULT '[]',
  cluster TEXT,
  intent TEXT,
  reason TEXT,
  urgency INTEGER,
  caller_name TEXT,
  callback_number TEXT,
  needs_review INTEGER NOT NULL DEFAULT 0,
  rules_result TEXT,
  jev_result TEXT,
  details TEXT NOT NULL DEFAULT '{}',
  red_flag_at REAL,
  transfer_started_at REAL,
  transfer_ended_at REAL,
  transfer_target TEXT,
  transfer_status TEXT,
  callback_status TEXT,
  callback_attempts INTEGER NOT NULL DEFAULT 0,
  summary TEXT,
  recording_url TEXT,
  transcript TEXT NOT NULL DEFAULT '[]',
  raw TEXT
);
CREATE INDEX IF NOT EXISTS calls_started ON calls(started_at);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  call_id TEXT,
  actor TEXT NOT NULL,
  type TEXT NOT NULL,
  payload TEXT NOT NULL DEFAULT '{}',
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS suggestions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  type TEXT NOT NULL,
  call_id TEXT,
  evidence TEXT NOT NULL DEFAULT '{}',
  recommendation TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'open',
  snooze_until REAL,
  outcome TEXT,
  created_at REAL NOT NULL,
  decided_at REAL
);
CREATE TABLE IF NOT EXISTS nurse_lines (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  label TEXT NOT NULL,
  number TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'nurse',
  on_duty INTEGER NOT NULL DEFAULT 1,
  priority INTEGER NOT NULL DEFAULT 1,
  updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS surge_state (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  is_on INTEGER NOT NULL DEFAULT 0,
  switched_at REAL,
  status_message TEXT,
  status_cluster TEXT,
  routine_window TEXT NOT NULL DEFAULT 'tomorrow morning between 8 and 11',
  priority_window TEXT NOT NULL DEFAULT 'within 30 minutes'
);
INSERT OR IGNORE INTO surge_state (id) VALUES (1);
"""

JSON_COLS = {"red_flags", "rules_result", "jev_result", "details", "transcript", "raw", "evidence", "recommendation", "payload"}
LANE_RANK = {None: -1, "green": 0, "amber": 1, "red": 2}

_lock = threading.RLock()
_conn = None


def conn():
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False, isolation_level=None)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.executescript(SCHEMA)
        for col, typ in (("language", "TEXT"), ("neighborhood", "TEXT"), ("callback_at", "REAL"), ("callback_for", "TEXT")):
            try:
                _conn.execute(f"ALTER TABLE calls ADD COLUMN {col} {typ}")
            except sqlite3.OperationalError:
                pass  # column already there
    return _conn


def reset_connection(path=None):
    """Point the module at a new database file (used by tests)."""
    global _conn, DB_PATH
    if _conn is not None:
        _conn.close()
    _conn = None
    if path:
        DB_PATH = path


def _decode(row):
    if row is None:
        return None
    d = dict(row)
    for k, v in d.items():
        if k in JSON_COLS and isinstance(v, str):
            try:
                d[k] = json.loads(v)
            except ValueError:
                pass
    return d


def _encode(v):
    return json.dumps(v) if isinstance(v, (dict, list)) else v


def q(sql, params=()):
    with _lock:
        return [_decode(r) for r in conn().execute(sql, params).fetchall()]


def one(sql, params=()):
    with _lock:
        return _decode(conn().execute(sql, params).fetchone())


def run(sql, params=()):
    with _lock:
        cur = conn().execute(sql, params)
        return cur.lastrowid


def insert(table, row):
    cols = list(row)
    sql = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})"
    return run(sql, [_encode(row[c]) for c in cols])


def update(table, key_col, key, fields):
    if not fields:
        return
    sets = ",".join(f"{c}=?" for c in fields)
    run(f"UPDATE {table} SET {sets} WHERE {key_col}=?", [_encode(v) for v in fields.values()] + [key])


def event(type_, call_id=None, actor="system", payload=None, at=None):
    insert("events", {"call_id": call_id, "actor": actor, "type": type_, "payload": payload or {}, "created_at": at or time.time()})


def raise_lane(call_id, new_lane, why, actor="system"):
    """The one-way rule: the system can only move a call up. Returns True if it moved."""
    call = one("SELECT lane FROM calls WHERE call_id=?", (call_id,))
    if call is None or LANE_RANK.get(new_lane, -1) <= LANE_RANK.get(call["lane"], -1):
        return False
    update("calls", "call_id", call_id, {"lane": new_lane})
    event("lane_raised", call_id, actor, {"from": call["lane"], "to": new_lane, "why": why})
    return True


def surge():
    return one("SELECT * FROM surge_state WHERE id=1")
