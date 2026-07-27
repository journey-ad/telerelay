"""Log tab components and event bindings."""

import gradio as gr

from src.constants import DEFAULT_LOG_LINES, MAX_LOG_LINES, MIN_LOG_LINES
from src.i18n import t


class LogTab:
    def __init__(self, handler):
        self.handler = handler

    def build(self) -> None:
        with gr.Tab(t("ui.title.tab_log")):
            self.output = gr.Textbox(
                label=t("ui.label.realtime_log"),
                lines=25,
                max_lines=25,
                interactive=False,
                show_copy_button=True,
                elem_id="log_output",
                autoscroll=True,
            )
            with gr.Row():
                self.refresh_button = gr.Button(t("ui.button.refresh_log"), size="lg")
                self.lines = gr.Slider(
                    minimum=MIN_LOG_LINES,
                    maximum=MAX_LOG_LINES,
                    value=DEFAULT_LOG_LINES,
                    step=10,
                    label=t("ui.label.log_lines"),
                    scale=2,
                )

    def bind(self, app) -> None:
        self.refresh_button.click(
            fn=self.handler.get_recent_logs,
            inputs=self.lines,
            outputs=self.output,
        )
        app.load(
            fn=self.handler.get_recent_logs,
            inputs=self.lines,
            outputs=self.output,
        )
