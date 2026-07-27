"""Gradio adapter for group metadata, message, and scheduled exports."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import gradio as gr

from src.i18n import t
from src.logger import get_logger
from src.webui.utils import format_message

logger = get_logger()


class ExportHandler:
    def __init__(self, service, scheduler):
        self.service = service
        self.scheduler = scheduler

    def availability_message(self):
        available, reason = self.service.availability(require_connection=True)
        return format_message(reason, "success" if available else "error")

    def refresh_chats(self):
        try:
            choices = self.service.list_chat_choices()
            value = choices[0][1] if choices else None
            message = t("message.export.chats_loaded", count=len(choices))
            return gr.update(choices=choices, value=value), format_message(message, "success")
        except Exception as exc:
            logger.warning("Could not load export chat choices: %s", exc)
            return gr.update(choices=[], value=None), format_message(str(exc), "error")

    def start_group_export(self, formats, subdirectory):
        try:
            job_id = self.service.start_group_export(formats, subdirectory)
            return format_message(t("message.export.started"), "info"), job_id
        except Exception as exc:
            return format_message(str(exc), "error"), None

    def start_message_export(
        self,
        chat_id,
        start_at,
        end_at,
        formats,
        subdirectory,
        all_history,
    ):
        try:
            job_id = self.service.start_message_export(
                chat_id=chat_id,
                start_at=start_at,
                end_at=end_at,
                formats=formats,
                subdirectory=subdirectory,
                all_history=all_history,
            )
            return format_message(t("message.export.started"), "info"), job_id
        except Exception as exc:
            return format_message(str(exc), "error"), None

    def poll_job(self, job_id):
        snapshot = self.service.get_job(job_id)
        if snapshot is None:
            return gr.update(), gr.update()
        if snapshot.status == "completed":
            message = t(
                "message.export.completed",
                count=snapshot.processed,
                files=len(snapshot.files),
            )
            return format_message(message, "success"), list(snapshot.files) or gr.update()
        if snapshot.status == "failed":
            return format_message(
                t("message.export.failed", error=snapshot.error or ""),
                "error",
            ), gr.update()
        if snapshot.status == "cancelled":
            return format_message(t("message.export.cancelled"), "info"), gr.update()

        phase = t(f"export.phase.{snapshot.phase}")
        progress = (
            f"{snapshot.processed}/{snapshot.total}"
            if snapshot.total is not None
            else str(snapshot.processed)
        )
        return format_message(
            t("message.export.progress", phase=phase, progress=progress),
            "info",
        ), gr.update()

    def cancel_job(self, job_id):
        if self.service.cancel_job(job_id):
            return format_message(t("message.export.cancelling"), "info")
        return format_message(t("message.export.nothing_to_cancel"), "info")

    def task_views(self):
        tasks = self.service.list_tasks()
        rows = [self._task_row(task) for task in tasks]
        choices = [(f"{task.id} · {task.name}", str(task.id)) for task in tasks]
        return rows, gr.update(choices=choices)

    def run_views(self):
        rows = []
        for run in self.service.list_runs(50):
            files = "\n".join(run.files)
            rows.append([
                run.id,
                run.task_id or "",
                run.run_type,
                run.chat_title or "",
                run.status,
                run.range_start or "",
                run.range_end or "",
                run.message_count,
                files,
                run.error or "",
                run.started_at,
                run.finished_at or "",
            ])
        return rows

    def refresh_task_views(self):
        rows, selector = self.task_views()
        return rows, selector, self.run_views()

    def save_task(
        self,
        task_id,
        name,
        chat_id,
        initial_start_at,
        formats,
        subdirectory,
        schedule_type,
        minute,
        hour,
        weekday,
        timezone_name,
        all_history,
        enabled,
    ):
        try:
            task = self.service.save_task(
                task_id=int(task_id) if task_id else None,
                name=name,
                chat_id=chat_id,
                initial_start_at=initial_start_at,
                formats=formats,
                subdirectory=subdirectory,
                schedule_type=schedule_type,
                minute=minute,
                hour=hour,
                weekday=weekday,
                timezone_name=timezone_name,
                all_history=all_history,
                enabled=enabled,
            )
            rows, selector = self.task_views()
            selector = gr.update(
                choices=selector.get("choices", []),
                value=str(task.id),
            )
            return (
                format_message(t("message.export.task_saved", name=task.name), "success"),
                rows,
                selector,
                self.run_views(),
            )
        except Exception as exc:
            return format_message(str(exc), "error"), gr.update(), gr.update(), gr.update()

    def load_task(self, task_id):
        if not task_id:
            return self.new_task_values()
        try:
            task = self.service.store.get_task(int(task_id))
            return (
                task.name,
                str(task.chat_id),
                datetime.fromisoformat(task.initial_start_at),
                list(task.formats),
                task.subdirectory,
                task.schedule_type,
                task.minute,
                task.hour,
                task.weekday,
                task.timezone,
                task.initial_start_at.startswith("1970-01-01"),
                task.enabled,
            )
        except Exception:
            return self.new_task_values()

    def new_task(self):
        return gr.update(value=None), *self.new_task_values()

    def new_task_values(self):
        timezone_name = self.service.config.export_timezone
        now = datetime.now(ZoneInfo(timezone_name))
        return (
            "",
            None,
            now - timedelta(days=30),
            ["json", "html"],
            "scheduled",
            "daily",
            0,
            2,
            0,
            timezone_name,
            False,
            True,
        )

    def toggle_task(self, task_id):
        if not task_id:
            return format_message(t("message.export.task_required"), "error"), *self.task_views(), self.run_views()
        try:
            current = self.service.store.get_task(int(task_id))
            task = self.service.set_task_enabled(current.id, not current.enabled)
            message = t(
                "message.export.task_toggled",
                name=task.name,
                status=t("export.enabled") if task.enabled else t("export.disabled"),
            )
            rows, selector = self.task_views()
            return format_message(message, "success"), rows, selector, self.run_views()
        except Exception as exc:
            rows, selector = self.task_views()
            return format_message(str(exc), "error"), rows, selector, self.run_views()

    def delete_task(self, task_id):
        if not task_id:
            return format_message(t("message.export.task_required"), "error"), *self.task_views(), self.run_views()
        try:
            task = self.service.store.get_task(int(task_id))
            self.service.delete_task(task.id)
            rows, selector = self.task_views()
            return (
                format_message(t("message.export.task_deleted", name=task.name), "success"),
                rows,
                gr.update(choices=selector.get("choices", []), value=None),
                self.run_views(),
            )
        except Exception as exc:
            rows, selector = self.task_views()
            return format_message(str(exc), "error"), rows, selector, self.run_views()

    def run_task_now(self, task_id):
        if not task_id:
            return format_message(t("message.export.task_required"), "error"), None
        try:
            job_id = self.scheduler.run_now(int(task_id))
            if job_id is None:
                return format_message(t("message.export.task_running"), "info"), None
            return format_message(t("message.export.started"), "info"), job_id
        except Exception as exc:
            return format_message(str(exc), "error"), None

    @staticmethod
    def _task_row(task):
        schedule = task.schedule_type
        if task.schedule_type == "hourly":
            schedule += f" :{task.minute:02d}"
        elif task.schedule_type == "daily":
            schedule += f" {task.hour:02d}:{task.minute:02d}"
        else:
            schedule += f" {task.weekday} {task.hour:02d}:{task.minute:02d}"
        return [
            task.id,
            task.name,
            task.chat_title,
            schedule,
            ", ".join(task.formats),
            task.next_run_at or "",
            task.last_success_at or "",
            task.last_message_id or "",
            t("export.enabled") if task.enabled else t("export.disabled"),
        ]
