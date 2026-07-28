"""Background orchestration for group metadata and message exports."""

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.i18n import t
from src.logger import get_logger

from .formatters import create_writer_set
from .models import (
    SCHEDULE_TYPES,
    SUPPORTED_FORMATS,
    ExportJobSnapshot,
    ExportJobState,
    ExportTask,
)
from .paths import ExportPathError, resolve_export_directory, safe_filename
from .source import TelegramExportSource
from .store import ExportStore

logger = get_logger()


class ExportError(RuntimeError):
    pass


class ExportCancelled(ExportError):
    pass


class ExportUnavailable(ExportError):
    pass


class ExportValidationError(ExportError):
    pass


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _date_text(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


class ExportService:
    def __init__(
        self,
        config,
        bot_manager,
        store: Optional[ExportStore] = None,
        source: Optional[TelegramExportSource] = None,
    ):
        self.config = config
        self.bot_manager = bot_manager
        self.store = store or ExportStore()
        self.source = source or TelegramExportSource(bot_manager)
        self.export_root = Path(config.export_root_dir)
        self.export_root.mkdir(parents=True, exist_ok=True)
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, int(config.export_concurrency)),
            thread_name_prefix="telerelay-export",
        )
        self._lock = threading.RLock()
        self._jobs: Dict[str, ExportJobState] = {}
        self._cancel_events: Dict[str, threading.Event] = {}
        self._active_task_ids = set()
        self._chat_cache = {}
        self.scheduler = None

    def set_scheduler(self, scheduler) -> None:
        self.scheduler = scheduler

    def availability(self, require_connection: bool = True) -> Tuple[bool, str]:
        if self.config.session_type != "user":
            return False, t("message.export.user_mode_required")
        if require_connection and not self.bot_manager.is_connected:
            return False, t("message.export.telegram_not_connected")
        return True, t("message.export.ready")

    def _ensure_available(self) -> None:
        available, reason = self.availability(require_connection=True)
        if not available:
            raise ExportUnavailable(reason)

    def list_chat_choices(self) -> List[Tuple[str, str]]:
        self._ensure_available()
        chats = self.source.list_chat_summaries()
        with self._lock:
            self._chat_cache = {chat.chat_id: chat for chat in chats}
        logger.debug(t("log.export.chats_loaded", count=len(chats)))
        return [(chat.label, str(chat.chat_id)) for chat in chats]

    def _chat_title(self, chat_id: int) -> str:
        with self._lock:
            chat = self._chat_cache.get(int(chat_id))
        return chat.title if chat else str(chat_id)

    @staticmethod
    def normalize_formats(formats: Iterable[str]) -> Tuple[str, ...]:
        if isinstance(formats, str):
            formats = [formats]
        normalized = tuple(
            fmt.lower().strip()
            for fmt in formats
            if fmt and fmt.lower().strip() in SUPPORTED_FORMATS
        )
        normalized = tuple(dict.fromkeys(normalized))
        if not normalized:
            raise ExportValidationError(t("message.export.format_required"))
        return normalized

    @staticmethod
    def parse_datetime(value, timezone_name: str) -> datetime:
        try:
            target_timezone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise ExportValidationError(
                t("message.export.invalid_timezone", timezone=timezone_name)
            ) from exc

        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, (int, float)):
            parsed = datetime.fromtimestamp(value, tz=target_timezone)
        elif value:
            text = str(value).strip().replace("Z", "+00:00")
            try:
                parsed = datetime.fromisoformat(text)
            except ValueError as exc:
                raise ExportValidationError(t("message.export.invalid_datetime")) from exc
        else:
            raise ExportValidationError(t("message.export.datetime_required"))

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=target_timezone)
        return parsed

    def _validated_directory(self, subdirectory: str) -> Path:
        try:
            return resolve_export_directory(self.export_root, subdirectory)
        except ExportPathError as exc:
            raise ExportValidationError(t("message.export.invalid_directory")) from exc

    def _new_job(self, kind: str, task_id: Optional[int] = None) -> ExportJobState:
        state = ExportJobState(id=uuid.uuid4().hex, kind=kind, task_id=task_id)
        with self._lock:
            terminal = [
                job_id
                for job_id, job in self._jobs.items()
                if job.status in {"completed", "failed", "cancelled"}
            ]
            while len(self._jobs) >= 100 and terminal:
                stale_id = terminal.pop(0)
                self._jobs.pop(stale_id, None)
                self._cancel_events.pop(stale_id, None)
            self._jobs[state.id] = state
            self._cancel_events[state.id] = threading.Event()
        return state

    def _update_job(self, job_id: str, **values) -> None:
        with self._lock:
            state = self._jobs[job_id]
            for key, value in values.items():
                setattr(state, key, value)

    def get_job(self, job_id: Optional[str]) -> Optional[ExportJobSnapshot]:
        if not job_id:
            return None
        with self._lock:
            state = self._jobs.get(job_id)
            return state.snapshot() if state else None

    def cancel_job(self, job_id: Optional[str]) -> bool:
        if not job_id:
            return False
        with self._lock:
            event = self._cancel_events.get(job_id)
            state = self._jobs.get(job_id)
            if not event or not state or state.status in {"completed", "failed", "cancelled"}:
                return False
            event.set()
            state.phase = "cancelling"
            logger.info(
                t(
                    "log.export.cancel_requested",
                    job_id=job_id,
                    kind=state.kind,
                    task_id=state.task_id or "-",
                )
            )
            return True

    def start_group_export(
        self,
        formats: Sequence[str],
        subdirectory: str = "groups",
    ) -> str:
        self._ensure_available()
        normalized_formats = self.normalize_formats(formats)
        directory = self._validated_directory(subdirectory)
        state = self._new_job("groups")
        logger.info(
            t(
                "log.export.group_queued",
                job_id=state.id,
                formats=", ".join(normalized_formats),
                directory=directory,
            )
        )
        self._executor.submit(
            self._run_group_export,
            state.id,
            normalized_formats,
            directory,
        )
        return state.id

    def _run_group_export(self, job_id: str, formats, directory: Path) -> None:
        cancel_event = self._cancel_events[job_id]
        run_id = self.store.start_run(task_id=None, run_type="groups")
        self._update_job(
            job_id,
            status="running",
            phase="reading_groups",
            run_id=run_id,
            started_at=_date_text(_now_utc()),
        )
        logger.debug(
            t("log.export.group_started", job_id=job_id, run_id=run_id)
        )
        writers = None
        try:
            def update_progress(processed, total):
                self._update_job(job_id, processed=processed, total=total)
                if processed == 1 or processed % 25 == 0 or processed == total:
                    logger.debug(
                        t(
                            "log.export.group_progress",
                            job_id=job_id,
                            processed=processed,
                            total=total if total is not None else "-",
                        )
                    )

            records = self.source.list_chat_records(update_progress, cancel_event)
            if cancel_event.is_set():
                raise ExportCancelled(t("message.export.cancelled"))

            self._update_job(job_id, phase="writing_files", total=len(records))
            now = _now_utc()
            stem = (
                f"telegram_groups_{now.strftime('%Y%m%d_%H%M%S')}"
                f"_{job_id[:8]}"
            )
            metadata = {
                "export_type": "groups",
                "title": t("export.html.groups_title"),
                "exported_at": _date_text(now),
                "chat_count": len(records),
            }
            writers = create_writer_set(
                directory / stem,
                "chats",
                formats,
                metadata,
                self._html_labels(),
            )
            for record in records:
                writers.add(record.to_dict())
            files = [str(path.resolve()) for path in writers.finalize()]
            writers = None
            self.store.finish_run(
                run_id,
                status="completed",
                message_count=len(records),
                files=files,
            )
            self._update_job(
                job_id,
                status="completed",
                phase="completed",
                files=files,
                processed=len(records),
                total=len(records),
                finished_at=_date_text(_now_utc()),
            )
            logger.info(
                t(
                    "log.export.group_completed",
                    job_id=job_id,
                    run_id=run_id,
                    count=len(records),
                    files=", ".join(files) or "-",
                )
            )
        except ExportCancelled as exc:
            if writers:
                writers.abort()
            self.store.finish_run(run_id, status="cancelled", error=str(exc))
            self._update_job(
                job_id,
                status="cancelled",
                phase="cancelled",
                error=str(exc),
                finished_at=_date_text(_now_utc()),
            )
            logger.info(
                t(
                    "log.export.group_cancelled",
                    job_id=job_id,
                    run_id=run_id,
                )
            )
        except Exception as exc:
            if writers:
                writers.abort()
            logger.error(
                t(
                    "log.export.group_failed",
                    job_id=job_id,
                    run_id=run_id,
                    error=str(exc),
                ),
                exc_info=True,
            )
            self.store.finish_run(run_id, status="failed", error=str(exc))
            self._update_job(
                job_id,
                status="failed",
                phase="failed",
                error=str(exc),
                finished_at=_date_text(_now_utc()),
            )

    def start_message_export(
        self,
        *,
        chat_id,
        start_at,
        end_at,
        formats: Sequence[str],
        subdirectory: str = "messages",
        all_history: bool = False,
    ) -> str:
        self._ensure_available()
        chat_id = self._validate_chat_id(chat_id)
        timezone_name = self.config.export_timezone
        end = self.parse_datetime(end_at, timezone_name) if end_at else datetime.now(ZoneInfo(timezone_name))
        start = (
            datetime(1970, 1, 1, tzinfo=ZoneInfo(timezone_name))
            if all_history
            else self.parse_datetime(start_at, timezone_name)
        )
        if start > end:
            raise ExportValidationError(t("message.export.invalid_range"))
        formats = self.normalize_formats(formats)
        directory = self._validated_directory(subdirectory)
        state = self._new_job("messages")
        chat_title = self._chat_title(chat_id)
        logger.info(
            t(
                "log.export.message_queued",
                job_id=state.id,
                task_id="-",
                chat_title=chat_title,
                chat_id=chat_id,
                start=_date_text(start),
                end=_date_text(end),
                formats=", ".join(formats),
                directory=directory,
            )
        )
        self._executor.submit(
            self._run_message_export,
            state.id,
            None,
            chat_id,
            chat_title,
            start,
            end,
            formats,
            directory,
            None,
        )
        return state.id

    @staticmethod
    def _validate_chat_id(value) -> int:
        if value in (None, ""):
            raise ExportValidationError(t("message.export.chat_required"))
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise ExportValidationError(t("message.export.invalid_chat")) from exc

    def _run_message_export(
        self,
        job_id: str,
        task_id: Optional[int],
        chat_id: int,
        chat_title: str,
        start_at: datetime,
        end_at: datetime,
        formats: Sequence[str],
        directory: Path,
        min_message_id: Optional[int],
    ) -> None:
        cancel_event = self._cancel_events[job_id]
        run_type = "scheduled" if task_id else "messages"
        run_id = self.store.start_run(
            task_id=task_id,
            run_type=run_type,
            chat_id=chat_id,
            chat_title=chat_title,
            range_start=_date_text(start_at),
            range_end=_date_text(end_at),
        )
        self._update_job(
            job_id,
            status="running",
            phase="reading_messages",
            run_id=run_id,
            started_at=_date_text(_now_utc()),
        )
        logger.debug(
            t(
                "log.export.message_started",
                kind=run_type,
                job_id=job_id,
                run_id=run_id,
                task_id=task_id or "-",
                chat_title=chat_title,
                chat_id=chat_id,
                start=_date_text(start_at),
                end=_date_text(end_at),
                min_message_id=min_message_id or "-",
            )
        )
        writers = None
        count = 0
        last_message_id = min_message_id
        output_timezone = ZoneInfo(self.config.export_timezone if not task_id else self.store.get_task(task_id).timezone)
        try:
            stem = self._message_stem(
                chat_title,
                chat_id,
                start_at,
                end_at,
                task_id,
                job_id,
            )
            metadata = {
                "export_type": "messages",
                "title": t("export.html.messages_title", chat=chat_title),
                "exported_at": _date_text(_now_utc()),
                "chat_id": chat_id,
                "chat_title": chat_title,
                "range_start": _date_text(start_at),
                "range_end": _date_text(end_at),
                "timezone": str(output_timezone),
            }
            records = self.source.iter_message_records(
                chat_id=chat_id,
                chat_title=chat_title,
                start_at=start_at.astimezone(timezone.utc),
                end_at=end_at.astimezone(timezone.utc),
                output_timezone=output_timezone,
                min_message_id=min_message_id,
                cancel_event=cancel_event,
            )
            for record in records:
                if cancel_event.is_set():
                    raise ExportCancelled(t("message.export.cancelled"))
                if writers is None:
                    writers = create_writer_set(
                        directory / stem,
                        "messages",
                        formats,
                        metadata,
                        self._html_labels(),
                    )
                writers.add(record.to_dict())
                count += 1
                last_message_id = record.message_id
                if count == 1 or count % 25 == 0:
                    self._update_job(job_id, processed=count)
                if count == 1 or count % 2000 == 0:
                    logger.debug(
                        t(
                            "log.export.message_progress",
                            kind=run_type,
                            job_id=job_id,
                            task_id=task_id or "-",
                            chat_id=chat_id,
                            count=count,
                        )
                    )

            files = []
            if writers:
                self._update_job(job_id, phase="writing_files")
                files = [str(path.resolve()) for path in writers.finalize()]
                writers = None

            if task_id:
                self.store.update_task(
                    task_id,
                    last_message_id=last_message_id,
                    last_success_at=_date_text(end_at),
                )
            self.store.finish_run(
                run_id,
                status="completed",
                message_count=count,
                files=files,
            )
            self._update_job(
                job_id,
                status="completed",
                phase="completed",
                processed=count,
                files=files,
                finished_at=_date_text(_now_utc()),
            )
            logger.info(
                t(
                    "log.export.message_completed",
                    kind=run_type,
                    job_id=job_id,
                    run_id=run_id,
                    task_id=task_id or "-",
                    chat_title=chat_title,
                    chat_id=chat_id,
                    count=count,
                    files=", ".join(files) or "-",
                )
            )
        except ExportCancelled as exc:
            if writers:
                writers.abort()
            self.store.finish_run(
                run_id,
                status="cancelled",
                message_count=count,
                error=str(exc),
            )
            self._update_job(
                job_id,
                status="cancelled",
                phase="cancelled",
                processed=count,
                error=str(exc),
                finished_at=_date_text(_now_utc()),
            )
            logger.info(
                t(
                    "log.export.message_cancelled",
                    kind=run_type,
                    job_id=job_id,
                    run_id=run_id,
                    task_id=task_id or "-",
                    chat_title=chat_title,
                    chat_id=chat_id,
                    count=count,
                )
            )
        except Exception as exc:
            if writers:
                writers.abort()
            logger.error(
                t(
                    "log.export.message_failed",
                    kind=run_type,
                    job_id=job_id,
                    run_id=run_id,
                    task_id=task_id or "-",
                    chat_title=chat_title,
                    chat_id=chat_id,
                    count=count,
                    error=str(exc),
                ),
                exc_info=True,
            )
            self.store.finish_run(
                run_id,
                status="failed",
                message_count=count,
                error=str(exc),
            )
            self._update_job(
                job_id,
                status="failed",
                phase="failed",
                processed=count,
                error=str(exc),
                finished_at=_date_text(_now_utc()),
            )
        finally:
            if task_id:
                with self._lock:
                    self._active_task_ids.discard(task_id)

    @staticmethod
    def _message_stem(chat_title, chat_id, start_at, end_at, task_id, job_id) -> str:
        title = safe_filename(chat_title, fallback="chat", max_length=48)
        start_tag = start_at.strftime("%Y%m%d_%H%M%S")
        end_tag = end_at.strftime("%Y%m%d_%H%M%S")
        task_tag = f"task{task_id}_" if task_id else ""
        return f"{task_tag}{title}_{chat_id}_{start_tag}_{end_tag}_{job_id[:8]}"

    def save_task(
        self,
        *,
        task_id=None,
        name: str,
        chat_id,
        initial_start_at,
        formats: Sequence[str],
        subdirectory: str,
        schedule_type: str,
        minute,
        hour,
        weekday,
        timezone_name: Optional[str] = None,
        all_history: bool = False,
        enabled: bool = True,
    ) -> ExportTask:
        chat_id = self._validate_chat_id(chat_id)
        name = (name or "").strip()
        if not name:
            raise ExportValidationError(t("message.export.task_name_required"))
        timezone_name = timezone_name or self.config.export_timezone
        try:
            task_timezone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise ExportValidationError(
                t("message.export.invalid_timezone", timezone=timezone_name)
            ) from exc
        start = (
            datetime(1970, 1, 1, tzinfo=task_timezone)
            if all_history
            else self.parse_datetime(initial_start_at, timezone_name)
        )
        formats = self.normalize_formats(formats)
        self._validated_directory(subdirectory)
        schedule_type = (schedule_type or "").lower()
        if schedule_type not in SCHEDULE_TYPES:
            raise ExportValidationError(t("message.export.invalid_schedule"))
        minute = int(minute)
        hour = int(hour)
        weekday = int(weekday)
        if not 0 <= minute <= 59 or not 0 <= hour <= 23 or not 0 <= weekday <= 6:
            raise ExportValidationError(t("message.export.invalid_schedule"))

        values = {
            "name": name[:100],
            "chat_id": chat_id,
            "chat_title": self._chat_title(chat_id),
            "initial_start_at": _date_text(start),
            "formats": formats,
            "subdirectory": subdirectory,
            "schedule_type": schedule_type,
            "minute": minute,
            "hour": hour,
            "weekday": weekday,
            "timezone": timezone_name,
            "enabled": enabled,
        }
        if task_id:
            existing = self.store.get_task(int(task_id))
            reset_cursor = (
                existing.chat_id != chat_id
                or existing.initial_start_at != values["initial_start_at"]
            )
            if reset_cursor:
                values.update(last_message_id=None, last_success_at=None)
            task = self.store.update_task(int(task_id), **values)
        else:
            task = self.store.create_task(timezone_name=values.pop("timezone"), **values)
        if self.scheduler:
            self.scheduler.sync_task(task.id)
        task = self.store.get_task(task.id)
        logger.info(
            t(
                "log.export.task_saved",
                task_id=task.id,
                name=task.name,
                chat_title=task.chat_title,
                chat_id=task.chat_id,
                schedule=task.schedule_type,
                enabled=task.enabled,
                next_run=task.next_run_at or "-",
            )
        )
        return task

    def start_task_export(self, task_id: int) -> Optional[str]:
        self._ensure_available()
        task = self.store.get_task(int(task_id))
        with self._lock:
            if task.id in self._active_task_ids:
                return None
            self._active_task_ids.add(task.id)
        try:
            timezone_value = ZoneInfo(task.timezone)
            end_at = datetime.now(timezone_value)
            start_at = self.parse_datetime(
                task.last_success_at or task.initial_start_at,
                task.timezone,
            )
            directory = self._validated_directory(task.subdirectory)
            state = self._new_job("scheduled", task.id)
            logger.info(
                t(
                    "log.export.message_queued",
                    job_id=state.id,
                    task_id=task.id,
                    chat_title=task.chat_title,
                    chat_id=task.chat_id,
                    start=_date_text(start_at),
                    end=_date_text(end_at),
                    formats=", ".join(task.formats),
                    directory=directory,
                )
            )
            self._executor.submit(
                self._run_message_export,
                state.id,
                task.id,
                task.chat_id,
                task.chat_title,
                start_at,
                end_at,
                task.formats,
                directory,
                task.last_message_id,
            )
            return state.id
        except Exception:
            with self._lock:
                self._active_task_ids.discard(task.id)
            raise

    def set_task_enabled(self, task_id: int, enabled: bool) -> ExportTask:
        task = self.store.update_task(int(task_id), enabled=enabled)
        if self.scheduler:
            self.scheduler.sync_task(task.id)
        task = self.store.get_task(task.id)
        logger.info(
            t(
                "log.export.task_state_changed",
                task_id=task.id,
                name=task.name,
                enabled=task.enabled,
                next_run=task.next_run_at or "-",
            )
        )
        return task

    def delete_task(self, task_id: int) -> None:
        task_id = int(task_id)
        with self._lock:
            if task_id in self._active_task_ids:
                raise ExportValidationError(t("message.export.task_running"))
        if self.scheduler:
            self.scheduler.remove_task(task_id)
        task = self.store.get_task(task_id)
        self.store.delete_task(task_id)
        logger.info(
            t("log.export.task_deleted", task_id=task.id, name=task.name)
        )

    def list_tasks(self) -> List[ExportTask]:
        return self.store.list_tasks()

    def list_runs(self, limit: int = 50):
        return self.store.list_runs(limit)

    @staticmethod
    def _html_labels() -> Dict[str, str]:
        keys = (
            "language",
            "title",
            "chat_id",
            "kind",
            "created_at",
            "username",
            "member_count",
            "description",
            "administrators",
            "bot",
            "none",
            "reply_to",
            "search",
            "search_placeholder",
            "date_from",
            "date_to",
            "apply_filters",
            "reset_filters",
            "page_size",
            "previous_page",
            "next_page",
            "page_status",
            "result_status",
            "filter_progress",
            "archive_summary",
            "range",
            "loading",
            "no_results",
            "unknown_sender",
            "edited",
            "open_reply",
            "reply_summary",
            "reply_missing",
            "reply_count",
            "open_thread",
            "thread_loading_title",
            "thread_loading",
            "thread_title",
            "thread_summary",
            "back_to_messages",
            "load_error",
            "archive_readme",
        )
        return {key: t(f"export.html.{key}") for key in keys}

    def shutdown(self) -> None:
        with self._lock:
            for event in self._cancel_events.values():
                event.set()
        self._executor.shutdown(wait=False, cancel_futures=True)
