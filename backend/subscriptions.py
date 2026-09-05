"""Per-account bot push subscription storage.

Bot-mode accounts can record users who send ``/start`` and honor per-user
``/stop`` / ``/resume`` opt-out state.  The store is a small SQLite database
under each account's isolated data directory, using the same short-lived
connection pattern as the forward queue and stats databases.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import func, inspect, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from backend.account_paths import AccountPathRegistry
from backend.database import Base, Subscriber, create_sqlite_engine, session_factory, session_scope
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
        self.engine = create_sqlite_engine(self.db_path)
        self._session_factory = session_factory(self.engine)
        self._init_db()

    def _session(self):
        return session_scope(self._session_factory)

    def _init_db(self) -> None:
        with self._lock:
            Base.metadata.create_all(self.engine, tables=[Subscriber.__table__])
            columns = {
                column["name"] for column in inspect(self.engine).get_columns("subscribers")
            }
            if "delivered_count" not in columns:
                with self.engine.begin() as connection:
                    connection.exec_driver_sql(
                        "ALTER TABLE subscribers ADD COLUMN delivered_count INTEGER NOT NULL DEFAULT 0"
                    )
        try:
            self.db_path.chmod(0o600)
        except OSError:
            pass

    @staticmethod
    def _row_to_dict(row: Subscriber) -> dict[str, Any]:
        return {
            "user_id": row.user_id,
            "username": row.username,
            "first_name": row.first_name,
            "last_name": row.last_name,
            "status": row.status,
            "delivered_count": row.delivered_count,
            "first_seen_at": row.first_seen_at,
            "updated_at": row.updated_at,
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
        with self._lock, self._session() as session:
            statement = sqlite_insert(Subscriber).values(
                user_id=int(user_id),
                username=username,
                first_name=first_name,
                last_name=last_name,
                status=STATUS_ACTIVE,
                first_seen_at=now,
                updated_at=now,
            )
            session.execute(
                statement.on_conflict_do_update(
                    index_elements=[Subscriber.user_id],
                    set_={
                        "username": func.coalesce(statement.excluded.username, Subscriber.username),
                        "first_name": func.coalesce(statement.excluded.first_name, Subscriber.first_name),
                        "last_name": func.coalesce(statement.excluded.last_name, Subscriber.last_name),
                        "updated_at": now,
                    },
                )
            )
            return self._row_to_dict(session.get(Subscriber, int(user_id)))

    def set_status(self, user_id: int, status: str) -> dict[str, Any]:
        """Persist an opt-in/opt-out change, creating a bare record if needed."""
        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid subscriber status: {status!r}")
        now = time.time()
        with self._lock, self._session() as session:
            session.execute(
                sqlite_insert(Subscriber)
                .values(user_id=int(user_id), status=status, first_seen_at=now, updated_at=now)
                .prefix_with("OR IGNORE")
            )
            session.execute(
                update(Subscriber)
                .where(Subscriber.user_id == int(user_id))
                .values(status=status, updated_at=now)
            )
            return self._row_to_dict(session.get(Subscriber, int(user_id)))

    def get(self, user_id: int) -> Optional[dict[str, Any]]:
        with self._lock, self._session() as session:
            row = session.get(Subscriber, int(user_id))
            return self._row_to_dict(row) if row else None

    def is_suppressed(self, user_id: int) -> bool:
        """True when a registered user has opted out of push delivery."""
        with self._lock, self._session() as session:
            return session.scalar(
                select(Subscriber.user_id).where(
                    Subscriber.user_id == int(user_id), Subscriber.status == STATUS_PAUSED
                )
            ) is not None

    def is_suppressed_username(self, username: str) -> bool:
        """Username-based suppressed lookup (Telegram usernames are case-folded)."""
        name = str(username or "").strip().lstrip("@")
        if not name:
            return False
        with self._lock, self._session() as session:
            return session.scalar(
                select(Subscriber.user_id).where(
                    func.lower(Subscriber.username) == name.lower(),
                    Subscriber.status == STATUS_PAUSED,
                )
            ) is not None

    def increment_delivered(self, user_id: int) -> bool:
        """Increment the successful push count for a registered user."""
        with self._lock, self._session() as session:
            result = session.execute(
                update(Subscriber)
                .where(Subscriber.user_id == int(user_id))
                .values(delivered_count=Subscriber.delivered_count + 1)
            )
            return result.rowcount > 0

    def increment_delivered_username(self, username: str) -> bool:
        """Increment the successful push count for a registered username."""
        name = str(username or "").strip().lstrip("@")
        if not name:
            return False
        with self._lock, self._session() as session:
            result = session.execute(
                update(Subscriber)
                .where(func.lower(Subscriber.username) == name.lower())
                .values(delivered_count=Subscriber.delivered_count + 1)
            )
            return result.rowcount > 0

    def list(self, limit: int | None = None) -> list[dict[str, Any]]:
        with self._lock, self._session() as session:
            statement = select(Subscriber).order_by(Subscriber.first_seen_at.desc())
            if limit is not None:
                statement = statement.limit(max(1, min(int(limit), 10000)))
            return [self._row_to_dict(row) for row in session.scalars(statement).all()]

    def counts(self) -> dict[str, int]:
        with self._lock, self._session() as session:
            rows = session.execute(
                select(Subscriber.status, func.count()).group_by(Subscriber.status)
            ).all()
            counts = {status: int(count) for status, count in rows}
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
