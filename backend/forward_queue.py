"""Persistent forwarding queue and queue-level FloodWait coordination.

The queue is deliberately synchronous at the storage boundary (each operation
uses a short-lived SQLite connection) and asynchronous at the consumer
boundary.  This keeps the Telegram event loop responsive while making every
state transition durable.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterator, Optional

from telethon.errors import FloodWaitError

from backend.i18n import t
from backend.logger import get_logger

logger = get_logger()


def rule_fingerprint(rule_data: dict[str, Any]) -> str:
    """Return a stable identity for the rule snapshot stored with a task."""
    payload = json.dumps(rule_data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def parse_member_ids(raw: Optional[str]) -> list[int]:
    """Parse a stored ``group_member_ids`` JSON column into a sorted id list."""
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return sorted({int(m) for m in parsed if m is not None})
    except (TypeError, ValueError, json.JSONDecodeError):
        pass
    return []


def parse_media_files(raw: Optional[str]) -> list[dict[str, Any]]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [item for item in parsed if isinstance(item, dict)]
    except (TypeError, ValueError, json.JSONDecodeError):
        pass
    return []


@dataclass(frozen=True)
class ForwardQueueItem:
    id: int
    dedup_key: str
    rule_name: str
    rule_data: dict[str, Any]
    rule_fingerprint: str
    source_chat_id: int
    source_chat_name: Optional[str]
    source_message_id: int
    sender_id: Optional[int]
    grouped_id: Optional[str]
    group_member_ids: Optional[tuple[int, ...]]
    group_settle_until: Optional[float]
    status: str
    attempt_count: int
    failure_count: int
    next_target_index: int
    available_at: float
    last_error: Optional[str]
    created_at: float
    updated_at: float
    content_preview: str
    media_files: tuple[dict[str, Any], ...]
    media_size: int


class ForwardQueueStore:
    """SQLite state store for durable forwarding jobs."""

    def __init__(self, db_path: str | Path = "data/forward_queue.db"):
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
                CREATE TABLE IF NOT EXISTS forward_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dedup_key TEXT NOT NULL UNIQUE,
                    rule_name TEXT NOT NULL,
                    rule_data TEXT NOT NULL,
                    rule_fingerprint TEXT NOT NULL,
                    source_chat_id INTEGER NOT NULL,
                    source_chat_name TEXT,
                    source_message_id INTEGER NOT NULL,
                    sender_id INTEGER,
                    grouped_id TEXT,
                    group_member_ids TEXT,
                    group_settle_until REAL,
                    status TEXT NOT NULL DEFAULT 'pending'
                        CHECK(status IN ('pending', 'processing', 'completed', 'failed')),
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    failure_count INTEGER NOT NULL DEFAULT 0,
                    next_target_index INTEGER NOT NULL DEFAULT 0,
                    available_at REAL NOT NULL,
                    last_error TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    completed_at REAL
                );
                CREATE INDEX IF NOT EXISTS idx_forward_queue_ready
                    ON forward_queue(status, available_at, id);
                CREATE INDEX IF NOT EXISTS idx_forward_queue_status
                    ON forward_queue(status, updated_at);
                CREATE TABLE IF NOT EXISTS forward_queue_state (
                    id INTEGER PRIMARY KEY CHECK(id = 1),
                    paused_until REAL NOT NULL DEFAULT 0,
                    pause_reason TEXT,
                    updated_at REAL NOT NULL
                );
                INSERT OR IGNORE INTO forward_queue_state(id, paused_until, updated_at)
                    VALUES (1, 0, 0);
                """
            )
            columns = {
                row[1] for row in conn.execute("PRAGMA table_info(forward_queue)").fetchall()
            }
            if "failure_count" not in columns:
                conn.execute(
                    "ALTER TABLE forward_queue ADD COLUMN failure_count INTEGER NOT NULL DEFAULT 0"
                )
            if "group_member_ids" not in columns:
                conn.execute(
                    "ALTER TABLE forward_queue ADD COLUMN group_member_ids TEXT"
                )
            if "group_settle_until" not in columns:
                conn.execute(
                    "ALTER TABLE forward_queue ADD COLUMN group_settle_until REAL"
                )
            if "source_chat_name" not in columns:
                conn.execute(
                    "ALTER TABLE forward_queue ADD COLUMN source_chat_name TEXT"
                )
            if "content_preview" not in columns:
                conn.execute("ALTER TABLE forward_queue ADD COLUMN content_preview TEXT NOT NULL DEFAULT ''")
            if "media_files" not in columns:
                conn.execute("ALTER TABLE forward_queue ADD COLUMN media_files TEXT NOT NULL DEFAULT '[]'")
            if "media_size" not in columns:
                conn.execute("ALTER TABLE forward_queue ADD COLUMN media_size INTEGER NOT NULL DEFAULT 0")
        try:
            self.db_path.chmod(0o600)
        except OSError:
            pass

    @staticmethod
    def _row_to_item(row: sqlite3.Row) -> ForwardQueueItem:
        member_ids = parse_member_ids(row["group_member_ids"])
        media_files = parse_media_files(row["media_files"])
        return ForwardQueueItem(
            id=row["id"],
            dedup_key=row["dedup_key"],
            rule_name=row["rule_name"],
            rule_data=json.loads(row["rule_data"]),
            rule_fingerprint=row["rule_fingerprint"],
            source_chat_id=row["source_chat_id"],
            source_chat_name=row["source_chat_name"],
            source_message_id=row["source_message_id"],
            sender_id=row["sender_id"],
            grouped_id=row["grouped_id"],
            group_member_ids=tuple(member_ids) if member_ids else None,
            group_settle_until=row["group_settle_until"],
            status=row["status"],
            attempt_count=row["attempt_count"],
            failure_count=row["failure_count"],
            next_target_index=row["next_target_index"],
            available_at=row["available_at"],
            last_error=row["last_error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            content_preview=row["content_preview"] or "",
            media_files=tuple(media_files),
            media_size=int(row["media_size"] or 0),
        )

    def _get(self, conn: sqlite3.Connection, item_id: int) -> ForwardQueueItem:
        row = conn.execute("SELECT * FROM forward_queue WHERE id = ?", (item_id,)).fetchone()
        if row is None:
            raise KeyError(f"Forward queue item {item_id} does not exist")
        return self._row_to_item(row)

    def get_item(self, item_id: int) -> ForwardQueueItem:
        with self._lock, self._connect() as conn:
            return self._get(conn, item_id)

    def delete_item(self, item_id: int) -> bool:
        """Remove an unfinished queue item.

        Completed and failed items remain available for retention and history,
        while pending/processing items are the operational queue shown in the
        dashboard.  The conditional delete also makes this operation safe to
        repeat when a consumer changes the item state concurrently.
        """
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """
                DELETE FROM forward_queue
                WHERE id = ? AND status IN ('pending', 'processing')
                """,
                (int(item_id),),
            )
            return cursor.rowcount == 1

    def list_active(self, limit: int = 50) -> list[ForwardQueueItem]:
        return self.list_active_page(limit, 0)[0]

    def list_active_page(self, limit: int = 50, offset: int = 0) -> tuple[list[ForwardQueueItem], int]:
        """Return a page and total count of unfinished queue items."""
        with self._lock, self._connect() as conn:
            bounded_limit = max(1, min(int(limit), 100))
            bounded_offset = max(0, int(offset))
            total = conn.execute(
                "SELECT COUNT(*) FROM forward_queue WHERE status IN ('pending', 'processing')"
            ).fetchone()[0]
            rows = conn.execute(
                """
                SELECT * FROM forward_queue
                WHERE status IN ('pending', 'processing')
                ORDER BY CASE status WHEN 'processing' THEN 0 ELSE 1 END,
                         available_at ASC, id ASC
                LIMIT ? OFFSET ?
                """,
                (bounded_limit, bounded_offset),
            ).fetchall()
            return [self._row_to_item(row) for row in rows], int(total)

    def enqueue(
        self,
        *,
        rule_data: dict[str, Any],
        source_chat_id: int,
        source_message_id: int,
        sender_id: Optional[int],
        grouped_id: Optional[int | str],
        source_chat_name: Optional[str] = None,
        settle_seconds: float = 1.0,
        content_preview: str = "",
        media_files: Optional[list[dict[str, Any]]] = None,
        media_size: int = 0,
    ) -> tuple[ForwardQueueItem, bool]:
        """Insert a message, merging subsequent updates from the same album.

        Album members arrive as separate updates.  The first insert seeds a
        durable job; later members of the same album are folded into its
        ``group_member_ids`` list so the consumer can fetch every member by ID
        (works for bot sessions, which cannot page history).  ``group_settle_until``
        extends with every member arrival so ``claim_next`` never consumes an
        album that is still being delivered.
        """
        now = time.time()
        fingerprint = rule_fingerprint(rule_data)
        group_text = str(grouped_id) if grouped_id is not None else None
        suffix = f"group:{group_text}" if group_text is not None else f"message:{source_message_id}"
        dedup_key = f"{fingerprint}:{source_chat_id}:{suffix}"
        settle = max(0.0, float(settle_seconds)) if group_text is not None else 0.0
        available_at = now + settle
        settle_until = now + settle if group_text is not None else None
        encoded_rule = json.dumps(rule_data, ensure_ascii=False, sort_keys=True)
        members_json = json.dumps([int(source_message_id)]) if group_text is not None else None
        normalized_media = [item for item in (media_files or []) if isinstance(item, dict)]
        media_json = json.dumps(normalized_media, ensure_ascii=False)

        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO forward_queue
                (dedup_key, rule_name, rule_data, rule_fingerprint, source_chat_id,
                 source_chat_name, source_message_id, sender_id, grouped_id,
                 group_member_ids, group_settle_until, content_preview, media_files, media_size, status,
                 available_at, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)
                """,
                (
                    dedup_key,
                    str(rule_data.get("name", "")),
                    encoded_rule,
                    fingerprint,
                    int(source_chat_id),
                    str(source_chat_name) if source_chat_name else None,
                    int(source_message_id),
                    sender_id,
                    group_text,
                    members_json,
                    settle_until,
                    str(content_preview or "")[:500],
                    media_json,
                    max(0, int(media_size or 0)),
                    available_at,
                    now,
                    now,
                ),
            )
            inserted = cursor.rowcount == 1
            target_key = dedup_key
            if not inserted and group_text is not None:
                # Album updates arrive separately; wait for the group to settle.
                existing = conn.execute(
                    "SELECT id, status, group_member_ids, media_files, media_size, content_preview FROM forward_queue WHERE dedup_key = ?",
                    (dedup_key,),
                ).fetchone()
                if existing is not None:
                    existing_members = parse_member_ids(existing["group_member_ids"])
                    already_member = int(source_message_id) in existing_members
                    if existing["status"] in ("pending", "processing") and not already_member:
                        # Normal case: fold the member in and extend the settle window.
                        members = sorted(set(existing_members + [int(source_message_id)]))
                        merged_media = parse_media_files(existing["media_files"])
                        seen_media = {item.get("message_id") for item in merged_media}
                        for media in normalized_media:
                            if media.get("message_id") not in seen_media:
                                merged_media.append(media)
                        merged_size = sum(int(item.get("size") or 0) for item in merged_media)
                        conn.execute(
                            """
                            UPDATE forward_queue
                            SET source_message_id = MIN(source_message_id, ?),
                                source_chat_name = COALESCE(?, source_chat_name),
                                sender_id = COALESCE(sender_id, ?),
                                available_at = CASE WHEN status = 'pending'
                                    THEN MAX(available_at, ?) ELSE available_at END,
                                group_settle_until = CASE WHEN status = 'pending'
                                    THEN MAX(COALESCE(group_settle_until, 0), ?)
                                    ELSE group_settle_until END,
                                group_member_ids = ?,
                                content_preview = CASE WHEN content_preview = '' THEN ? ELSE content_preview END,
                                media_files = ?, media_size = ?,
                                updated_at = ?
                            WHERE dedup_key = ? AND next_target_index = 0
                            """,
                            (
                                int(source_message_id),
                                str(source_chat_name) if source_chat_name else None,
                                sender_id,
                                available_at,
                                settle_until,
                                json.dumps(members),
                                str(content_preview or "")[:500], json.dumps(merged_media, ensure_ascii=False), merged_size,
                                now,
                                dedup_key,
                            ),
                        )
                    elif existing["status"] in ("completed", "failed") and not already_member:
                        # Late member: the album already shipped, so resend the
                        # stragglers as a fresh queue task (same settle window).
                        late_row = conn.execute(
                            """
                            SELECT id, dedup_key, status, group_member_ids, media_files
                            FROM forward_queue
                            WHERE grouped_id = ? AND dedup_key LIKE ?
                            ORDER BY id DESC LIMIT 1
                            """,
                            (group_text, "%:late:%"),
                        ).fetchone()
                        if late_row is not None and late_row["status"] in ("pending", "processing"):
                            target_key = late_row["dedup_key"]
                            late_members = sorted(
                                set(parse_member_ids(late_row["group_member_ids"])
                                    + [int(source_message_id)])
                            )
                            late_media = parse_media_files(late_row["media_files"])
                            late_seen = {item.get("message_id") for item in late_media}
                            for media in normalized_media:
                                if media.get("message_id") not in late_seen:
                                    late_media.append(media)
                            conn.execute(
                                """
                                UPDATE forward_queue
                                SET source_message_id = MIN(source_message_id, ?),
                                    group_member_ids = ?,
                                    content_preview = CASE WHEN content_preview = '' THEN ? ELSE content_preview END,
                                    media_files = ?, media_size = ?,
                                    available_at = CASE WHEN status = 'pending'
                                        THEN MAX(available_at, ?) ELSE available_at END,
                                    group_settle_until = CASE WHEN status = 'pending'
                                        THEN MAX(COALESCE(group_settle_until, 0), ?)
                                        ELSE group_settle_until END,
                                    updated_at = ?
                                WHERE id = ? AND next_target_index = 0
                                """,
                                (
                                    int(source_message_id),
                                    json.dumps(late_members),
                                    str(content_preview or "")[:500], json.dumps(late_media, ensure_ascii=False),
                                    sum(int(item.get("size") or 0) for item in late_media),
                                    available_at,
                                    settle_until,
                                    now,
                                    late_row["id"],
                                ),
                            )
                        else:
                            # No open late task: seed a new resend job.
                            target_key = f"{dedup_key}:late:{int(source_message_id)}"
                            conn.execute(
                                """
                                INSERT OR IGNORE INTO forward_queue
                                (dedup_key, rule_name, rule_data, rule_fingerprint,
                                 source_chat_id, source_chat_name, source_message_id,
                                 sender_id, grouped_id, group_member_ids,
                                 group_settle_until, content_preview, media_files, media_size, status, available_at,
                                 created_at, updated_at)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)
                                """,
                                (
                                    target_key,
                                    str(rule_data.get("name", "")),
                                    encoded_rule,
                                    fingerprint,
                                    int(source_chat_id),
                                    str(source_chat_name) if source_chat_name else None,
                                    int(source_message_id),
                                    sender_id,
                                    group_text,
                                    json.dumps([int(source_message_id)]),
                                    settle_until,
                                    str(content_preview or "")[:500], media_json, max(0, int(media_size or 0)),
                                    available_at,
                                    now,
                                    now,
                                ),
                            )
                            inserted = True
                            logger.warning(
                                t(
                                    "log.forward_queue.media_group_late_resent",
                                    rule=str(rule_data.get("name", "")),
                                    chat=str(source_chat_id),
                                    message_id=int(source_message_id),
                                    group=group_text,
                                )
                            )
            item_id = conn.execute(
                "SELECT id FROM forward_queue WHERE dedup_key = ?", (target_key,)
            ).fetchone()[0]
            return self._get(conn, item_id), inserted

    def update_source_chat_name(self, item_id: int, source_chat_name: str) -> None:
        name = str(source_chat_name).strip()
        if not name:
            return
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE forward_queue
                SET source_chat_name = ?, updated_at = ?
                WHERE id = ?
                """,
                (name, time.time(), item_id),
            )

    def recover_processing(self) -> int:
        """Make jobs left in ``processing`` available after a crash/restart."""
        now = time.time()
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE forward_queue
                SET status = 'pending', available_at = MIN(available_at, ?), updated_at = ?
                WHERE status = 'processing'
                """,
                (now, now),
            )
            return cursor.rowcount

    def claim_next(
        self,
        now: Optional[float] = None,
        *,
        blocked_rule_fingerprints: Optional[set[str]] = None,
        deprioritize_rule: Optional[str] = None,
    ) -> Optional[ForwardQueueItem]:
        now = time.time() if now is None else now
        blocked = sorted(blocked_rule_fingerprints or set())
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            clauses = [
                "status = 'pending'",
                "available_at <= ?",
                "(group_settle_until IS NULL OR group_settle_until <= ?)",
            ]
            params: list[Any] = [now, now]
            if blocked:
                placeholders = ", ".join("?" for _ in blocked)
                clauses.append(f"rule_fingerprint NOT IN ({placeholders})")
                params.extend(blocked)
            params.append(deprioritize_rule or "")
            row = conn.execute(
                f"""
                SELECT * FROM forward_queue
                WHERE {' AND '.join(clauses)}
                ORDER BY CASE WHEN rule_fingerprint = ? THEN 1 ELSE 0 END,
                         available_at ASC, id ASC
                LIMIT 1
                """,
                params,
            ).fetchone()
            if row is None:
                conn.commit()
                return None
            conn.execute(
                """
                UPDATE forward_queue
                SET status = 'processing', attempt_count = attempt_count + 1, updated_at = ?
                WHERE id = ?
                """,
                (now, row["id"]),
            )
            return self._get(conn, row["id"])

    def next_available_at(self) -> Optional[float]:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT MIN(
                    CASE WHEN group_settle_until IS NULL THEN available_at
                         ELSE MAX(available_at, group_settle_until) END
                ) FROM forward_queue WHERE status = 'pending'
                """
            ).fetchone()
            return row[0]

    def get_pause(self) -> tuple[float, Optional[str]]:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT paused_until, pause_reason FROM forward_queue_state WHERE id = 1"
            ).fetchone()
            return float(row[0]), row[1]

    def pause_for(self, seconds: float, reason: str) -> float:
        now = time.time()
        requested_until = now + max(0.0, float(seconds))
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT paused_until FROM forward_queue_state WHERE id = 1"
            ).fetchone()
            paused_until = max(float(row[0]), requested_until)
            conn.execute(
                """
                UPDATE forward_queue SET available_at = MAX(available_at, ?)
                WHERE status = 'pending'
                """,
                (paused_until,),
            )
            conn.execute(
                """
                UPDATE forward_queue_state
                SET paused_until = ?, pause_reason = ?, updated_at = ?
                WHERE id = 1
                """,
                (paused_until, reason, now),
            )
            return paused_until

    def clear_pause_if_expired(self, now: Optional[float] = None) -> None:
        now = time.time() if now is None else now
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE forward_queue_state
                SET paused_until = 0, pause_reason = NULL, updated_at = ?
                WHERE id = 1 AND paused_until <= ?
                """,
                (now, now),
            )

    def update_target_index(self, item_id: int, next_target_index: int) -> None:
        now = time.time()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE forward_queue
                SET next_target_index = MAX(next_target_index, ?), updated_at = ?
                WHERE id = ? AND status = 'processing'
                """,
                (int(next_target_index), now, item_id),
            )

    def reschedule(
        self,
        item_id: int,
        *,
        available_at: float,
        error: str,
        increment_failure: bool = False,
    ) -> None:
        now = time.time()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE forward_queue
                SET status = 'pending', available_at = ?, last_error = ?, updated_at = ?,
                    failure_count = failure_count + ?
                WHERE id = ?
                """,
                (
                    float(available_at),
                    str(error)[:2000],
                    now,
                    int(increment_failure),
                    item_id,
                ),
            )

    def mark_completed(self, item_id: int) -> None:
        now = time.time()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE forward_queue
                SET status = 'completed', completed_at = ?, updated_at = ?, last_error = NULL
                WHERE id = ?
                """,
                (now, now, item_id),
            )

    def mark_failed(self, item_id: int, error: str, *, increment_failure: bool = False) -> None:
        now = time.time()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE forward_queue
                SET status = 'failed', last_error = ?, updated_at = ?,
                    failure_count = failure_count + ?
                WHERE id = ?
                """,
                (str(error)[:2000], now, int(increment_failure), item_id),
            )

    def requeue_processing(self) -> int:
        return self.recover_processing()

    def purge_completed(self, retention_days: int = 7) -> int:
        cutoff = time.time() - max(1, int(retention_days)) * 86400
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM forward_queue WHERE status = 'completed' AND completed_at < ?",
                (cutoff,),
            )
            return cursor.rowcount

    def counts(self) -> dict[str, int]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) AS count FROM forward_queue GROUP BY status"
            ).fetchall()
            return {row["status"]: row["count"] for row in rows}

    def active_count(self) -> int:
        """Return the number of unfinished jobs currently in the queue."""
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) FROM forward_queue
                WHERE status IN ('pending', 'processing')
                """
            ).fetchone()
            return int(row[0])


class ForwardQueue:
    """Single FIFO consumer with durable queue-level backoff."""

    def __init__(
        self,
        store: ForwardQueueStore,
        processor: Callable[[ForwardQueueItem], Awaitable[Optional[float]]],
        *,
        max_retries: int = 5,
        retry_base_seconds: float = 5.0,
        flood_wait_buffer: float = 1.0,
        poll_interval: float = 1.0,
        completed_retention_days: int = 7,
        on_outcome: Callable[[ForwardQueueItem, str, Optional[Exception]], None]
        | None = None,
    ):
        self.store = store
        self.processor = processor
        self.max_retries = max(1, int(max_retries))
        self.retry_base_seconds = max(0.1, float(retry_base_seconds))
        self.flood_wait_buffer = max(0.0, float(flood_wait_buffer))
        self.poll_interval = max(0.05, float(poll_interval))
        self.completed_retention_days = max(1, int(completed_retention_days))
        self.on_outcome = on_outcome
        self._wake = asyncio.Event()
        self._stop = asyncio.Event()
        self._task: Optional[asyncio.Task] = None
        self._rule_next_at: dict[str, float] = {}
        self._last_rule_fingerprint: Optional[str] = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def enqueue(self, **kwargs) -> tuple[ForwardQueueItem, bool]:
        item = self.store.enqueue(**kwargs)
        self._wake.set()
        return item

    def active_count(self) -> int:
        return self.store.active_count()

    @staticmethod
    def _log_fields(item: ForwardQueueItem) -> dict[str, Any]:
        targets = item.rule_data.get("target_chats", []) or []
        target = (
            targets[item.next_target_index]
            if 0 <= item.next_target_index < len(targets)
            else "-"
        )
        return {
            "rule": item.rule_name,
            "chat_id": item.source_chat_id,
            "message_id": item.source_message_id,
            "target": target,
        }

    async def start(self) -> None:
        if self.running:
            return
        recovered = self.store.recover_processing()
        purged = self.store.purge_completed(self.completed_retention_days)
        if recovered or purged:
            logger.info(t("log.forward_queue.restored", recovered=recovered, purged=purged))
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="forward-queue-consumer")

    async def stop(self, timeout: float = 8.0) -> None:
        task = self._task
        if task is None:
            return
        self._stop.set()
        self._wake.set()
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=max(0.1, timeout))
        except asyncio.TimeoutError:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            self.store.requeue_processing()
        finally:
            self._task = None

    async def _wait(self, seconds: float) -> None:
        self._wake.clear()
        try:
            await asyncio.wait_for(self._wake.wait(), timeout=max(0.01, seconds))
        except asyncio.TimeoutError:
            pass

    def _notify_outcome(
        self, item: ForwardQueueItem, status: str, error: Optional[Exception] = None
    ) -> None:
        if not self.on_outcome:
            return
        try:
            self.on_outcome(item, status, error)
        except Exception:
            logger.exception("Forward queue outcome callback failed")

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                await self._run_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                try:
                    self.store.requeue_processing()
                except Exception:
                    logger.exception(t("log.forward_queue.recovery_failed"))
                logger.exception(t("log.forward_queue.loop_error", error=exc))
                await self._wait(self.poll_interval)

    async def _run_once(self) -> None:
        paused_until, _ = self.store.get_pause()
        now = time.time()
        if paused_until > now:
            await self._wait(min(paused_until - now, self.poll_interval))
            return
        self.store.clear_pause_if_expired(now)

        blocked_rules: set[str] = set()
        for fingerprint, available_at in list(self._rule_next_at.items()):
            if available_at > now:
                blocked_rules.add(fingerprint)
            else:
                del self._rule_next_at[fingerprint]
        item = self.store.claim_next(
            now,
            blocked_rule_fingerprints=blocked_rules,
            deprioritize_rule=self._last_rule_fingerprint,
        )
        if item is None:
            next_at = self.store.next_available_at()
            rule_next_at = min(self._rule_next_at.values(), default=None)
            candidates = [value for value in (next_at, rule_next_at) if value is not None]
            delay = self.poll_interval if not candidates else max(
                0.01, min(self.poll_interval, min(candidates) - now)
            )
            await self._wait(delay)
            return

        try:
            post_delay = await self.processor(item)
        except asyncio.CancelledError:
            self.store.requeue_processing()
            raise
        except FloodWaitError as exc:
            seconds = max(1.0, float(getattr(exc, "seconds", 1))) + self.flood_wait_buffer
            paused = self.store.pause_for(seconds, str(exc))
            self.store.reschedule(item.id, available_at=paused, error=str(exc))
            logger.warning(
                t(
                    "log.forward_queue.paused",
                    seconds=seconds,
                    **self._log_fields(item),
                )
            )
            self._notify_outcome(item, "delayed", exc)
        except Exception as exc:
            failure_count = item.failure_count + 1
            if failure_count >= self.max_retries:
                self.store.mark_failed(item.id, str(exc), increment_failure=True)
                logger.error(
                    t(
                        "log.forward_queue.failed",
                        attempts=failure_count,
                        error=exc,
                        **self._log_fields(item),
                    )
                )
                self._notify_outcome(item, "failed", exc)
            else:
                delay = min(
                    3600.0,
                    self.retry_base_seconds * (2 ** max(0, failure_count - 1)),
                )
                self.store.reschedule(
                    item.id,
                    available_at=time.time() + delay,
                    error=str(exc),
                    increment_failure=True,
                )
                logger.warning(
                    t(
                        "log.forward_queue.retry",
                        seconds=delay,
                        error=exc,
                        **self._log_fields(item),
                    )
                )
                self._notify_outcome(item, "retrying", exc)
        else:
            self.store.mark_completed(item.id)
            self._notify_outcome(item, "completed")
            self._last_rule_fingerprint = item.rule_fingerprint
            if post_delay:
                self._rule_next_at[item.rule_fingerprint] = time.time() + float(post_delay)
