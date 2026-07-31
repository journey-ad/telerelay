"""Data contracts shared by the export source, writers, scheduler, and UI."""

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

GROUP_EXPORT_FORMATS: Tuple[str, ...] = ("json", "csv", "html")
MESSAGE_EXPORT_FORMATS: Tuple[str, ...] = ("json", "csv", "html", "sqlite")
SUPPORTED_FORMATS: Tuple[str, ...] = MESSAGE_EXPORT_FORMATS
SCHEDULE_TYPES: Tuple[str, ...] = ("hourly", "daily", "weekly")
JOB_TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


def datetime_to_text(value: Optional[datetime]) -> Optional[str]:
    """Serialize datetimes consistently without discarding their timezone."""
    return value.isoformat(timespec="seconds") if value else None


@dataclass(frozen=True)
class AdministratorRecord:
    user_id: int
    name: str
    username: Optional[str] = None
    role: str = "administrator"
    is_bot: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ChatRecord:
    chat_id: int
    title: str
    kind: str
    created_at: Optional[str]
    username: Optional[str]
    public_link: Optional[str]
    is_public: bool
    member_count: Optional[int]
    description: Optional[str]
    administrators: List[AdministratorRecord] = field(default_factory=list)
    export_warning: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["administrators"] = [admin.to_dict() for admin in self.administrators]
        return data


@dataclass(frozen=True)
class MessageRecord:
    message_id: int
    chat_id: int
    chat_title: str
    date: str
    sender_id: Optional[int]
    sender_name: Optional[str]
    sender_username: Optional[str]
    text: str
    media_type: str
    content: str
    reply_to_message_id: Optional[int]
    edited_at: Optional[str]
    grouped_id: Optional[int]
    date_utc: Optional[str] = None
    sender_type: Optional[str] = None
    sender_first_name: Optional[str] = None
    sender_last_name: Optional[str] = None
    sender_is_bot: Optional[bool] = None
    sender_phone: Optional[str] = None
    sender_is_verified: Optional[bool] = None
    sender_is_premium: Optional[bool] = None
    sender_is_scam: Optional[bool] = None
    sender_is_fake: Optional[bool] = None
    sender_is_contact: Optional[bool] = None
    sender_is_mutual_contact: Optional[bool] = None
    reply_to_top_id: Optional[int] = None
    edited_at_utc: Optional[str] = None
    forward_from_id: Optional[int] = None
    forward_from_name: Optional[str] = None
    forward_date: Optional[str] = None
    forward_date_utc: Optional[str] = None
    via_bot_id: Optional[int] = None
    post_author: Optional[str] = None
    views: Optional[int] = None
    forwards: Optional[int] = None
    replies_count: Optional[int] = None
    media_id: Optional[int] = None
    media_mime_type: Optional[str] = None
    media_file_name: Optional[str] = None
    media_size: Optional[int] = None
    media_duration: Optional[float] = None
    service_action: Optional[str] = None
    is_outgoing: Optional[bool] = None
    is_mentioned: Optional[bool] = None
    is_media_unread: Optional[bool] = None
    is_silent: Optional[bool] = None
    is_post: Optional[bool] = None
    is_from_scheduled: Optional[bool] = None
    is_pinned: Optional[bool] = None
    is_forwarding_restricted: Optional[bool] = None
    entities: List[Dict[str, Any]] = field(default_factory=list)
    reactions: Optional[Dict[str, Any]] = None
    reply_markup: Optional[Dict[str, Any]] = None
    restriction_reason: List[Dict[str, Any]] = field(default_factory=list)
    sender_raw: Dict[str, Any] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExportTask:
    id: int
    name: str
    chat_id: int
    chat_title: str
    initial_start_at: str
    formats: Tuple[str, ...]
    subdirectory: str
    schedule_type: str
    minute: int
    hour: int
    weekday: int
    timezone: str
    enabled: bool
    last_message_id: Optional[int]
    last_success_at: Optional[str]
    next_run_at: Optional[str]
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class ExportRun:
    id: int
    task_id: Optional[int]
    run_type: str
    chat_id: Optional[int]
    chat_title: Optional[str]
    status: str
    range_start: Optional[str]
    range_end: Optional[str]
    message_count: int
    files: Tuple[str, ...]
    error: Optional[str]
    started_at: str
    finished_at: Optional[str]


@dataclass
class ExportJobState:
    id: str
    kind: str
    status: str = "queued"
    phase: str = "queued"
    processed: int = 0
    total: Optional[int] = None
    files: List[str] = field(default_factory=list)
    error: Optional[str] = None
    task_id: Optional[int] = None
    run_id: Optional[int] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    chat_title: Optional[str] = None
    range_start: Optional[str] = None
    range_end: Optional[str] = None
    all_history: bool = False
    progress_date: Optional[str] = None

    def snapshot(self) -> "ExportJobSnapshot":
        return ExportJobSnapshot(
            id=self.id,
            kind=self.kind,
            status=self.status,
            phase=self.phase,
            processed=self.processed,
            total=self.total,
            files=tuple(self.files),
            error=self.error,
            task_id=self.task_id,
            started_at=self.started_at,
            finished_at=self.finished_at,
            chat_title=self.chat_title,
            range_start=self.range_start,
            range_end=self.range_end,
            all_history=self.all_history,
            progress_date=self.progress_date,
        )


@dataclass(frozen=True)
class ExportJobSnapshot:
    id: str
    kind: str
    status: str
    phase: str
    processed: int
    total: Optional[int]
    files: Tuple[str, ...]
    error: Optional[str]
    task_id: Optional[int]
    started_at: Optional[str]
    finished_at: Optional[str]
    chat_title: Optional[str] = None
    range_start: Optional[str] = None
    range_end: Optional[str] = None
    all_history: bool = False
    progress_date: Optional[str] = None

    @property
    def is_terminal(self) -> bool:
        return self.status in JOB_TERMINAL_STATUSES
