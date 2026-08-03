"""Per-account bot push subscription storage.

Bot-mode accounts can record users who send ``/start`` and honor per-user
``/stop`` / ``/resume`` opt-out state.  The store is a small SQLite database
under each account's isolated data directory, using the same short-lived
connection pattern as the forward queue and stats databases.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional

from backend.account_paths import AccountPathRegistry
from backend.logger import get_logger

logger = get_logger()

STATUS_ACTIVE = "active"
STATUS_PAUSED = "paused"
VALID_STATUSES = (STATUS_ACTIVE, STATUS_PAUSED)


class SubscriberStore:
    """SQLite-backed registry of users who opted into bot push delivery."""

    def __init__(self, db_path: str | Path = "data/subscribers.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_db()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 30000")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS subscribers (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    status TEXT NOT NULL DEFAULT 'active'
                        CHECK(status IN ('active', 'paused')),
                    delivered_count INTEGER NOT NULL DEFAULT 0,
                    first_seen_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_subscribers_status
                    ON subscribers(status);
                """
            )
            columns = {
                row[1] for row in conn.execute("PRAGMA table_info(subscribers)").fetchall()
            }
            if "delivered_count" not in columns:
                conn.execute(
                    "ALTER TABLE subscribers "
                    "ADD COLUMN delivered_count INTEGER NOT NULL DEFAULT 0"
                )
        try:
            self.db_path.chmod(0o600)
        except OSError:
            pass

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "user_id": row["user_id"],
            "username": row["username"],
            "first_name": row["first_name"],
            "last_name": row["last_name"],
            "status": row["status"],
            "delivered_count": row["delivered_count"],
            "first_seen_at": row["first_seen_at"],
            "updated_at": row["updated_at"],
        }

    def record(
        self,
        user_id: int,
        *,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
    ) -> dict[str, Any]:
        """Register or refresh a user identity, keeping their opt-out state."""
        now = time.time()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO subscribers
                    (user_id, username, first_name, last_name, status,
                     first_seen_at, updated_at)
                VALUES (?, ?, ?, ?, 'active', ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username = COALESCE(?, username),
                    first_name = COALESCE(?, first_name),
                    last_name = COALESCE(?, last_name),
                    updated_at = ?
                """,
                (
                    int(user_id),
                    username,
                    first_name,
                    last_name,
                    now,
                    now,
                    username,
                    first_name,
                    last_name,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT * FROM subscribers WHERE user_id = ?", (int(user_id),)
            ).fetchone()
            return self._row_to_dict(row)

    def set_status(self, user_id: int, status: str) -> dict[str, Any]:
        """Persist an opt-in/opt-out change, creating a bare record if needed."""
        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid subscriber status: {status!r}")
        now = time.time()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO subscribers
                    (user_id, status, first_seen_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (int(user_id), status, now, now),
            )
            conn.execute(
                """
                UPDATE subscribers
                SET status = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (status, now, int(user_id)),
            )
            row = conn.execute(
                "SELECT * FROM subscribers WHERE user_id = ?", (int(user_id),)
            ).fetchone()
            return self._row_to_dict(row)

    def get(self, user_id: int) -> Optional[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM subscribers WHERE user_id = ?", (int(user_id),)
            ).fetchone()
            return self._row_to_dict(row) if row else None

    def is_suppressed(self, user_id: int) -> bool:
        """True when a registered user has opted out of push delivery."""
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM subscribers
                WHERE user_id = ? AND status = 'paused'
                """,
                (int(user_id),),
            ).fetchone()
            return row is not None

    def is_suppressed_username(self, username: str) -> bool:
        """Username-based suppressed lookup (Telegram usernames are case-folded)."""
        name = str(username or "").strip().lstrip("@")
        if not name:
            return False
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM subscribers
                WHERE LOWER(username) = LOWER(?) AND status = 'paused'
                """,
                (name,),
            ).fetchone()
            return row is not None

    def increment_delivered(self, user_id: int) -> bool:
        """Increment the successful push count for a registered user."""
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE subscribers
                SET delivered_count = delivered_count + 1
                WHERE user_id = ?
                """,
                (int(user_id),),
            )
            return cursor.rowcount > 0

    def increment_delivered_username(self, username: str) -> bool:
        """Increment the successful push count for a registered username."""
        name = str(username or "").strip().lstrip("@")
        if not name:
            return False
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE subscribers
                SET delivered_count = delivered_count + 1
                WHERE LOWER(username) = LOWER(?)
                """,
                (name,),
            )
            return cursor.rowcount > 0

    def list(self, limit: int | None = None) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            query = "SELECT * FROM subscribers ORDER BY first_seen_at DESC"
            params: tuple[Any, ...] = ()
            if limit is not None:
                query += " LIMIT ?"
                params = (max(1, min(int(limit), 10000)),)
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_dict(row) for row in rows]

    def counts(self) -> dict[str, int]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) AS count FROM subscribers GROUP BY status"
            ).fetchall()
            counts = {row["status"]: int(row["count"]) for row in rows}
            return {
                "total": sum(counts.values()),
                "active": counts.get(STATUS_ACTIVE, 0),
                "paused": counts.get(STATUS_PAUSED, 0),
            }


class AccountSubscriptionRegistry:
    """Resolve one isolated subscriber store per authenticated account."""

    def __init__(
        self,
        data_dir: str | Path = "data",
        paths: AccountPathRegistry | None = None,
    ):
        self.paths = paths or AccountPathRegistry(data_dir=data_dir)
        self._stores: dict[str, SubscriberStore] = {}
        self._lock = threading.RLock()

    def for_account(self, account_id: str) -> SubscriberStore:
        path = self.paths.for_account(account_id).data_dir / "subscribers.db"
        with self._lock:
            store = self._stores.get(account_id)
            if store is None:
                store = SubscriberStore(path)
                self._stores[account_id] = store
            return store

    def discard(self, account_id: str) -> None:
        with self._lock:
            self._stores.pop(account_id, None)
