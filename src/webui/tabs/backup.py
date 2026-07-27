"""Configuration backup tab components and event bindings."""

import gradio as gr

from src.i18n import t


class BackupTab:
    def __init__(self, handler):
        self.handler = handler

    def build(self) -> None:
        with gr.Tab(t("ui.title.tab_backup")):
            gr.Markdown(t("ui.markdown.backup_guide"))
            with gr.Group():
                gr.Markdown(f"#### {t('ui.label.export_config')}")
                self.export_button = gr.Button(
                    t("ui.button.export_config"), variant="primary"
                )
                self.export_file = gr.File(
                    label=t("ui.label.export_file"), visible=True
                )
            with gr.Group():
                gr.Markdown(f"#### {t('ui.label.import_config')}")
                self.upload = gr.File(
                    label=t("ui.label.upload_config"), file_types=[".yaml", ".yml"]
                )
                self.import_button = gr.Button(
                    t("ui.button.import_config"), variant="secondary"
                )
                self.import_message = gr.Textbox(
                    label=t("ui.label.operation_message"), visible=False
                )

    def bind(self, app) -> None:
        self.export_button.click(
            fn=self.handler.export_config, outputs=self.export_file
        )
        self.import_button.click(
            fn=self.handler.import_config,
            inputs=self.upload,
            outputs=self.import_message,
        ).then(
            fn=self._update_message_visibility,
            inputs=self.import_message,
            outputs=self.import_message,
        )

    @staticmethod
    def _update_message_visibility(message: str) -> dict:
        return gr.update(visible=bool(message))
