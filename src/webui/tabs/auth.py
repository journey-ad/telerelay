"""Authentication tab components and event bindings."""

import gradio as gr

from src.i18n import t


class AuthTab:
    def __init__(self, handler):
        self.handler = handler

    def build(self) -> None:
        with gr.Tab(t("ui.title.tab_auth")):
            gr.Markdown(t("ui.markdown.auth_guide"))
            self.status = gr.Textbox(
                label=t("ui.label.auth_status"),
                value=t("ui.auth.idle"),
                interactive=False,
            )
            with gr.Row():
                self.start_button = gr.Button(
                    t("ui.button.start_auth"), variant="primary"
                )
                self.cancel_button = gr.Button(
                    t("ui.button.cancel_auth"), variant="stop"
                )
            self.phone_input = gr.Textbox(
                label=t("ui.label.phone"),
                placeholder=t("ui.placeholder.phone"),
                info=t("ui.info.phone"),
                visible=False,
            )
            self.submit_phone_button = gr.Button(
                t("ui.button.send_code"), variant="primary", visible=False
            )
            self.code_input = gr.Textbox(
                label=t("ui.label.code"),
                placeholder=t("ui.placeholder.code"),
                info=t("ui.info.code"),
                visible=False,
            )
            self.submit_code_button = gr.Button(
                t("ui.button.submit_code"), variant="primary", visible=False
            )
            self.password_input = gr.Textbox(
                label=t("ui.label.password"),
                type="password",
                placeholder=t("ui.placeholder.password"),
                info=t("ui.info.password"),
                visible=False,
            )
            self.submit_password_button = gr.Button(
                t("ui.button.submit_password"), variant="primary", visible=False
            )
            self.error = gr.Textbox(label=t("ui.label.error_info"), visible=False)

    def bind(self, app) -> None:
        self.start_button.click(fn=self.handler.start_auth, outputs=self.status)
        self.cancel_button.click(fn=self.handler.cancel_auth, outputs=self.status)
        self.submit_phone_button.click(
            fn=self.handler.submit_phone,
            inputs=self.phone_input,
            outputs=self.status,
        ).then(fn=lambda: "", outputs=self.phone_input)
        self.submit_code_button.click(
            fn=self.handler.submit_code,
            inputs=self.code_input,
            outputs=self.status,
        ).then(fn=lambda: "", outputs=self.code_input)
        self.submit_password_button.click(
            fn=self.handler.submit_password,
            inputs=self.password_input,
            outputs=self.status,
        ).then(fn=lambda: "", outputs=self.password_input)

    @property
    def refresh_outputs(self):
        return [
            self.status,
            self.phone_input,
            self.submit_phone_button,
            self.code_input,
            self.submit_code_button,
            self.password_input,
            self.submit_password_button,
            self.error,
        ]
