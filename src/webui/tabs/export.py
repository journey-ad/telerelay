"""Data export tab components and event bindings."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import gradio as gr

from src.i18n import t


class ExportTab:
    """Keep export-specific components and bindings out of the main UI builder."""

    def __init__(self, config, handler):
        self.config = config
        self.handler = handler

    def build(self) -> None:
        now = datetime.now(ZoneInfo(self.config.export_timezone))
        task_rows, task_selector = self.handler.task_views()
        run_rows = self.handler.run_views()

        with gr.Tab(t("ui.title.tab_export")):
            self.availability = gr.Textbox(
                label=t("ui.label.export_availability"),
                value=self.handler.availability_message(),
                interactive=False,
            )
            self._build_group_export()
            self._build_message_export(now)
            self._build_task_export(now, task_rows, task_selector)
            self._build_run_history(run_rows)

    def _build_group_export(self) -> None:
        with gr.Accordion(t("ui.accordion.export_groups"), open=True):
            with gr.Row():
                self.group_formats = gr.CheckboxGroup(
                    choices=["json", "csv", "html"],
                    value=["json", "html"],
                    label=t("ui.label.export_formats"),
                    scale=2,
                )
                self.group_subdirectory = gr.Textbox(
                    value="groups",
                    label=t("ui.label.export_subdirectory"),
                    placeholder=t("ui.placeholder.export_subdirectory"),
                    info=t("ui.info.export_subdirectory"),
                    scale=2,
                )
            with gr.Row():
                self.export_groups_button = gr.Button(
                    t("ui.button.export_groups"),
                    variant="primary",
                )
                self.cancel_groups_button = gr.Button(
                    t("ui.button.cancel_export")
                )
            self.group_status = gr.Textbox(
                label=t("ui.label.export_status"),
                interactive=False,
            )
            self.group_files = self._file_output()
            self.group_job = gr.State(value=None)

    def _build_message_export(self, now: datetime) -> None:
        with gr.Accordion(t("ui.accordion.export_messages"), open=True):
            with gr.Row():
                self.message_chat = gr.Dropdown(
                    choices=[],
                    label=t("ui.label.export_chat"),
                    filterable=True,
                    scale=3,
                )
                self.refresh_chats_button = gr.Button(
                    t("ui.button.refresh_chats"),
                    scale=0,
                    min_width=130,
                )
            self.chat_status = gr.Textbox(
                label=t("ui.label.export_status"),
                interactive=False,
            )
            with gr.Row():
                self.message_start = self._datetime_input(
                    now - timedelta(days=30),
                    "ui.label.start_time",
                )
                self.message_end = self._datetime_input(
                    now,
                    "ui.label.end_time",
                )
                self.message_all_history = self._all_history_checkbox()
            with gr.Row():
                self.message_formats = gr.CheckboxGroup(
                    choices=["json", "csv", "html"],
                    value=["json", "html"],
                    label=t("ui.label.export_formats"),
                    scale=2,
                )
                self.message_subdirectory = gr.Textbox(
                    value="messages",
                    label=t("ui.label.export_subdirectory"),
                    placeholder=t("ui.placeholder.export_subdirectory"),
                    info=t("ui.info.export_subdirectory"),
                    scale=2,
                )
            with gr.Row():
                self.export_messages_button = gr.Button(
                    t("ui.button.export_messages"),
                    variant="primary",
                )
                self.cancel_messages_button = gr.Button(
                    t("ui.button.cancel_export")
                )
            self.message_status = gr.Textbox(
                label=t("ui.label.export_status"),
                interactive=False,
            )
            self.message_files = self._file_output()
            self.message_job = gr.State(value=None)

    def _build_task_export(self, now, task_rows, task_selector) -> None:
        with gr.Accordion(t("ui.accordion.export_tasks"), open=True):
            with gr.Row():
                self.task_selector = gr.Dropdown(
                    choices=task_selector.get("choices", []),
                    label=t("ui.label.task_selector"),
                    scale=3,
                )
                self.new_task_button = gr.Button(
                    t("ui.button.new_task"),
                    scale=0,
                    min_width=110,
                )
                self.refresh_tasks_button = gr.Button(
                    t("ui.button.refresh_tasks"),
                    scale=0,
                    min_width=120,
                )
            with gr.Row():
                self.task_name = gr.Textbox(
                    label=t("ui.label.task_name"),
                    placeholder=t("ui.placeholder.task_name"),
                )
                self.task_chat = gr.Dropdown(
                    choices=[],
                    label=t("ui.label.export_chat"),
                    filterable=True,
                )
                self.task_enabled = gr.Checkbox(
                    value=True,
                    label=t("ui.label.task_enabled"),
                )
            with gr.Row():
                self.task_start = self._datetime_input(
                    now - timedelta(days=30),
                    "ui.label.start_time",
                )
                self.task_all_history = self._all_history_checkbox()
                self.task_formats = gr.CheckboxGroup(
                    choices=["json", "csv", "html"],
                    value=["json", "html"],
                    label=t("ui.label.export_formats"),
                )
            with gr.Row():
                self.task_subdirectory = gr.Textbox(
                    value="scheduled",
                    label=t("ui.label.export_subdirectory"),
                    placeholder=t("ui.placeholder.export_subdirectory"),
                    info=t("ui.info.export_subdirectory"),
                )
                self.task_timezone = gr.Textbox(
                    value=self.config.export_timezone,
                    label=t("ui.label.timezone"),
                )
                self.schedule_type = gr.Dropdown(
                    choices=[
                        (t("export.schedule.hourly"), "hourly"),
                        (t("export.schedule.daily"), "daily"),
                        (t("export.schedule.weekly"), "weekly"),
                    ],
                    value="daily",
                    label=t("ui.label.schedule_type"),
                )
            with gr.Row():
                self.schedule_minute = gr.Number(
                    value=0,
                    minimum=0,
                    maximum=59,
                    precision=0,
                    label=t("ui.label.schedule_minute"),
                    info=t("ui.info.schedule_minute"),
                )
                self.schedule_hour = gr.Number(
                    value=2,
                    minimum=0,
                    maximum=23,
                    precision=0,
                    label=t("ui.label.schedule_hour"),
                    info=t("ui.info.schedule_hour"),
                )
                self.schedule_weekday = gr.Dropdown(
                    choices=[
                        (t(f"export.weekday.{day}"), day)
                        for day in range(7)
                    ],
                    value=0,
                    label=t("ui.label.schedule_weekday"),
                    info=t("ui.info.schedule_weekday"),
                )
            with gr.Row():
                self.save_task_button = gr.Button(
                    t("ui.button.save_task"),
                    variant="primary",
                )
                self.run_task_button = gr.Button(t("ui.button.run_now"))
                self.toggle_task_button = gr.Button(t("ui.button.toggle_task"))
                self.delete_task_button = gr.Button(
                    t("ui.button.delete_task"),
                    variant="stop",
                )
            self.task_status = gr.Textbox(
                label=t("ui.label.task_operation"),
                interactive=False,
            )
            self.task_files = self._file_output()
            self.task_job = gr.State(value=None)
            self.task_table = gr.Dataframe(
                headers=[
                    "id",
                    "name",
                    "chat",
                    "schedule",
                    "formats",
                    "next_run",
                    "last_success",
                    "cursor",
                    "status",
                ],
                datatype=[
                    "number",
                    "str",
                    "str",
                    "str",
                    "str",
                    "str",
                    "str",
                    "str",
                    "str",
                ],
                value=task_rows,
                interactive=False,
                row_count=(1, "dynamic"),
                label=t("ui.label.task_table"),
            )

    def _build_run_history(self, run_rows) -> None:
        with gr.Accordion(t("ui.accordion.export_runs"), open=False):
            self.run_table = gr.Dataframe(
                headers=[
                    "id",
                    "task_id",
                    "type",
                    "chat",
                    "status",
                    "start",
                    "end",
                    "count",
                    "files",
                    "error",
                    "started_at",
                    "finished_at",
                ],
                datatype=[
                    "number",
                    "str",
                    "str",
                    "str",
                    "str",
                    "str",
                    "str",
                    "number",
                    "str",
                    "str",
                    "str",
                    "str",
                ],
                value=run_rows,
                interactive=False,
                row_count=(1, "dynamic"),
                label=t("ui.label.run_history"),
            )

    @staticmethod
    def _datetime_input(value, label_key):
        return gr.DateTime(
            value=value,
            include_time=True,
            type="datetime",
            label=t(label_key),
        )

    @staticmethod
    def _all_history_checkbox():
        return gr.Checkbox(
            value=False,
            label=t("ui.label.all_history"),
            info=t("ui.info.all_history"),
        )

    @staticmethod
    def _file_output():
        return gr.File(
            label=t("ui.label.export_files"),
            file_count="multiple",
            type="filepath",
        )

    def _task_form_components(self):
        return [
            self.task_name,
            self.task_chat,
            self.task_start,
            self.task_formats,
            self.task_subdirectory,
            self.schedule_type,
            self.schedule_minute,
            self.schedule_hour,
            self.schedule_weekday,
            self.task_timezone,
            self.task_all_history,
            self.task_enabled,
        ]

    def _task_view_components(self):
        return [self.task_table, self.task_selector, self.run_table]

    def _refresh_chat_choices(self):
        update, status = self.handler.refresh_chats()
        return update, dict(update), status

    def bind(self, app, progress_timer, table_timer) -> None:
        self.refresh_chats_button.click(
            fn=self._refresh_chat_choices,
            outputs=[self.message_chat, self.task_chat, self.chat_status],
        )
        self.export_groups_button.click(
            fn=self.handler.start_group_export,
            inputs=[self.group_formats, self.group_subdirectory],
            outputs=[self.group_status, self.group_job],
        )
        self.cancel_groups_button.click(
            fn=self.handler.cancel_job,
            inputs=self.group_job,
            outputs=self.group_status,
        )
        self.export_messages_button.click(
            fn=self.handler.start_message_export,
            inputs=[
                self.message_chat,
                self.message_start,
                self.message_end,
                self.message_formats,
                self.message_subdirectory,
                self.message_all_history,
            ],
            outputs=[self.message_status, self.message_job],
        )
        self.cancel_messages_button.click(
            fn=self.handler.cancel_job,
            inputs=self.message_job,
            outputs=self.message_status,
        )

        task_form = self._task_form_components()
        self.task_selector.change(
            fn=self.handler.load_task,
            inputs=self.task_selector,
            outputs=task_form,
        )
        self.new_task_button.click(
            fn=self.handler.new_task,
            outputs=[self.task_selector, *task_form],
        )
        self.save_task_button.click(
            fn=self.handler.save_task,
            inputs=[self.task_selector, *task_form],
            outputs=[self.task_status, *self._task_view_components()],
        )
        self.refresh_tasks_button.click(
            fn=self.handler.refresh_task_views,
            outputs=self._task_view_components(),
        )
        self.toggle_task_button.click(
            fn=self.handler.toggle_task,
            inputs=self.task_selector,
            outputs=[self.task_status, *self._task_view_components()],
        )
        self.delete_task_button.click(
            fn=self.handler.delete_task,
            inputs=self.task_selector,
            outputs=[self.task_status, *self._task_view_components()],
        )
        self.run_task_button.click(
            fn=self.handler.run_task_now,
            inputs=self.task_selector,
            outputs=[self.task_status, self.task_job],
        )

        progress_timer.tick(
            fn=self.handler.poll_job,
            inputs=self.group_job,
            outputs=[self.group_status, self.group_files],
        )
        progress_timer.tick(
            fn=self.handler.poll_job,
            inputs=self.message_job,
            outputs=[self.message_status, self.message_files],
        )
        progress_timer.tick(
            fn=self.handler.poll_job,
            inputs=self.task_job,
            outputs=[self.task_status, self.task_files],
        )
        table_timer.tick(
            fn=self.handler.refresh_task_views,
            outputs=self._task_view_components(),
        )
        table_timer.tick(
            fn=self.handler.availability_message,
            outputs=self.availability,
        )

        app.load(
            fn=self._refresh_chat_choices,
            outputs=[self.message_chat, self.task_chat, self.chat_status],
        )
        app.load(
            fn=self.handler.refresh_task_views,
            outputs=self._task_view_components(),
        )
