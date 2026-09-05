"""SQLite persistence for export tasks and run history."""

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Sequence

from sqlalchemy import delete, select, update

from backend.database import (
    Base,
    ExportRunRow,
    ExportTaskRow,
    create_sqlite_engine,
    session_factory,
    session_scope,
)
from .models import ExportRun, ExportTask

DEFAULT_EXPORT_DB_PATH = Path("data/exports.db")


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ExportStore:
    def __init__(
        self,
        db_path: Path = DEFAULT_EXPORT_DB_PATH,
        export_root: str | Path | None = None,
    ):
        self.db_path = Path(db_path)
        self.export_root = Path(export_root).resolve() if export_root is not None else None
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.engine = create_sqlite_engine(self.db_path)
        self._session_factory = session_factory(self.engine)
        self._init_db()
        self.db_path.chmod(0o600)

    @staticmethod
    def _legacy_relative_path(path: Path) -> Path | None:
        try:
            index = path.parts.index("exports")
        except ValueError:
            return None
        return Path(*path.parts[index + 1 :])

    def _resolve_file(self, file: str) -> str:
        candidate = Path(file)
        if self.export_root is not None:
            relative = self._legacy_relative_path(candidate)
            if relative is not None:
                remapped = self.export_root / relative
                if remapped.is_file():
                    return str(remapped)
        if candidate.is_file():
            return str(candidate)
        return file

    def _session(self):
        return session_scope(self._session_factory)

    def _init_db(self) -> None:
        with self._lock:
            Base.metadata.create_all(
                self.engine, tables=[ExportTaskRow.__table__, ExportRunRow.__table__]
            )

    @staticmethod
    def _task_from_row(row: ExportTaskRow) -> ExportTask:
        return ExportTask(
            id=row.id, name=row.name, chat_id=row.chat_id, chat_title=row.chat_title,
            initial_start_at=row.initial_start_at, formats=tuple(json.loads(row.formats)),
            subdirectory=row.subdirectory, schedule_type=row.schedule_type,
            minute=row.minute, hour=row.hour, weekday=row.weekday, timezone=row.timezone,
            enabled=bool(row.enabled), last_message_id=row.last_message_id,
            last_success_at=row.last_success_at, next_run_at=row.next_run_at,
            created_at=row.created_at, updated_at=row.updated_at,
        )

    def _run_from_row(self, row: ExportRunRow) -> ExportRun:
        return ExportRun(
            id=row.id, task_id=row.task_id, run_type=row.run_type, chat_id=row.chat_id,
            chat_title=row.chat_title, status=row.status, range_start=row.range_start,
            range_end=row.range_end, message_count=row.message_count,
            files=tuple(self._resolve_file(file) for file in json.loads(row.files or "[]")),
            error=row.error, started_at=row.started_at, finished_at=row.finished_at,
        )

    def create_task(
        self,
        *,
        name: str,
        chat_id: int,
        chat_title: str,
        initial_start_at: str,
        formats: Sequence[str],
        subdirectory: str,
        schedule_type: str,
        minute: int,
        hour: int,
        weekday: int,
        timezone_name: str,
        enabled: bool = True,
    ) -> ExportTask:
        now = _utc_now_text()
        with self._lock, self._session() as session:
            task = ExportTaskRow(
                name=name, chat_id=chat_id, chat_title=chat_title,
                initial_start_at=initial_start_at, formats=json.dumps(list(formats)),
                subdirectory=subdirectory, schedule_type=schedule_type,
                minute=minute, hour=hour, weekday=weekday, timezone=timezone_name,
                enabled=enabled, created_at=now, updated_at=now,
            )
            session.add(task)
            session.flush()
            return self._task_from_row(task)

    def update_task(self, task_id: int, **values) -> ExportTask:
        allowed = {
            "name",
            "chat_id",
            "chat_title",
            "initial_start_at",
            "formats",
            "subdirectory",
            "schedule_type",
            "minute",
            "hour",
            "weekday",
            "timezone",
            "enabled",
            "last_message_id",
            "last_success_at",
            "next_run_at",
        }
        unknown = set(values) - allowed
        if unknown:
            raise ValueError(f"Unsupported task fields: {sorted(unknown)}")
        if not values:
            return self.get_task(task_id)

        normalized = dict(values)
        if "formats" in normalized:
            normalized["formats"] = json.dumps(list(normalized["formats"]))
        if "enabled" in normalized:
            normalized["enabled"] = int(bool(normalized["enabled"]))
        normalized["updated_at"] = _utc_now_text()
        with self._lock, self._session() as session:
            task = session.get(ExportTaskRow, int(task_id))
            if task is None:
                raise KeyError(f"Export task {task_id} does not exist")
            for key, value in normalized.items():
                setattr(task, key, value)
            return self._task_from_row(task)

    def get_task(self, task_id: int) -> ExportTask:
        with self._lock, self._session() as session:
            row = session.get(ExportTaskRow, int(task_id))
            if row is None:
                raise KeyError(f"Export task {task_id} does not exist")
            return self._task_from_row(row)

    def list_tasks(self, enabled_only: bool = False) -> List[ExportTask]:
        with self._lock, self._session() as session:
            statement = select(ExportTaskRow)
            if enabled_only:
                statement = statement.where(ExportTaskRow.enabled.is_(True))
            rows = session.scalars(statement.order_by(ExportTaskRow.id.desc())).all()
            return [self._task_from_row(row) for row in rows]

    def delete_task(self, task_id: int) -> None:
        with self._lock, self._session() as session:
            result = session.execute(delete(ExportTaskRow).where(ExportTaskRow.id == int(task_id)))
            if result.rowcount == 0:
                raise KeyError(f"Export task {task_id} does not exist")

    def start_run(
        self,
        *,
        task_id: Optional[int],
        run_type: str,
        chat_id: Optional[int] = None,
        chat_title: Optional[str] = None,
        range_start: Optional[str] = None,
        range_end: Optional[str] = None,
    ) -> int:
        with self._lock, self._session() as session:
            run = ExportRunRow(
                task_id=task_id, run_type=run_type, chat_id=chat_id, chat_title=chat_title,
                status="running", range_start=range_start, range_end=range_end,
                started_at=_utc_now_text(),
            )
            session.add(run)
            session.flush()
            return run.id

    def finish_run(
        self,
        run_id: int,
        *,
        status: str,
        message_count: int = 0,
        files: Sequence[str] = (),
        error: Optional[str] = None,
    ) -> None:
        with self._lock, self._session() as session:
            session.execute(
                update(ExportRunRow)
                .where(ExportRunRow.id == int(run_id))
                .values(
                    status=status, message_count=message_count,
                    files=json.dumps(list(files), ensure_ascii=False), error=error,
                    finished_at=_utc_now_text(),
                )
            )

    def list_runs(self, limit: int = 50) -> List[ExportRun]:
        with self._lock, self._session() as session:
            rows = session.scalars(
                select(ExportRunRow)
                .order_by(ExportRunRow.started_at.desc(), ExportRunRow.id.desc())
                .limit(max(1, min(int(limit), 500)))
            ).all()
            return [self._run_from_row(row) for row in rows]

    def get_run(self, run_id: int) -> Optional[ExportRun]:
        with self._lock, self._session() as session:
            row = session.get(ExportRunRow, int(run_id))
            return self._run_from_row(row) if row else None

    def delete_run(self, run_id: int) -> None:
        with self._lock, self._session() as session:
            result = session.execute(delete(ExportRunRow).where(ExportRunRow.id == int(run_id)))
            if result.rowcount == 0:
                raise KeyError(f"Export run {run_id} does not exist")
