"""SQLite persistence for export tasks and run history."""

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, List, Optional, Sequence

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

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS export_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    chat_id INTEGER NOT NULL,
                    chat_title TEXT NOT NULL,
                    initial_start_at TEXT NOT NULL,
                    formats TEXT NOT NULL,
                    subdirectory TEXT NOT NULL,
                    schedule_type TEXT NOT NULL,
                    minute INTEGER NOT NULL DEFAULT 0,
                    hour INTEGER NOT NULL DEFAULT 0,
                    weekday INTEGER NOT NULL DEFAULT 0,
                    timezone TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    last_message_id INTEGER,
                    last_success_at TEXT,
                    next_run_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_export_tasks_enabled
                    ON export_tasks(enabled);

                CREATE TABLE IF NOT EXISTS export_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER REFERENCES export_tasks(id) ON DELETE SET NULL,
                    run_type TEXT NOT NULL,
                    chat_id INTEGER,
                    chat_title TEXT,
                    status TEXT NOT NULL,
                    range_start TEXT,
                    range_end TEXT,
                    message_count INTEGER NOT NULL DEFAULT 0,
                    files TEXT NOT NULL DEFAULT '[]',
                    error TEXT,
                    started_at TEXT NOT NULL,
                    finished_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_export_runs_started_at
                    ON export_runs(started_at DESC);
                CREATE INDEX IF NOT EXISTS idx_export_runs_task
                    ON export_runs(task_id, started_at DESC);
                """
            )

    @staticmethod
    def _task_from_row(row: sqlite3.Row) -> ExportTask:
        return ExportTask(
            id=row["id"],
            name=row["name"],
            chat_id=row["chat_id"],
            chat_title=row["chat_title"],
            initial_start_at=row["initial_start_at"],
            formats=tuple(json.loads(row["formats"])),
            subdirectory=row["subdirectory"],
            schedule_type=row["schedule_type"],
            minute=row["minute"],
            hour=row["hour"],
            weekday=row["weekday"],
            timezone=row["timezone"],
            enabled=bool(row["enabled"]),
            last_message_id=row["last_message_id"],
            last_success_at=row["last_success_at"],
            next_run_at=row["next_run_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _run_from_row(self, row: sqlite3.Row) -> ExportRun:
        return ExportRun(
            id=row["id"],
            task_id=row["task_id"],
            run_type=row["run_type"],
            chat_id=row["chat_id"],
            chat_title=row["chat_title"],
            status=row["status"],
            range_start=row["range_start"],
            range_end=row["range_end"],
            message_count=row["message_count"],
            files=tuple(self._resolve_file(file) for file in json.loads(row["files"] or "[]")),
            error=row["error"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
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
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO export_tasks
                (name, chat_id, chat_title, initial_start_at, formats, subdirectory,
                 schedule_type, minute, hour, weekday, timezone, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    chat_id,
                    chat_title,
                    initial_start_at,
                    json.dumps(list(formats)),
                    subdirectory,
                    schedule_type,
                    minute,
                    hour,
                    weekday,
                    timezone_name,
                    int(enabled),
                    now,
                    now,
                ),
            )
            task_id = cursor.lastrowid
        return self.get_task(task_id)

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
        assignments = ", ".join(f"{key} = ?" for key in normalized)
        params = list(normalized.values()) + [task_id]
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                f"UPDATE export_tasks SET {assignments} WHERE id = ?",
                params,
            )
            if cursor.rowcount == 0:
                raise KeyError(f"Export task {task_id} does not exist")
        return self.get_task(task_id)

    def get_task(self, task_id: int) -> ExportTask:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM export_tasks WHERE id = ?", (task_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"Export task {task_id} does not exist")
        return self._task_from_row(row)

    def list_tasks(self, enabled_only: bool = False) -> List[ExportTask]:
        query = "SELECT * FROM export_tasks"
        if enabled_only:
            query += " WHERE enabled = 1"
        query += " ORDER BY id DESC"
        with self._lock, self._connect() as conn:
            rows = conn.execute(query).fetchall()
        return [self._task_from_row(row) for row in rows]

    def delete_task(self, task_id: int) -> None:
        with self._lock, self._connect() as conn:
            cursor = conn.execute("DELETE FROM export_tasks WHERE id = ?", (task_id,))
            if cursor.rowcount == 0:
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
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO export_runs
                (task_id, run_type, chat_id, chat_title, status, range_start, range_end, started_at)
                VALUES (?, ?, ?, ?, 'running', ?, ?, ?)
                """,
                (
                    task_id,
                    run_type,
                    chat_id,
                    chat_title,
                    range_start,
                    range_end,
                    _utc_now_text(),
                ),
            )
            return cursor.lastrowid

    def finish_run(
        self,
        run_id: int,
        *,
        status: str,
        message_count: int = 0,
        files: Sequence[str] = (),
        error: Optional[str] = None,
    ) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE export_runs
                SET status = ?, message_count = ?, files = ?, error = ?, finished_at = ?
                WHERE id = ?
                """,
                (
                    status,
                    message_count,
                    json.dumps(list(files), ensure_ascii=False),
                    error,
                    _utc_now_text(),
                    run_id,
                ),
            )

    def list_runs(self, limit: int = 50) -> List[ExportRun]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM export_runs ORDER BY started_at DESC, id DESC LIMIT ?",
                (max(1, min(int(limit), 500)),),
            ).fetchall()
        return [self._run_from_row(row) for row in rows]

    def get_run(self, run_id: int) -> Optional[ExportRun]:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM export_runs WHERE id = ?",
                (int(run_id),),
            ).fetchone()
        return self._run_from_row(row) if row else None

    def delete_run(self, run_id: int) -> None:
        with self._lock, self._connect() as conn:
            cursor = conn.execute("DELETE FROM export_runs WHERE id = ?", (int(run_id),))
            if cursor.rowcount == 0:
                raise KeyError(f"Export run {run_id} does not exist")
