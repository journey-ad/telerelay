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
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from sqlalchemy import case, delete, func, inspect, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from telethon.errors import FloodWaitError

from backend.database import (
    Base,
    ForwardQueueRow,
    ForwardQueueState,
    create_sqlite_engine,
    session_factory,
    session_scope,
)
from backend.i18n import t
from backend.logger import get_logger

logger = get_logger()


class QueueItemCancelled(Exception):
    """Raised when a queue item is cancelled while it is being processed."""


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
        self.engine = create_sqlite_engine(self.db_path)
        self._session_factory = session_factory(self.engine)
        self._init_db()

    def _session(self):
        return session_scope(self._session_factory)

    def _init_db(self) -> None:
        with self._lock:
            Base.metadata.create_all(
                self.engine, tables=[ForwardQueueRow.__table__, ForwardQueueState.__table__]
            )
            inspector = inspect(self.engine)
            columns = {column["name"] for column in inspector.get_columns("forward_queue")}
            additions = {
                "failure_count": "INTEGER NOT NULL DEFAULT 0",
                "group_member_ids": "TEXT",
                "group_settle_until": "REAL",
                "source_chat_name": "TEXT",
                "content_preview": "TEXT NOT NULL DEFAULT ''",
                "media_files": "TEXT NOT NULL DEFAULT '[]'",
                "media_size": "INTEGER NOT NULL DEFAULT 0",
                "cancel_requested": "INTEGER NOT NULL DEFAULT 0",
            }
            with self.engine.begin() as connection:
                connection.exec_driver_sql("PRAGMA journal_mode = WAL")
                for name, definition in additions.items():
                    if name not in columns:
                        connection.exec_driver_sql(
                            f"ALTER TABLE forward_queue ADD COLUMN {name} {definition}"
                        )
            with self._session() as session:
                if session.get(ForwardQueueState, 1) is None:
                    session.add(ForwardQueueState(id=1, paused_until=0, updated_at=0))
        try:
            self.db_path.chmod(0o600)
        except OSError:
            pass

    @staticmethod
    def _row_to_item(row: ForwardQueueRow) -> ForwardQueueItem:
        member_ids = parse_member_ids(row.group_member_ids)
        media_files = parse_media_files(row.media_files)
        return ForwardQueueItem(
            id=row.id,
            dedup_key=row.dedup_key,
            rule_name=row.rule_name,
            rule_data=json.loads(row.rule_data),
            rule_fingerprint=row.rule_fingerprint,
            source_chat_id=row.source_chat_id,
            source_chat_name=row.source_chat_name,
            source_message_id=row.source_message_id,
            sender_id=row.sender_id,
            grouped_id=row.grouped_id,
            group_member_ids=tuple(member_ids) if member_ids else None,
            group_settle_until=row.group_settle_until,
            status=row.status,
            attempt_count=row.attempt_count,
            failure_count=row.failure_count,
            next_target_index=row.next_target_index,
            available_at=row.available_at,
            last_error=row.last_error,
            created_at=row.created_at,
            updated_at=row.updated_at,
            content_preview=row.content_preview or "",
            media_files=tuple(media_files),
            media_size=int(row.media_size or 0),
        )

    def _get(self, session, item_id: int) -> ForwardQueueItem:
        row = session.get(ForwardQueueRow, int(item_id))
        if row is None:
            raise KeyError(f"Forward queue item {item_id} does not exist")
        return self._row_to_item(row)

    def get_item(self, item_id: int) -> ForwardQueueItem:
        with self._lock, self._session() as session:
            return self._get(session, item_id)

    def delete_item(self, item_id: int) -> bool:
        """Remove an unfinished queue item.

        Pending items are removed immediately. Processing items are marked for
        cancellation so the active sender can stop before its next target.
        Completed and failed items remain available for retention and history.
        """
        with self._lock, self._session() as session:
            deleted = session.execute(
                delete(ForwardQueueRow).where(
                    ForwardQueueRow.id == int(item_id), ForwardQueueRow.status == "pending"
                )
            ).rowcount
            if deleted == 1:
                return True
            updated = session.execute(
                update(ForwardQueueRow)
                .where(
                    ForwardQueueRow.id == int(item_id),
                    ForwardQueueRow.status == "processing",
                    ForwardQueueRow.cancel_requested.is_(False),
                )
                .values(cancel_requested=True, updated_at=time.time())
            ).rowcount
            return updated == 1

    def is_cancel_requested(self, item_id: int) -> bool:
        with self._lock, self._session() as session:
            row = session.scalar(
                select(ForwardQueueRow.cancel_requested).where(ForwardQueueRow.id == int(item_id))
            )
            return bool(row)

    def remove_item(self, item_id: int) -> None:
        """Remove a cancelled processing item after its worker exits."""
        with self._lock, self._session() as session:
            session.execute(delete(ForwardQueueRow).where(ForwardQueueRow.id == int(item_id)))

    def list_active(self, limit: int = 50) -> list[ForwardQueueItem]:
        return self.list_active_page(limit, 0)[0]

    def list_active_page(self, limit: int = 50, offset: int = 0) -> tuple[list[ForwardQueueItem], int]:
        """Return a page and total count of unfinished queue items."""
        with self._lock, self._session() as session:
            bounded_limit = max(1, min(int(limit), 100))
            bounded_offset = max(0, int(offset))
            active = (ForwardQueueRow.status == "pending") | (
                (ForwardQueueRow.status == "processing")
                & ForwardQueueRow.cancel_requested.is_(False)
            )
            total = session.scalar(select(func.count()).select_from(ForwardQueueRow).where(active)) or 0
            rows = session.scalars(
                select(ForwardQueueRow)
                .where(active)
                .order_by(
                    case((ForwardQueueRow.status == "processing", 0), else_=1),
                    ForwardQueueRow.available_at,
                    ForwardQueueRow.id,
                )
                .limit(bounded_limit)
                .offset(bounded_offset)
            ).all()
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

        with self._lock, self._session() as session:
            values = {
                "dedup_key": dedup_key,
                "rule_name": str(rule_data.get("name", "")),
                "rule_data": encoded_rule,
                "rule_fingerprint": fingerprint,
                "source_chat_id": int(source_chat_id),
                "source_chat_name": str(source_chat_name) if source_chat_name else None,
                "source_message_id": int(source_message_id),
                "sender_id": sender_id,
                "grouped_id": group_text,
                "group_member_ids": members_json,
                "group_settle_until": settle_until,
                "content_preview": str(content_preview or "")[:500],
                "media_files": media_json,
                "media_size": max(0, int(media_size or 0)),
                "status": "pending",
                "available_at": available_at,
                "created_at": now,
                "updated_at": now,
            }
            insert = sqlite_insert(ForwardQueueRow).values(**values).prefix_with("OR IGNORE")
            result = session.execute(insert)
            inserted = result.rowcount == 1
            target_key = dedup_key
            if not inserted and group_text is not None:
                # Album updates arrive separately; wait for the group to settle.
                existing = session.scalar(
                    select(ForwardQueueRow).where(ForwardQueueRow.dedup_key == dedup_key)
                )
                if existing is not None:
                    existing_members = parse_member_ids(existing.group_member_ids)
                    already_member = int(source_message_id) in existing_members
                    if existing.status in ("pending", "processing") and not already_member:
                        # Normal case: fold the member in and extend the settle window.
                        members = sorted(set(existing_members + [int(source_message_id)]))
                        merged_media = parse_media_files(existing.media_files)
                        seen_media = {item.get("message_id") for item in merged_media}
                        for media in normalized_media:
                            if media.get("message_id") not in seen_media:
                                merged_media.append(media)
                        merged_size = sum(int(item.get("size") or 0) for item in merged_media)
                        if existing.next_target_index == 0:
                            existing.source_message_id = min(existing.source_message_id, int(source_message_id))
                            existing.source_chat_name = str(source_chat_name) if source_chat_name else existing.source_chat_name
                            existing.sender_id = existing.sender_id or sender_id
                            if existing.status == "pending":
                                existing.available_at = max(existing.available_at, available_at)
                                existing.group_settle_until = max(existing.group_settle_until or 0, settle_until or 0)
                            existing.group_member_ids = json.dumps(members)
                            existing.content_preview = existing.content_preview or str(content_preview or "")[:500]
                            existing.media_files = json.dumps(merged_media, ensure_ascii=False)
                            existing.media_size = merged_size
                            existing.updated_at = now
                    elif existing.status in ("completed", "failed") and not already_member:
                        # Late member: the album already shipped, so resend the
                        # stragglers as a fresh queue task (same settle window).
                        late_row = session.scalar(
                            select(ForwardQueueRow)
                            .where(
                                ForwardQueueRow.grouped_id == group_text,
                                ForwardQueueRow.dedup_key.like("%:late:%"),
                            )
                            .order_by(ForwardQueueRow.id.desc())
                            .limit(1)
                        )
                        if late_row is not None and late_row.status in ("pending", "processing"):
                            target_key = late_row.dedup_key
                            late_members = sorted(
                                set(parse_member_ids(late_row.group_member_ids)
                                    + [int(source_message_id)])
                            )
                            late_media = parse_media_files(late_row.media_files)
                            late_seen = {item.get("message_id") for item in late_media}
                            for media in normalized_media:
                                if media.get("message_id") not in late_seen:
                                    late_media.append(media)
                            if late_row.next_target_index == 0:
                                late_row.source_message_id = min(late_row.source_message_id, int(source_message_id))
                                late_row.group_member_ids = json.dumps(late_members)
                                late_row.content_preview = late_row.content_preview or str(content_preview or "")[:500]
                                late_row.media_files = json.dumps(late_media, ensure_ascii=False)
                                late_row.media_size = sum(int(item.get("size") or 0) for item in late_media)
                                if late_row.status == "pending":
                                    late_row.available_at = max(late_row.available_at, available_at)
                                    late_row.group_settle_until = max(late_row.group_settle_until or 0, settle_until or 0)
                                late_row.updated_at = now
                        else:
                            # No open late task: seed a new resend job.
                            target_key = f"{dedup_key}:late:{int(source_message_id)}"
                            session.execute(
                                sqlite_insert(ForwardQueueRow)
                                .values(**{**values, "dedup_key": target_key, "group_member_ids": json.dumps([int(source_message_id)])})
                                .prefix_with("OR IGNORE")
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
            item = session.scalar(select(ForwardQueueRow).where(ForwardQueueRow.dedup_key == target_key))
            if item is None:
                raise KeyError(f"Forward queue item for {target_key} does not exist")
            return self._row_to_item(item), inserted

    def update_source_chat_name(self, item_id: int, source_chat_name: str) -> None:
        name = str(source_chat_name).strip()
        if not name:
            return
        with self._lock, self._session() as session:
            session.execute(
                update(ForwardQueueRow)
                .where(ForwardQueueRow.id == int(item_id))
                .values(source_chat_name=name, updated_at=time.time())
            )

    def recover_processing(self) -> int:
        """Make jobs left in ``processing`` available after a crash/restart."""
        now = time.time()
        with self._lock, self._session() as session:
            session.execute(
                delete(ForwardQueueRow).where(
                    ForwardQueueRow.status == "processing",
                    ForwardQueueRow.cancel_requested.is_(True),
                )
            )
            result = session.execute(
                update(ForwardQueueRow)
                .where(ForwardQueueRow.status == "processing")
                .values(
                    status="pending",
                    available_at=func.min(ForwardQueueRow.available_at, now),
                    updated_at=now,
                )
            )
            return result.rowcount

    def claim_next(
        self,
        now: Optional[float] = None,
        *,
        blocked_rule_fingerprints: Optional[set[str]] = None,
        deprioritize_rule: Optional[str] = None,
    ) -> Optional[ForwardQueueItem]:
        now = time.time() if now is None else now
        blocked = sorted(blocked_rule_fingerprints or set())
        with self._lock, self._session() as session:
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            statement = select(ForwardQueueRow).where(
                ForwardQueueRow.status == "pending",
                ForwardQueueRow.cancel_requested.is_(False),
                ForwardQueueRow.available_at <= now,
                (ForwardQueueRow.group_settle_until.is_(None))
                | (ForwardQueueRow.group_settle_until <= now),
            )
            if blocked:
                statement = statement.where(~ForwardQueueRow.rule_fingerprint.in_(blocked))
            statement = statement.order_by(
                (ForwardQueueRow.rule_fingerprint == (deprioritize_rule or "")).asc(),
                ForwardQueueRow.available_at,
                ForwardQueueRow.id,
            ).limit(1)
            row = session.scalar(statement)
            if row is None:
                return None
            row.status = "processing"
            row.attempt_count += 1
            row.updated_at = now
            session.flush()
            return self._row_to_item(row)

    def next_available_at(self) -> Optional[float]:
        with self._lock, self._session() as session:
            value = session.scalar(
                select(
                    func.min(
                        func.max(
                            ForwardQueueRow.available_at,
                            func.coalesce(ForwardQueueRow.group_settle_until, 0),
                        )
                    )
                ).where(ForwardQueueRow.status == "pending")
            )
            return value

    def get_pause(self) -> tuple[float, Optional[str]]:
        with self._lock, self._session() as session:
            row = session.get(ForwardQueueState, 1)
            return (float(row.paused_until), row.pause_reason) if row else (0.0, None)

    def pause_for(self, seconds: float, reason: str) -> float:
        now = time.time()
        requested_until = now + max(0.0, float(seconds))
        with self._lock, self._session() as session:
            state = session.get(ForwardQueueState, 1)
            paused_until = max(float(state.paused_until if state else 0), requested_until)
            session.execute(
                update(ForwardQueueRow)
                .where(ForwardQueueRow.status == "pending")
                .values(available_at=func.max(ForwardQueueRow.available_at, paused_until))
            )
            if state is None:
                state = ForwardQueueState(id=1, paused_until=paused_until, pause_reason=reason, updated_at=now)
                session.add(state)
            else:
                state.paused_until = paused_until
                state.pause_reason = reason
                state.updated_at = now
            return paused_until

    def clear_pause_if_expired(self, now: Optional[float] = None) -> None:
        now = time.time() if now is None else now
        with self._lock, self._session() as session:
            session.execute(
                update(ForwardQueueState)
                .where(ForwardQueueState.id == 1, ForwardQueueState.paused_until <= now)
                .values(paused_until=0, pause_reason=None, updated_at=now)
            )

    def update_target_index(self, item_id: int, next_target_index: int) -> None:
        now = time.time()
        with self._lock, self._session() as session:
            session.execute(
                update(ForwardQueueRow)
                .where(ForwardQueueRow.id == int(item_id), ForwardQueueRow.status == "processing")
                .values(
                    next_target_index=func.max(ForwardQueueRow.next_target_index, int(next_target_index)),
                    updated_at=now,
                )
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
        with self._lock, self._session() as session:
            session.execute(
                update(ForwardQueueRow)
                .where(ForwardQueueRow.id == int(item_id))
                .values(
                    status="pending",
                    available_at=float(available_at),
                    last_error=str(error)[:2000],
                    updated_at=now,
                    failure_count=ForwardQueueRow.failure_count + int(increment_failure),
                )
            )

    def mark_completed(self, item_id: int) -> None:
        now = time.time()
        with self._lock, self._session() as session:
            session.execute(
                update(ForwardQueueRow)
                .where(ForwardQueueRow.id == int(item_id))
                .values(status="completed", completed_at=now, updated_at=now, last_error=None)
            )

    def mark_failed(self, item_id: int, error: str, *, increment_failure: bool = False) -> None:
        now = time.time()
        with self._lock, self._session() as session:
            session.execute(
                update(ForwardQueueRow)
                .where(ForwardQueueRow.id == int(item_id))
                .values(
                    status="failed",
                    last_error=str(error)[:2000],
                    updated_at=now,
                    failure_count=ForwardQueueRow.failure_count + int(increment_failure),
                )
            )

    def requeue_processing(self) -> int:
        return self.recover_processing()

    def purge_completed(self, retention_days: int = 7) -> int:
        cutoff = time.time() - max(1, int(retention_days)) * 86400
        with self._lock, self._session() as session:
            result = session.execute(
                delete(ForwardQueueRow).where(
                    ForwardQueueRow.status == "completed", ForwardQueueRow.completed_at < cutoff
                )
            )
            return result.rowcount

    def counts(self) -> dict[str, int]:
        with self._lock, self._session() as session:
            active = (ForwardQueueRow.status != "processing") | ForwardQueueRow.cancel_requested.is_(False)
            rows = session.execute(
                select(ForwardQueueRow.status, func.count())
                .where(active)
                .group_by(ForwardQueueRow.status)
            ).all()
            return {status: count for status, count in rows}

    def active_count(self) -> int:
        """Return the number of unfinished jobs currently in the queue."""
        with self._lock, self._session() as session:
            active = (ForwardQueueRow.status == "pending") | (
                (ForwardQueueRow.status == "processing")
                & ForwardQueueRow.cancel_requested.is_(False)
            )
            return int(session.scalar(select(func.count()).select_from(ForwardQueueRow).where(active)) or 0)


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
            if self.store.is_cancel_requested(item.id):
                self.store.remove_item(item.id)
                return
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
        except QueueItemCancelled:
            self.store.remove_item(item.id)
        except Exception as exc:
            if self.store.is_cancel_requested(item.id):
                self.store.remove_item(item.id)
                return
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
