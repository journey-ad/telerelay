"""Persistent export task scheduling backed by APScheduler 3.x."""

from datetime import datetime, timezone
from threading import RLock

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from src.i18n import t
from src.logger import get_logger

logger = get_logger()


class ExportScheduler:
    def __init__(self, service):
        self.service = service
        self.store = service.store
        self._scheduler = BackgroundScheduler(
            timezone=service.config.export_timezone,
            daemon=True,
        )
        self._lock = RLock()
        self._started = False
        service.set_scheduler(self)

    @staticmethod
    def _job_id(task_id: int) -> str:
        return f"export-task-{int(task_id)}"

    @staticmethod
    def _trigger(task):
        common = {"minute": task.minute, "timezone": task.timezone}
        if task.schedule_type == "hourly":
            return CronTrigger(**common)
        if task.schedule_type == "daily":
            return CronTrigger(hour=task.hour, **common)
        return CronTrigger(day_of_week=task.weekday, hour=task.hour, **common)

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            self._scheduler.start()
            self._started = True
            tasks = self.store.list_tasks()
            logger.info(t("log.export.scheduler_started", count=len(tasks)))
            for task in tasks:
                self.sync_task(task.id)

    def sync_task(self, task_id: int) -> None:
        with self._lock:
            if not self._started:
                return
            task = self.store.get_task(int(task_id))
            job_id = self._job_id(task.id)
            if not task.enabled:
                self._remove_job(job_id)
                self.store.update_task(task.id, next_run_at=None)
                logger.debug(
                    t(
                        "log.export.task_unscheduled",
                        task_id=task.id,
                        name=task.name,
                    )
                )
                return
            job = self._scheduler.add_job(
                self._execute_task,
                trigger=self._trigger(task),
                id=job_id,
                args=[task.id],
                replace_existing=True,
                coalesce=True,
                max_instances=1,
                misfire_grace_time=3600,
            )
            next_run = job.next_run_time
            self.store.update_task(
                task.id,
                next_run_at=(next_run.isoformat(timespec="seconds") if next_run else None),
            )
            logger.debug(
                t(
                    "log.export.task_scheduled",
                    task_id=task.id,
                    name=task.name,
                    next_run=(
                        next_run.isoformat(timespec="seconds")
                        if next_run
                        else "-"
                    ),
                )
            )

    def _execute_task(self, task_id: int) -> None:
        logger.debug(t("log.export.task_triggered", task_id=task_id))
        try:
            job_id = self.service.start_task_export(task_id)
            if job_id is None:
                logger.warning(t("log.export.task_overlap", task_id=task_id))
            else:
                logger.debug(
                    t(
                        "log.export.task_job_started",
                        task_id=task_id,
                        job_id=job_id,
                    )
                )
        except Exception as exc:
            logger.error(
                t(
                    "log.export.task_start_failed",
                    task_id=task_id,
                    error=str(exc),
                ),
                exc_info=True,
            )
            try:
                task = self.store.get_task(task_id)
                run_id = self.store.start_run(
                    task_id=task.id,
                    run_type="scheduled",
                    chat_id=task.chat_id,
                    chat_title=task.chat_title,
                    range_start=task.last_success_at or task.initial_start_at,
                    range_end=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                )
                self.store.finish_run(run_id, status="failed", error=str(exc))
            except Exception:
                logger.error(
                    t("log.export.run_record_failed", task_id=task_id),
                    exc_info=True,
                )
        finally:
            self._refresh_next_run(task_id)

    def _refresh_next_run(self, task_id: int) -> None:
        with self._lock:
            job = self._scheduler.get_job(self._job_id(task_id))
            next_run = job.next_run_time if job else None
            try:
                self.store.update_task(
                    task_id,
                    next_run_at=(
                        next_run.isoformat(timespec="seconds") if next_run else None
                    ),
                )
            except KeyError:
                return

    def run_now(self, task_id: int):
        return self.service.start_task_export(int(task_id))

    def remove_task(self, task_id: int) -> None:
        with self._lock:
            self._remove_job(self._job_id(task_id))

    def _remove_job(self, job_id: str) -> None:
        if self._scheduler.get_job(job_id):
            self._scheduler.remove_job(job_id)

    def shutdown(self) -> None:
        with self._lock:
            if self._started:
                self._scheduler.shutdown(wait=False)
                self._started = False
                logger.debug(t("log.export.scheduler_stopped"))
