"""Configuration tab components and event bindings."""

import gradio as gr

from src.i18n import t


class ConfigTab:
    """Build and bind the forwarding-rule configuration tab."""

    def __init__(self, handler):
        self.handler = handler

    def build(self) -> None:
        rule_names = self.handler.get_rule_names()
        with gr.Tab(t("ui.title.tab_config")):
            with gr.Group():
                with gr.Row():
                    self.rule_selector = gr.Dropdown(
                        choices=rule_names,
                        value=rule_names[0] if rule_names else t("ui.status.default_rule"),
                        label=t("ui.label.current_rule"),
                        scale=3,
                        interactive=True,
                    )
                    self.add_rule_button = gr.Button(
                        t("ui.button.add_rule"), scale=0, min_width=50
                    )
                    self.delete_rule_button = gr.Button(
                        t("ui.button.delete_rule"), scale=0, min_width=50
                    )
                    self.rename_rule_button = gr.Button(
                        t("ui.button.rename_rule"), scale=0, min_width=50
                    )
                    self.rule_enabled = gr.Checkbox(
                        label=t("ui.label.enable"), value=True, scale=0, min_width=80
                    )

                self.rename_input = gr.Textbox(
                    label=t("ui.label.new_name"),
                    placeholder=t("ui.placeholder.new_name"),
                    visible=False,
                )

            with gr.Accordion(t("ui.accordion.source_target"), open=True):
                self.source_chats = gr.Textbox(
                    label=t("ui.label.source_chats"),
                    placeholder=t("ui.placeholder.source_chats"),
                    lines=4,
                    info=t("ui.info.source_chats"),
                )
                self.target_chats = gr.Textbox(
                    label=t("ui.label.target_chats"),
                    placeholder=t("ui.placeholder.target_chats"),
                    lines=4,
                    info=t("ui.info.target_chats"),
                )

            with gr.Accordion(t("ui.accordion.filter_rules"), open=True):
                self.regex_patterns = gr.Textbox(
                    label=t("ui.label.regex_patterns"),
                    placeholder=t("ui.placeholder.regex_patterns"),
                    lines=3,
                    info=t("ui.info.regex_patterns"),
                )
                self.keywords = gr.Textbox(
                    label=t("ui.label.keywords"),
                    placeholder=t("ui.placeholder.keywords"),
                    lines=3,
                    info=t("ui.info.keywords"),
                )
                self.filter_mode = gr.Radio(
                    choices=["whitelist", "blacklist"],
                    value="whitelist",
                    label=t("ui.label.filter_mode"),
                    info=t("ui.info.filter_mode"),
                )
                self.media_types = gr.CheckboxGroup(
                    choices=[
                        "text",
                        "photo",
                        "video",
                        "document",
                        "audio",
                        "voice",
                        "sticker",
                        "animation",
                    ],
                    label=t("ui.label.media_types"),
                    info=t("ui.info.media_types"),
                )
                self.max_file_size = gr.Number(
                    label=t("ui.label.max_file_size"),
                    value=0,
                    minimum=0,
                    info=t("ui.info.max_file_size"),
                )

            with gr.Accordion(t("ui.accordion.ignore_list"), open=True):
                gr.Markdown(t("ui.markdown.ignore_warning"))
                self.ignored_user_ids = gr.Textbox(
                    label=t("ui.label.ignored_user_ids"),
                    placeholder=t("ui.placeholder.ignored_user_ids"),
                    lines=3,
                    info=t("ui.info.ignored_user_ids"),
                )
                self.ignored_keywords = gr.Textbox(
                    label=t("ui.label.ignored_keywords"),
                    placeholder=t("ui.placeholder.ignored_keywords"),
                    lines=3,
                    info=t("ui.info.ignored_keywords"),
                )

            with gr.Accordion(t("ui.accordion.forward_options"), open=True):
                self.preserve_format = gr.Checkbox(
                    label=t("ui.label.preserve_format"),
                    value=True,
                    info=t("ui.info.preserve_format"),
                )
                self.add_source_info = gr.Checkbox(
                    label=t("ui.label.add_source_info"),
                    value=True,
                    info=t("ui.info.add_source_info"),
                )
                self.force_forward = gr.Checkbox(
                    label=t("ui.label.force_forward"),
                    value=False,
                    info=t("ui.info.force_forward"),
                )
                self.hide_sender = gr.Checkbox(
                    label=t("ui.label.hide_sender"),
                    value=False,
                    info=t("ui.info.hide_sender"),
                )
                self.delay = gr.Slider(
                    minimum=0,
                    maximum=5,
                    value=0.5,
                    step=0.1,
                    label=t("ui.label.delay"),
                    info=t("ui.info.delay"),
                )

            self.save_button = gr.Button(
                t("ui.button.save_config"), variant="primary", size="lg"
            )
            self.save_message = gr.Textbox(
                label=t("ui.label.save_result"), visible=False
            )

        self.components = {
            "source_chats": self.source_chats,
            "target_chats": self.target_chats,
            "regex_patterns": self.regex_patterns,
            "keywords": self.keywords,
            "filter_mode": self.filter_mode,
            "media_types": self.media_types,
            "max_file_size": self.max_file_size,
            "ignored_user_ids": self.ignored_user_ids,
            "ignored_keywords": self.ignored_keywords,
            "preserve_format": self.preserve_format,
            "add_source_info": self.add_source_info,
            "force_forward": self.force_forward,
            "hide_sender": self.hide_sender,
            "delay": self.delay,
            "enabled": self.rule_enabled,
        }

    def bind(self, app) -> None:
        outputs = list(self.components.values())

        self.save_button.click(
            fn=self._save_current_rule,
            inputs=[self.rule_selector, *outputs],
            outputs=self.save_message,
        ).then(
            fn=self._update_message_visibility,
            inputs=self.save_message,
            outputs=self.save_message,
        )
        self.rule_selector.change(
            fn=self._load_rule_values,
            inputs=self.rule_selector,
            outputs=outputs,
        )
        self.add_rule_button.click(
            fn=self._add_rule,
            outputs=self.rule_selector,
        ).then(
            fn=self._load_rule_values,
            inputs=self.rule_selector,
            outputs=outputs,
        )
        self.delete_rule_button.click(
            fn=self._delete_rule,
            inputs=self.rule_selector,
            outputs=self.rule_selector,
        ).then(
            fn=self._load_rule_values,
            inputs=self.rule_selector,
            outputs=outputs,
        )
        self.rename_rule_button.click(
            fn=lambda: gr.update(visible=True),
            outputs=self.rename_input,
        )
        self.rename_input.submit(
            fn=self._rename_rule,
            inputs=[self.rule_selector, self.rename_input],
            outputs=[self.rule_selector, self.rename_input],
        )
        self.rule_enabled.change(
            fn=self._toggle_rule,
            inputs=[self.rule_selector, self.rule_enabled],
        )
        app.load(fn=self._load_config_values, outputs=outputs)

    @staticmethod
    def _update_message_visibility(message: str) -> dict:
        return gr.update(visible=bool(message))

    def _rule_index(self, rule_name: str) -> int:
        names = self.handler.get_rule_names()
        return names.index(rule_name) if rule_name in names else 0

    def _load_rule_values(self, rule_name: str):
        config = self.handler.load_rule(self._rule_index(rule_name))
        return [config.get(key, "") for key in self.components]

    def _load_config_values(self):
        config = self.handler.load_config()
        return [config.get(key, "") for key in self.components]

    def _save_current_rule(self, rule_name, *values):
        return self.handler.save_rule(self._rule_index(rule_name), *values)

    def _add_rule(self):
        _, names, new_index = self.handler.add_rule("")
        return gr.update(choices=names, value=names[new_index])

    def _delete_rule(self, rule_name):
        _, names, new_index = self.handler.delete_rule(self._rule_index(rule_name))
        value = names[new_index] if names else t("ui.status.default_rule")
        return gr.update(choices=names, value=value)

    def _rename_rule(self, rule_name, new_name):
        _, names = self.handler.rename_rule(self._rule_index(rule_name), new_name)
        selector = gr.update(
            choices=names, value=new_name if new_name else rule_name
        )
        return selector, gr.update(visible=False)

    def _toggle_rule(self, rule_name, enabled):
        self.handler.toggle_rule(self._rule_index(rule_name), enabled)
