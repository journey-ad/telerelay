"""Background orchestration for group metadata and message exports."""

import secrets
import threading
import time
import uuid
import zipfile
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from backend.i18n import t
from backend.logger import get_logger, run_with_account_log_context

from .formatters import create_writer_set
from .message_store import MessageArchiveStore
from .models import (
    GROUP_EXPORT_FORMATS,
    MESSAGE_EXPORT_FORMATS,
    SCHEDULE_TYPES,
    ExportJobSnapshot,
    ExportJobState,
    ExportTask,
)
from .paths import (
    ExportPathError,
    purge_partial_files,
    resolve_export_directory,
    safe_filename,
)
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


PREVIEW_TOKEN_TTL = 300.0

# Task kinds and the sentinel chat id a chat-list task stores instead of a chat.
TASK_KINDS: Tuple[str, ...] = ("messages", "chats")
CHAT_LIST_TASK_CHAT_ID = 0

# Per-chat archive stores kept open per account; each one holds a connection.
MESSAGE_STORE_CACHE_LIMIT = 16

# A running export mirrors its count into the run row so the console's run
# history grows while the job is still working. Writes are rate limited: one
# SQLite transaction per message would cost more than the export itself.
RUN_PROGRESS_INTERVAL_SECONDS = 2.0


class _RunProgressWriter:
    """Persist a running export's message count at a bounded rate."""

    def __init__(
        self,
        store: ExportStore,
        run_id: int,
        *,
        interval: Optional[float] = None,
    ):
        self._store = store
        self._run_id = run_id
        self._interval = (
            RUN_PROGRESS_INTERVAL_SECONDS if interval is None else interval
        )
        self._count = 0
        self._at = time.monotonic()

    @property
    def count(self) -> int:
        return self._count

    def update(self, count: int, *, force: bool = False) -> bool:
        """Store `count` when the rate limit allows it; report whether it stored."""
        if count <= self._count:
            return False
        now = time.monotonic()
        if not force and now - self._at < self._interval:
            return False
        self._store.update_run_progress(self._run_id, message_count=count)
        self._count = count
        self._at = now
        return True


class ExportService:
    def __init__(
        self,
        config,
        bot_manager,
        store: Optional[ExportStore] = None,
        source: Optional[TelegramExportSource] = None,
        events=None,
        session_type: str = "user",
    ):
        self.config = config
        self.bot_manager = bot_manager
        self.account_id = getattr(bot_manager, "account_id", None)
        self.export_root = Path(config.export_root_dir)
        self.export_root.mkdir(parents=True, exist_ok=True)
        self.message_db_root = Path(
            getattr(config, "export_message_db_dir", "data/db")
        )
        self.message_db_root.mkdir(parents=True, exist_ok=True)
        self.store = store or ExportStore(export_root=self.export_root)
        self.source = source or TelegramExportSource(bot_manager)
        self.events = events
        self.session_type = session_type
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, int(config.export_concurrency)),
            thread_name_prefix="telerelay-export",
        )
        self._lock = threading.RLock()
        self._jobs: Dict[str, ExportJobState] = {}
        self._cancel_events: Dict[str, threading.Event] = {}
        self._active_task_ids = set()
        self._message_stores: "OrderedDict[int, MessageArchiveStore]" = OrderedDict()
        self._preview_tokens: Dict[str, Tuple[str, float]] = {}
        self.scheduler = None

    def set_scheduler(self, scheduler) -> None:
        self.scheduler = scheduler

    def create_preview_token(self, zip_path: str | Path) -> str:
        candidate = Path(zip_path).resolve()
        root = self.export_root.resolve()
        if not candidate.is_file() or not (candidate == root or root in candidate.parents):
            raise ExportValidationError("Export archive does not exist")
        if not candidate.name.endswith((".html.zip", ".html")):
            raise ExportValidationError("Only HTML exports support online preview")
        token = secrets.token_urlsafe(24)
        self._preview_tokens[token] = (str(candidate), time.monotonic() + PREVIEW_TOKEN_TTL)
        return token

    def resolve_preview_token(self, token: str) -> Optional[Path]:
        entry = self._preview_tokens.get(token)
        if not entry:
            return None
        path_text, expires = entry
        if time.monotonic() > expires:
            self._preview_tokens.pop(token, None)
            return None
        return Path(path_text)

    def read_archive_file(self, zip_path: Path, inner: str) -> Optional[bytes]:
        normalized = PurePosixPath(inner)
        if normalized.is_absolute() or ".." in normalized.parts:
            return None
        name = normalized.as_posix()
        # A chat-list export is one self-contained HTML file rather than an
        # archive, so it is served straight from disk.
        if zip_path.name.endswith(".html"):
            if name in ("", "index.html", zip_path.name):
                try:
                    return zip_path.read_bytes()
                except OSError:
                    return None
            return None
        try:
            with zipfile.ZipFile(zip_path) as archive:
                if name in archive.namelist():
                    return archive.read(name)
                if name == "index.html":
                    for entry in archive.namelist():
                        if entry.endswith("index.html"):
                            return archive.read(entry)
        except (OSError, zipfile.BadZipFile):
            return None
        return None

    def availability(self, require_connection: bool = True) -> Tuple[bool, str]:
        if self.session_type != "user":
            return False, t("message.export.user_mode_required")
        if require_connection and not self.bot_manager.is_connected:
            return False, t("message.export.telegram_not_connected")
        return True, t("message.export.ready")

    def _ensure_available(self) -> None:
        available, reason = self.availability(require_connection=True)
        if not available:
            raise ExportUnavailable(reason)

    @staticmethod
    def normalize_formats(
        formats: Iterable[str],
        supported: Sequence[str] = MESSAGE_EXPORT_FORMATS,
    ) -> Tuple[str, ...]:
        if isinstance(formats, str):
            formats = [formats]
        normalized = tuple(
            fmt.lower().strip()
            for fmt in formats
            if fmt and fmt.lower().strip() in supported
        )
        normalized = tuple(dict.fromkeys(normalized))
        if not normalized:
            raise ExportValidationError(t("message.export.format_required"))
        return normalized

    def _message_store(self, chat_id: int) -> MessageArchiveStore:
        chat_id = int(chat_id)
        with self._lock:
            store = self._message_stores.get(chat_id)
            if store is None:
                store = MessageArchiveStore(self.message_db_root, chat_id)
                self._message_stores[chat_id] = store
            self._message_stores.move_to_end(chat_id)
            if len(self._message_stores) > MESSAGE_STORE_CACHE_LIMIT:
                _, stale = self._message_stores.popitem(last=False)
                stale.close()
            return store

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

    def publish_scheduled_event(self, task_id: int, status: str, **values) -> None:
        if not self.events:
            return
        try:
            task = self.store.get_task(task_id)
            payload = {
                "status": status,
                "account_id": self.account_id,
                "task_id": task_id,
                "task_name": task.name,
                "chat_id": task.chat_id,
                "chat_title": task.chat_title,
                **values,
            }
        except KeyError:
            payload = {
                "status": status,
                "account_id": self.account_id,
                "task_id": task_id,
                **values,
            }
        self.events.publish_threadsafe("scheduled-export", payload)

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
        task_id: Optional[int] = None,
    ) -> str:
        self._ensure_available()
        normalized_formats = self.normalize_formats(formats, GROUP_EXPORT_FORMATS)
        directory = self._validated_directory(subdirectory)
        state = self._new_job("groups", task_id)
        logger.info(
            t(
                "log.export.group_queued",
                job_id=state.id,
                formats=", ".join(normalized_formats),
                directory=directory,
            )
        )
        self._executor.submit(
            run_with_account_log_context,
            self.account_id,
            self._run_group_export,
            state.id,
            normalized_formats,
            directory,
            task_id,
        )
        return state.id

    def _run_group_export(
        self, job_id: str, formats, directory: Path, task_id: Optional[int] = None
    ) -> None:
        cancel_event = self._cancel_events[job_id]
        scheduled = task_id is not None
        # A chat-list run is not bound to a chat, and the console labels it from
        # run_type instead of a stored (language-specific) title.
        run_id = self.store.start_run(
            task_id=task_id,
            run_type="scheduled_chats" if scheduled else "groups",
        )
        progress = _RunProgressWriter(self.store, run_id)
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
                progress.update(processed, force=processed == 1)
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
        finally:
            if scheduled:
                with self._lock:
                    self._active_task_ids.discard(task_id)

    def start_message_export(
        self,
        *,
        chat_id,
        chat_title: str,
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
        chat_title = str(chat_title).strip() or str(chat_id)
        state.chat_title = chat_title
        state.range_start = _date_text(start)
        state.range_end = _date_text(end)
        state.all_history = all_history
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
            run_with_account_log_context,
            self.account_id,
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
        progress = _RunProgressWriter(self.store, run_id)
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
        try:
            task = self.store.get_task(task_id) if task_id else None
            if task and task.last_message_id is not None:
                last_message_id = task.last_message_id
            output_timezone = ZoneInfo(
                task.timezone if task else self.config.export_timezone
            )
            message_store = self._message_store(chat_id)
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
            incremental_formats = (
                tuple(fmt for fmt in formats if fmt in {"json", "csv"})
                if task
                else ()
            )
            pending_records = []
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
                payload = record.to_dict()
                pending_records.append(payload)
                if len(pending_records) >= 250:
                    message_store.upsert(pending_records)
                    pending_records.clear()
                if incremental_formats and writers is None:
                    writers = create_writer_set(
                        directory / stem,
                        "messages",
                        incremental_formats,
                        metadata,
                        self._html_labels(),
                    )
                if writers:
                    writers.add(payload)
                count += 1
                last_message_id = max(
                    int(last_message_id or record.message_id),
                    int(record.message_id),
                )
                progress.update(count, force=count == 1)
                if count == 1 or count % 25 == 0:
                    self._update_job(
                        job_id,
                        processed=count,
                        progress_date=record.date,
                    )
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

            if pending_records:
                message_store.upsert(pending_records)

            files = []
            if writers:
                self._update_job(job_id, phase="writing_files")
                files.extend(str(path.resolve()) for path in writers.finalize())
                writers = None

            if task:
                if "html" in formats:
                    archive_start = self.parse_datetime(
                        task.initial_start_at,
                        task.timezone,
                    )
                    stored_records = message_store.iter_records(
                        start_at=archive_start,
                        end_at=end_at,
                        output_timezone=output_timezone,
                    )
                    first_record = next(stored_records, None)
                    if first_record is not None:
                        self._update_job(job_id, phase="writing_files")
                        archive_metadata = dict(metadata)
                        archive_metadata["range_start"] = _date_text(archive_start)
                        writers = create_writer_set(
                            directory / stem,
                            "messages",
                            ("html",),
                            archive_metadata,
                            self._html_labels(),
                        )
                        writers.add(first_record)
                        for record in stored_records:
                            writers.add(record)
                        files.extend(
                            str(path.resolve()) for path in writers.finalize()
                        )
                        writers = None
            else:
                rebuild_formats = tuple(
                    fmt for fmt in formats if fmt in {"json", "csv", "html"}
                )
                if rebuild_formats:
                    stored_records = message_store.iter_records(
                        start_at=start_at,
                        end_at=end_at,
                        output_timezone=output_timezone,
                    )
                    first_record = next(stored_records, None)
                    if first_record is not None:
                        self._update_job(job_id, phase="writing_files")
                        writers = create_writer_set(
                            directory / stem,
                            "messages",
                            rebuild_formats,
                            metadata,
                            self._html_labels(),
                        )
                        writers.add(first_record)
                        for record in stored_records:
                            writers.add(record)
                        files.extend(
                            str(path.resolve()) for path in writers.finalize()
                        )
                        writers = None

            if "sqlite" in formats and message_store.count():
                database = message_store.backup_to(
                    directory / message_store.path.name
                )
                files.append(str(database.resolve()))

            if task_id:
                message_store.set_metadata(
                    self._task_backfill_key(task_id),
                    task.initial_start_at,
                )
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
            if task_id:
                self.publish_scheduled_event(
                    task_id, "completed", job_id=job_id, message_count=count
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
            if task_id:
                self.publish_scheduled_event(
                    task_id,
                    "cancelled",
                    job_id=job_id,
                    message_count=count,
                    error=str(exc),
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
            if task_id:
                self.publish_scheduled_event(
                    task_id,
                    "failed",
                    job_id=job_id,
                    message_count=count,
                    error=str(exc),
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

    @staticmethod
    def _task_backfill_key(task_id: int) -> str:
        return f"task:{int(task_id)}:initial_start_at"

    def save_task(
        self,
        *,
        task_id=None,
        name: str,
        chat_id=None,
        chat_title: str,
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
        kind: str = "messages",
    ) -> ExportTask:
        if kind not in TASK_KINDS:
            raise ExportValidationError(t("message.export.invalid_task_kind"))
        if kind == "chats":
            # A chat-list task archives the whole account, so it binds to no
            # single chat and reuses the chat_id column with a sentinel value.
            # It stores no title: the console labels it from the task kind, so
            # the label follows the reader's language rather than the writer's.
            chat_id = CHAT_LIST_TASK_CHAT_ID
            chat_title = ""
        else:
            chat_id = self._validate_chat_id(chat_id)
            chat_title = str(chat_title).strip() or str(chat_id)
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
        if all_history:
            start = datetime(1970, 1, 1, tzinfo=task_timezone)
        elif initial_start_at:
            start = self.parse_datetime(initial_start_at, timezone_name)
        else:
            # No explicit start: the task archives from now on.
            start = datetime.now(task_timezone)
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
            "kind": kind,
            "chat_id": chat_id,
            "chat_title": chat_title,
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
                or existing.kind != kind
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
        if task.kind == "chats":
            return self._start_chat_list_task(task)
        with self._lock:
            if task.id in self._active_task_ids:
                return None
            self._active_task_ids.add(task.id)
        try:
            timezone_value = ZoneInfo(task.timezone)
            end_at = datetime.now(timezone_value)
            message_store = self._message_store(task.chat_id)
            backfill_complete = (
                message_store.get_metadata(self._task_backfill_key(task.id))
                == task.initial_start_at
            )
            start_at = self.parse_datetime(
                (
                    task.last_success_at
                    if backfill_complete and task.last_success_at
                    else task.initial_start_at
                ),
                task.timezone,
            )
            min_message_id = task.last_message_id if backfill_complete else None
            directory = self._validated_directory(task.subdirectory)
            state = self._new_job("scheduled", task.id)
            state.chat_title = task.chat_title
            state.range_start = _date_text(start_at)
            state.range_end = _date_text(end_at)
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
                run_with_account_log_context,
                self.account_id,
                self._run_message_export,
                state.id,
                task.id,
                task.chat_id,
                task.chat_title,
                start_at,
                end_at,
                task.formats,
                directory,
                min_message_id,
            )
            return state.id
        except Exception:
            with self._lock:
                self._active_task_ids.discard(task.id)
            raise

    def _start_chat_list_task(self, task: ExportTask) -> Optional[str]:
        """Run a chat-list task, which archives the account rather than one chat."""
        with self._lock:
            if task.id in self._active_task_ids:
                return None
            self._active_task_ids.add(task.id)
        try:
            job_id = self.start_group_export(
                formats=task.formats,
                subdirectory=task.subdirectory,
                task_id=task.id,
            )
            logger.info(
                t(
                    "log.export.task_job_started",
                    task_id=task.id,
                    job_id=job_id,
                )
            )
            return job_id
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

    def delete_run(self, run_id: int) -> None:
        run_id = int(run_id)
        run = self.store.get_run(run_id)
        if run is None:
            raise KeyError(f"Export run {run_id} does not exist")
        roots = [self.export_root.resolve(), self.message_db_root.resolve()]
        for file in run.files:
            candidate = Path(file).resolve()
            if candidate.is_file() and any(
                candidate == root or root in candidate.parents for root in roots
            ):
                candidate.unlink(missing_ok=True)
        self.store.delete_run(run_id)

    @staticmethod
    def _html_labels() -> Dict[str, str]:
        keys = (
            "language",
            "title",
            "chat_id",
            "kind",
            "created_at",
            "username",
            "public_link",
            "member_count",
            "description",
            "status",
            "joined_at",
            "last_message_at",
            "last_message_text",
            "message_count",
            "unread_count",
            "is_archived",
            "export_warning",
            # Chat-list table chrome and status vocabulary.
            "chats_search_placeholder",
            "chats_sort_hint",
            "chats_no_results",
            "chats_total",
            "chats_filtered_count",
            "status_ok",
            "status_left",
            "status_readonly",
            "status_blocked",
            "status_deleted",
            "status_deactivated",
            "status_missing",
            "yes",
            "no",
            "reply_to",
            "search",
            "date_from",
            "date_to",
            "apply_filters",
            "reset_filters",
            "page_size",
            "page_input",
            "previous_page",
            "next_page",
            "page_status",
            "page_of",
            "result_status",
            "filter_progress",
            "archive_summary",
            "range",
            "loading",
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

    def recover_interrupted_runs(self) -> List[int]:
        """Close runs an earlier process left `running`; returns their ids.

        Called once at startup, before the scheduler is started, so no run of
        this process can be mistaken for an orphan.
        """
        run_ids = self.store.interrupt_running_runs()
        if run_ids:
            logger.warning(
                t(
                    "log.export.runs_interrupted",
                    account_id=self.account_id or "-",
                    count=len(run_ids),
                    run_ids=", ".join(str(run_id) for run_id in run_ids),
                )
            )
        return run_ids

    def purge_partial_exports(self) -> int:
        """Delete staged export files an earlier process left behind.

        Called once at startup, while no export of this process can hold one.
        """
        removed, freed = purge_partial_files(self.export_root)
        if removed:
            logger.info(
                t(
                    "log.export.partial_files_removed",
                    account_id=self.account_id or "-",
                    count=removed,
                    size=f"{freed / 1048576:.1f}MB",
                )
            )
        return removed

    def shutdown(self) -> None:
        with self._lock:
            for event in self._cancel_events.values():
                event.set()
            stores = list(self._message_stores.values())
            self._message_stores.clear()
        for store in stores:
            store.close()
        self._executor.shutdown(wait=False, cancel_futures=True)
