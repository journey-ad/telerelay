"""Per-chat SQLite storage used as the canonical message export source."""

from __future__ import annotations

import base64
import json
import os
import sqlite3
import tempfile
import threading
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = 1

MESSAGE_COLUMNS = (
    "message_id",
    "chat_id",
    "chat_title",
    "date",
    "date_utc",
    "sender_id",
    "sender_type",
    "sender_name",
    "sender_username",
    "sender_first_name",
    "sender_last_name",
    "sender_is_bot",
    "sender_phone",
    "sender_is_verified",
    "sender_is_premium",
    "sender_is_scam",
    "sender_is_fake",
    "sender_is_contact",
    "sender_is_mutual_contact",
    "text",
    "media_type",
    "content",
    "reply_to_message_id",
    "reply_to_top_id",
    "edited_at",
    "edited_at_utc",
    "grouped_id",
    "forward_from_id",
    "forward_from_name",
    "forward_date",
    "forward_date_utc",
    "via_bot_id",
    "post_author",
    "views",
    "forwards",
    "replies_count",
    "media_id",
    "media_mime_type",
    "media_file_name",
    "media_size",
    "media_duration",
    "service_action",
    "is_outgoing",
    "is_mentioned",
    "is_media_unread",
    "is_silent",
    "is_post",
    "is_from_scheduled",
    "is_pinned",
    "is_forwarding_restricted",
    "entities_json",
    "reactions_json",
    "reply_markup_json",
    "restriction_reason_json",
    "sender_json",
    "record_json",
    "raw_json",
    "fetched_at",
)

JSON_FIELDS = {
    "entities": "entities_json",
    "reactions": "reactions_json",
    "reply_markup": "reply_markup_json",
    "restriction_reason": "restriction_reason_json",
}
JSON_COLUMNS = {column: field for field, column in JSON_FIELDS.items()}

BOOLEAN_FIELDS = {
    "sender_is_bot",
    "sender_is_verified",
    "sender_is_premium",
    "sender_is_scam",
    "sender_is_fake",
    "sender_is_contact",
    "sender_is_mutual_contact",
    "is_outgoing",
    "is_mentioned",
    "is_media_unread",
    "is_silent",
    "is_post",
    "is_from_scheduled",
    "is_pinned",
    "is_forwarding_restricted",
}


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    if isinstance(value, bytes):
        return {"_bytes_base64": base64.b64encode(value).decode("ascii")}
    if hasattr(value, "to_dict"):
        return value.to_dict()
    return str(value)


def _json_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        default=_json_default,
    )


def _parse_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _utc_text(value: Any) -> Optional[str]:
    parsed = _parse_datetime(value)
    if parsed is None:
        return None
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")


def _localized_text(value: Any, output_timezone) -> Optional[str]:
    parsed = _parse_datetime(value)
    if parsed is None:
        return None
    return parsed.astimezone(output_timezone).isoformat(timespec="seconds")


class MessageArchiveStore:
    """Store one Telegram chat per database for idempotent incremental sync."""

    def __init__(self, root: Path, chat_id: int):
        self.root = Path(root).expanduser()
        self.root.mkdir(parents=True, exist_ok=True)
        self.chat_id = int(chat_id)
        self.path = self.root / f"msg_export_{self.chat_id}.sqlite3"
        if self.path.is_symlink():
            raise ValueError(
                f"Message archive database cannot be a symlink: {self.path}"
            )
        self._lock = threading.RLock()
        self._init_db()
        os.chmod(self.path, 0o600)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 30000")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS archive_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    message_id INTEGER NOT NULL,
                    chat_id INTEGER NOT NULL,
                    chat_title TEXT NOT NULL,
                    date TEXT NOT NULL,
                    date_utc TEXT NOT NULL,
                    sender_id INTEGER,
                    sender_type TEXT,
                    sender_name TEXT,
                    sender_username TEXT,
                    sender_first_name TEXT,
                    sender_last_name TEXT,
                    sender_is_bot INTEGER,
                    sender_phone TEXT,
                    sender_is_verified INTEGER,
                    sender_is_premium INTEGER,
                    sender_is_scam INTEGER,
                    sender_is_fake INTEGER,
                    sender_is_contact INTEGER,
                    sender_is_mutual_contact INTEGER,
                    text TEXT NOT NULL DEFAULT '',
                    media_type TEXT NOT NULL DEFAULT 'text',
                    content TEXT NOT NULL DEFAULT '',
                    reply_to_message_id INTEGER,
                    reply_to_top_id INTEGER,
                    edited_at TEXT,
                    edited_at_utc TEXT,
                    grouped_id INTEGER,
                    forward_from_id INTEGER,
                    forward_from_name TEXT,
                    forward_date TEXT,
                    forward_date_utc TEXT,
                    via_bot_id INTEGER,
                    post_author TEXT,
                    views INTEGER,
                    forwards INTEGER,
                    replies_count INTEGER,
                    media_id INTEGER,
                    media_mime_type TEXT,
                    media_file_name TEXT,
                    media_size INTEGER,
                    media_duration REAL,
                    service_action TEXT,
                    is_outgoing INTEGER,
                    is_mentioned INTEGER,
                    is_media_unread INTEGER,
                    is_silent INTEGER,
                    is_post INTEGER,
                    is_from_scheduled INTEGER,
                    is_pinned INTEGER,
                    is_forwarding_restricted INTEGER,
                    entities_json TEXT,
                    reactions_json TEXT,
                    reply_markup_json TEXT,
                    restriction_reason_json TEXT,
                    sender_json TEXT,
                    record_json TEXT NOT NULL,
                    raw_json TEXT,
                    fetched_at TEXT NOT NULL,
                    PRIMARY KEY (chat_id, message_id)
                );
                CREATE INDEX IF NOT EXISTS idx_messages_date
                    ON messages(date_utc, message_id);
                CREATE INDEX IF NOT EXISTS idx_messages_sender
                    ON messages(sender_id);
                CREATE INDEX IF NOT EXISTS idx_messages_reply
                    ON messages(reply_to_message_id);
                """
            )
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            conn.execute(
                """
                INSERT INTO archive_metadata(key, value) VALUES('schema_version', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (str(SCHEMA_VERSION),),
            )

    @staticmethod
    def _column_values(record: Mapping[str, Any], fetched_at: str) -> Dict[str, Any]:
        data = dict(record)
        raw = data.pop("raw", None)
        sender_raw = data.pop("sender_raw", None)
        date_utc = _utc_text(data.get("date_utc") or data.get("date"))
        if date_utc is None:
            raise ValueError("A message date is required for SQLite export")
        data["date_utc"] = date_utc
        data["edited_at_utc"] = _utc_text(
            data.get("edited_at_utc") or data.get("edited_at")
        )
        data["forward_date_utc"] = _utc_text(
            data.get("forward_date_utc") or data.get("forward_date")
        )

        values: Dict[str, Any] = {}
        for column in MESSAGE_COLUMNS:
            if column == "record_json":
                values[column] = _json_text(data)
            elif column == "raw_json":
                values[column] = _json_text(raw)
            elif column == "sender_json":
                values[column] = _json_text(sender_raw)
            elif column == "fetched_at":
                values[column] = fetched_at
            elif column in JSON_COLUMNS:
                values[column] = _json_text(data.get(JSON_COLUMNS[column]))
            elif column in BOOLEAN_FIELDS:
                value = data.get(column)
                values[column] = None if value is None else int(bool(value))
            else:
                values[column] = data.get(column)
        values["date"] = str(data.get("date") or date_utc)
        values["date_utc"] = date_utc
        values["chat_title"] = str(data.get("chat_title") or data.get("chat_id") or "")
        values["text"] = str(data.get("text") or "")
        values["media_type"] = str(data.get("media_type") or "text")
        values["content"] = str(data.get("content") or data.get("text") or "")
        return values

    def upsert(self, records: Iterable[Mapping[str, Any]]) -> int:
        fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        rows = [self._column_values(record, fetched_at) for record in records]
        if not rows:
            return 0
        for row in rows:
            if int(row["chat_id"]) != self.chat_id:
                raise ValueError(
                    f"Message chat_id {row['chat_id']} does not match "
                    f"archive {self.chat_id}"
                )

        columns = ", ".join(MESSAGE_COLUMNS)
        placeholders = ", ".join("?" for _ in MESSAGE_COLUMNS)
        updates = ", ".join(
            f"{column} = excluded.{column}"
            for column in MESSAGE_COLUMNS
            if column not in {"chat_id", "message_id"}
        )
        values = [tuple(row[column] for column in MESSAGE_COLUMNS) for row in rows]
        with self._lock, self._connect() as conn:
            conn.executemany(
                f"""
                INSERT INTO messages ({columns}) VALUES ({placeholders})
                ON CONFLICT(chat_id, message_id) DO UPDATE SET {updates}
                """,
                values,
            )
            title = str(rows[-1]["chat_title"])
            for key, value in (
                ("chat_id", str(self.chat_id)),
                ("chat_title", title),
                ("updated_at", fetched_at),
            ):
                conn.execute(
                    """
                    INSERT INTO archive_metadata(key, value) VALUES(?, ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    (key, value),
                )
        os.chmod(self.path, 0o600)
        return len(rows)

    def list_records(
        self,
        *,
        start_at: datetime,
        end_at: datetime,
        output_timezone,
    ) -> List[Dict[str, Any]]:
        start_text = _utc_text(start_at)
        end_text = _utc_text(end_at)
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT record_json, raw_json, sender_json,
                       date_utc, edited_at_utc, forward_date_utc
                FROM messages
                WHERE chat_id = ? AND date_utc >= ? AND date_utc <= ?
                ORDER BY date_utc, message_id
                """,
                (self.chat_id, start_text, end_text),
            ).fetchall()

        records: List[Dict[str, Any]] = []
        for row in rows:
            record = json.loads(row["record_json"])
            record["date_utc"] = row["date_utc"]
            record["date"] = _localized_text(row["date_utc"], output_timezone)
            record["edited_at_utc"] = row["edited_at_utc"]
            record["edited_at"] = _localized_text(
                row["edited_at_utc"], output_timezone
            )
            record["forward_date_utc"] = row["forward_date_utc"]
            record["forward_date"] = _localized_text(
                row["forward_date_utc"], output_timezone
            )
            if row["raw_json"]:
                record["raw"] = json.loads(row["raw_json"])
            if row["sender_json"]:
                record["sender_raw"] = json.loads(row["sender_json"])
            records.append(record)
        return records

    def count(self) -> int:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE chat_id = ?",
                (self.chat_id,),
            ).fetchone()
        return int(row[0])

    def backup_to(self, destination: Path) -> Path:
        """Write a consistent database snapshot to an export directory."""
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.resolve() == self.path.resolve():
            return self.path

        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
        )
        os.close(file_descriptor)
        temporary_path = Path(temporary_name)
        try:
            with self._lock, self._connect() as source:
                with sqlite3.connect(str(temporary_path), timeout=30) as target:
                    source.backup(target)
            os.chmod(temporary_path, 0o600)
            os.replace(temporary_path, destination)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise
        return destination

    def get_metadata(self, key: str) -> Optional[str]:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM archive_metadata WHERE key = ?",
                (str(key),),
            ).fetchone()
        return str(row[0]) if row is not None else None

    def set_metadata(self, key: str, value: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO archive_metadata(key, value) VALUES(?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (str(key), str(value)),
            )
