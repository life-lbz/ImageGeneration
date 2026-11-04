"""Per-call SQLite connection with a process-wide serialization lock.

Every API (connect/transaction/one/all/execute) opens a fresh sqlite3.Connection
so SQLite's own transaction machinery can never see a "nested BEGIN" that was
working on the same object. A single ``threading.Lock`` serializes writes so
worker + uvicorn threads do not clobber each other's WAL frames. Schema and
PRAGMA are applied once at Database init; per-connection PRAGMA only sets
busy_timeout so a writer waits for the other connection's transaction.
"""
from contextlib import contextmanager
import logging
import sqlite3
import threading
from pathlib import Path

log = logging.getLogger(__name__)

# WAL + busy_timeout lets concurrent writers queue cleanly instead of throwing
# "database is locked" to callers. Both the connect() timeout and busy_timeout
# are intentionally 15s so any lock wait ends before uvicorn's default worker.
_TIMEOUT_SEC = 15
_BUSY_TIMEOUT_MS = _TIMEOUT_SEC * 1000

SCHEMA = '''
CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE, password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','user')), is_active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), csrf_token TEXT NOT NULL, expires_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id), prompt TEXT NOT NULL, negative_prompt TEXT NOT NULL DEFAULT '', steps INTEGER NOT NULL, seed INTEGER NOT NULL, status TEXT NOT NULL CHECK(status IN ('queued','running','succeeded','failed','cancelled')), created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT, error TEXT, prompt_id TEXT, image_path TEXT, image_sha256 TEXT, elapsed_seconds REAL);
CREATE INDEX IF NOT EXISTS jobs_owner_created ON jobs(owner_id,created_at DESC);
CREATE INDEX IF NOT EXISTS jobs_status_created ON jobs(status,created_at);
CREATE INDEX IF NOT EXISTS sessions_user ON sessions(user_id);
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
'''


class Database:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        # Apply schema + one-shot PRAGMA through a throwaway connection so WAL is
        # created and migrations run before any other path touches the file.
        with self.connect() as c:
            c.executescript(SCHEMA)
            columns = {row[1] for row in c.execute('PRAGMA table_info(users)')}
            if 'must_change_password' not in columns:
                c.execute('ALTER TABLE users ADD COLUMN must_change_password INTEGER NOT NULL DEFAULT 0')
            job_columns = {row[1] for row in c.execute('PRAGMA table_info(jobs)')}
            for side in ('width', 'height'):
                if side not in job_columns:
                    c.execute(f'ALTER TABLE jobs ADD COLUMN {side} INTEGER NOT NULL DEFAULT 512')
            c.execute('PRAGMA journal_mode=WAL')

    def connect(self):
        c = sqlite3.connect(self.path, timeout=_TIMEOUT_SEC, isolation_level=None)
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA foreign_keys=ON')
        c.execute(f'PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}')
        return c

    @contextmanager
    def transaction(self):
        with self._lock:
            c = self.connect()
            try:
                c.execute('BEGIN IMMEDIATE')
                yield c
                c.execute('COMMIT')
            except sqlite3.Error:
                try:
                    c.execute('ROLLBACK')
                except sqlite3.Error:
                    log.exception('DB rollback failed')
                raise
            finally:
                c.close()

    def one(self, sql, params=()):
        with self._lock:
            c = self.connect()
            try:
                row = c.execute(sql, params).fetchone()
                return dict(row) if row else None
            finally:
                c.close()

    def all(self, sql, params=()):
        with self._lock:
            c = self.connect()
            try:
                return [dict(row) for row in c.execute(sql, params).fetchall()]
            finally:
                c.close()

    def execute(self, sql, params=()):
        with self._lock:
            c = self.connect()
            try:
                return c.execute(sql, params).rowcount
            finally:
                c.close()
