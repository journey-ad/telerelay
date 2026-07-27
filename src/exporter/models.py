"""Data contracts shared by the export source, writers, scheduler, and UI."""

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

SUPPORTED_FORMATS: Tuple[str, ...] = ("json", "csv", "html")
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
class ChatSummary:
    chat_id: int
    title: str
    kind: str
    username: Optional[str] = None

    @property
    def label(self) -> str:
        suffix = f" (@{self.username})" if self.username else ""
        return f"{self.title}{suffix} [{self.chat_id}]"


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

    @property
    def is_terminal(self) -> bool:
        return self.status in JOB_TERMINAL_STATUSES
