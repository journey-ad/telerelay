"""Shared SQLAlchemy models and SQLite session helpers."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class RuleStats(Base):
    __tablename__ = "rule_stats"

    rule_name: Mapped[str] = mapped_column(String, primary_key=True)
    forwarded_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    filtered_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class ForwardedMessage(Base):
    __tablename__ = "forwarded_messages"
    __table_args__ = (
        Index("idx_fm_forwarded_at", "forwarded_at"),
        Index("idx_fm_rule", "rule_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_name: Mapped[str] = mapped_column(String, nullable=False)
    message_id: Mapped[int | None] = mapped_column(Integer)
    source_chat_id: Mapped[int | None] = mapped_column(Integer)
    source_chat_name: Mapped[str | None] = mapped_column(String)
    sender_id: Mapped[int | None] = mapped_column(Integer)
    sender_name: Mapped[str | None] = mapped_column(String)
    sender_first_name: Mapped[str | None] = mapped_column(String)
    sender_last_name: Mapped[str | None] = mapped_column(String)
    sender_username: Mapped[str | None] = mapped_column(String)
    content: Mapped[str | None] = mapped_column(Text)
    media_type: Mapped[str | None] = mapped_column(String)
    entities_json: Mapped[str | None] = mapped_column(Text)
    forwarded_at: Mapped[str | None] = mapped_column(String)


class DailyStat(Base):
    __tablename__ = "daily_stats"
    __table_args__ = (
        UniqueConstraint("rule_name", "date"),
        Index("idx_ds_date", "date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_name: Mapped[str] = mapped_column(String, nullable=False)
    date: Mapped[str] = mapped_column(String, nullable=False)
    forwarded_count: Mapped[int] = mapped_column(Integer, default=0)
    filtered_count: Mapped[int] = mapped_column(Integer, default=0)


class HourlyStat(Base):
    __tablename__ = "hourly_stats"
    __table_args__ = (
        UniqueConstraint("rule_name", "hour"),
        Index("idx_hs_hour", "hour"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_name: Mapped[str] = mapped_column(String, nullable=False)
    hour: Mapped[str] = mapped_column(String, nullable=False)
    forwarded_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    filtered_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class ButtonActionStat(Base):
    __tablename__ = "button_action_stats"

    rule_name: Mapped[str] = mapped_column(String, primary_key=True)
    trigger_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class ButtonActionHourly(Base):
    __tablename__ = "button_action_hourly"
    __table_args__ = (
        UniqueConstraint("rule_name", "hour"),
        Index("idx_bah_hour", "hour"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_name: Mapped[str] = mapped_column(String, nullable=False)
    hour: Mapped[str] = mapped_column(String, nullable=False)
    trigger_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class ForwardQueueRow(Base):
    __tablename__ = "forward_queue"
    __table_args__ = (
        Index("idx_forward_queue_ready", "status", "available_at", "id"),
        Index("idx_forward_queue_status", "status", "updated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dedup_key: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    rule_name: Mapped[str] = mapped_column(String, nullable=False)
    rule_data: Mapped[str] = mapped_column(Text, nullable=False)
    rule_fingerprint: Mapped[str] = mapped_column(String, nullable=False)
    source_chat_id: Mapped[int] = mapped_column(Integer, nullable=False)
    source_chat_name: Mapped[str | None] = mapped_column(String)
    source_message_id: Mapped[int] = mapped_column(Integer, nullable=False)
    sender_id: Mapped[int | None] = mapped_column(Integer)
    grouped_id: Mapped[str | None] = mapped_column(String)
    group_member_ids: Mapped[str | None] = mapped_column(Text)
    group_settle_until: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String, default="pending", nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failure_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_target_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    available_at: Mapped[float] = mapped_column(Float, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[float] = mapped_column(Float, nullable=False)
    completed_at: Mapped[float | None] = mapped_column(Float)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    content_preview: Mapped[str] = mapped_column(Text, default="", nullable=False)
    media_files: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    media_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class ForwardQueueState(Base):
    __tablename__ = "forward_queue_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    paused_until: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    pause_reason: Mapped[str | None] = mapped_column(String)
    updated_at: Mapped[float] = mapped_column(Float, nullable=False)


class Subscriber(Base):
    __tablename__ = "subscribers"
    __table_args__ = (Index("idx_subscribers_status", "status"),)

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str | None] = mapped_column(String)
    first_name: Mapped[str | None] = mapped_column(String)
    last_name: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="active", nullable=False)
    delivered_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    first_seen_at: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[float] = mapped_column(Float, nullable=False)


class ExportTaskRow(Base):
    __tablename__ = "export_tasks"
    __table_args__ = (Index("idx_export_tasks_enabled", "enabled"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    chat_id: Mapped[int] = mapped_column(Integer, nullable=False)
    chat_title: Mapped[str] = mapped_column(String, nullable=False)
    initial_start_at: Mapped[str] = mapped_column(String, nullable=False)
    formats: Mapped[str] = mapped_column(Text, nullable=False)
    subdirectory: Mapped[str] = mapped_column(String, nullable=False)
    schedule_type: Mapped[str] = mapped_column(String, nullable=False)
    minute: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    hour: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    weekday: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    timezone: Mapped[str] = mapped_column(String, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_message_id: Mapped[int | None] = mapped_column(Integer)
    last_success_at: Mapped[str | None] = mapped_column(String)
    next_run_at: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)


class ExportRunRow(Base):
    __tablename__ = "export_runs"
    __table_args__ = (
        Index("idx_export_runs_started_at", "started_at"),
        Index("idx_export_runs_task", "task_id", "started_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("export_tasks.id", ondelete="SET NULL")
    )
    run_type: Mapped[str] = mapped_column(String, nullable=False)
    chat_id: Mapped[int | None] = mapped_column(Integer)
    chat_title: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, nullable=False)
    range_start: Mapped[str | None] = mapped_column(String)
    range_end: Mapped[str | None] = mapped_column(String)
    message_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    files: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[str] = mapped_column(String, nullable=False)
    finished_at: Mapped[str | None] = mapped_column(String)


class ArchiveMetadata(Base):
    __tablename__ = "archive_metadata"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)


class MessageArchiveRecord(Base):
    __tablename__ = "messages"
    __table_args__ = (
        Index("idx_messages_date", "date_utc", "message_id"),
        Index("idx_messages_sender", "sender_id"),
        Index("idx_messages_reply", "reply_to_message_id"),
    )

    message_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_title: Mapped[str] = mapped_column(String, nullable=False)
    date: Mapped[str] = mapped_column(String, nullable=False)
    date_utc: Mapped[str] = mapped_column(String, nullable=False)
    sender_id: Mapped[int | None] = mapped_column(Integer)
    sender_type: Mapped[str | None] = mapped_column(String)
    sender_name: Mapped[str | None] = mapped_column(String)
    sender_username: Mapped[str | None] = mapped_column(String)
    sender_first_name: Mapped[str | None] = mapped_column(String)
    sender_last_name: Mapped[str | None] = mapped_column(String)
    sender_is_bot: Mapped[bool | None] = mapped_column(Boolean)
    sender_phone: Mapped[str | None] = mapped_column(String)
    sender_is_verified: Mapped[bool | None] = mapped_column(Boolean)
    sender_is_premium: Mapped[bool | None] = mapped_column(Boolean)
    sender_is_scam: Mapped[bool | None] = mapped_column(Boolean)
    sender_is_fake: Mapped[bool | None] = mapped_column(Boolean)
    sender_is_contact: Mapped[bool | None] = mapped_column(Boolean)
    sender_is_mutual_contact: Mapped[bool | None] = mapped_column(Boolean)
    text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    media_type: Mapped[str] = mapped_column(String, default="text", nullable=False)
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    reply_to_message_id: Mapped[int | None] = mapped_column(Integer)
    reply_to_top_id: Mapped[int | None] = mapped_column(Integer)
    edited_at: Mapped[str | None] = mapped_column(String)
    edited_at_utc: Mapped[str | None] = mapped_column(String)
    grouped_id: Mapped[int | None] = mapped_column(Integer)
    forward_from_id: Mapped[int | None] = mapped_column(Integer)
    forward_from_name: Mapped[str | None] = mapped_column(String)
    forward_date: Mapped[str | None] = mapped_column(String)
    forward_date_utc: Mapped[str | None] = mapped_column(String)
    via_bot_id: Mapped[int | None] = mapped_column(Integer)
    post_author: Mapped[str | None] = mapped_column(String)
    views: Mapped[int | None] = mapped_column(Integer)
    forwards: Mapped[int | None] = mapped_column(Integer)
    replies_count: Mapped[int | None] = mapped_column(Integer)
    media_id: Mapped[int | None] = mapped_column(Integer)
    media_mime_type: Mapped[str | None] = mapped_column(String)
    media_file_name: Mapped[str | None] = mapped_column(String)
    media_size: Mapped[int | None] = mapped_column(Integer)
    media_duration: Mapped[float | None] = mapped_column(Float)
    service_action: Mapped[str | None] = mapped_column(String)
    is_outgoing: Mapped[bool | None] = mapped_column(Boolean)
    is_mentioned: Mapped[bool | None] = mapped_column(Boolean)
    is_media_unread: Mapped[bool | None] = mapped_column(Boolean)
    is_silent: Mapped[bool | None] = mapped_column(Boolean)
    is_post: Mapped[bool | None] = mapped_column(Boolean)
    is_from_scheduled: Mapped[bool | None] = mapped_column(Boolean)
    is_pinned: Mapped[bool | None] = mapped_column(Boolean)
    is_forwarding_restricted: Mapped[bool | None] = mapped_column(Boolean)
    entities_json: Mapped[str | None] = mapped_column(Text)
    reactions_json: Mapped[str | None] = mapped_column(Text)
    reply_markup_json: Mapped[str | None] = mapped_column(Text)
    restriction_reason_json: Mapped[str | None] = mapped_column(Text)
    sender_json: Mapped[str | None] = mapped_column(Text)
    record_json: Mapped[str] = mapped_column(Text, nullable=False)
    raw_json: Mapped[str | None] = mapped_column(Text)
    fetched_at: Mapped[str] = mapped_column(String, nullable=False)


def create_sqlite_engine(db_path: str | Path) -> Engine:
    engine = create_engine(
        f"sqlite:///{Path(db_path)}",
        connect_args={"check_same_thread": False, "timeout": 30},
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _configure_sqlite(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA busy_timeout = 30000")
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    return engine


def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
