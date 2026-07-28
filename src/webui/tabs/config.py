"""Configuration tab components and event bindings."""

import gradio as gr

from src.i18n import t


class ConfigTab:
    """Build forwarding and message-button configuration areas."""

    def __init__(self, handler):
        self.handler = handler

    def build(self) -> None:
        rule_names = self.handler.get_rule_names()
        button_rule_names = self.handler.get_button_action_rule_names()

        with gr.Tab(t("ui.title.tab_config")):
            with gr.Tabs():
                with gr.Tab(t("ui.title.config_forwarding_rules")):
                    self._build_forwarding_area(rule_names)
                with gr.Tab(t("ui.title.config_button_actions")):
                    self._build_button_action_area(button_rule_names)

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
        self.button_action_components = {
            "enabled": self.button_action_enabled,
            "source_chats": self.button_action_source_chats,
            "button_texts": self.button_action_texts,
            "match_mode": self.button_action_match_mode,
            "delay": self.button_action_delay,
            "click_all_matches": self.button_action_click_all_matches,
        }

    def _build_forwarding_area(self, rule_names) -> None:
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

    def _build_button_action_area(self, rule_names) -> None:
        gr.Markdown(t("ui.markdown.button_action_guide"))
        with gr.Group():
            with gr.Row():
                self.button_action_selector = gr.Dropdown(
                    choices=rule_names,
                    value=rule_names[0],
                    label=t("ui.label.current_button_action_rule"),
                    scale=3,
                    interactive=True,
                )
                self.add_button_action_button = gr.Button(
                    t("ui.button.add_rule"), scale=0, min_width=50
                )
                self.delete_button_action_button = gr.Button(
                    t("ui.button.delete_rule"), scale=0, min_width=50
                )
                self.rename_button_action_button = gr.Button(
                    t("ui.button.rename_rule"), scale=0, min_width=50
                )
                self.button_action_enabled = gr.Checkbox(
                    label=t("ui.label.enable"), value=False, scale=0, min_width=80
                )

            self.button_action_rename_input = gr.Textbox(
                label=t("ui.label.new_name"),
                placeholder=t("ui.placeholder.new_name"),
                visible=False,
            )

        self.button_action_source_chats = gr.Textbox(
            label=t("ui.label.button_action_source_chats"),
            placeholder=t("ui.placeholder.button_action_source_chats"),
            lines=4,
            info=t("ui.info.button_action_source_chats"),
        )
        self.button_action_texts = gr.Textbox(
            label=t("ui.label.button_action_texts"),
            placeholder=t("ui.placeholder.button_action_texts"),
            lines=4,
            info=t("ui.info.button_action_texts"),
        )
        self.button_action_match_mode = gr.Radio(
            choices=["exact", "contains", "regex"],
            value="exact",
            label=t("ui.label.button_action_match_mode"),
            info=t("ui.info.button_action_match_mode"),
        )
        self.button_action_click_all_matches = gr.Checkbox(
            label=t("ui.label.button_action_click_all_matches"),
            value=False,
        )
        self.button_action_delay = gr.Slider(
            minimum=0,
            maximum=30,
            value=0,
            step=0.1,
            label=t("ui.label.button_action_delay"),
            info=t("ui.info.button_action_delay"),
        )
        self.save_button_action_button = gr.Button(
            t("ui.button.save_button_action"), variant="primary", size="lg"
        )
        self.button_action_save_message = gr.Textbox(
            label=t("ui.label.save_result"), visible=False
        )

    def bind(self, app) -> None:
        outputs = list(self.components.values())
        button_outputs = list(self.button_action_components.values())

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

        self.save_button_action_button.click(
            fn=self._save_current_button_action_rule,
            inputs=[self.button_action_selector, *button_outputs],
            outputs=self.button_action_save_message,
        ).then(
            fn=self._update_message_visibility,
            inputs=self.button_action_save_message,
            outputs=self.button_action_save_message,
        )
        self.button_action_selector.change(
            fn=self._load_button_action_values,
            inputs=self.button_action_selector,
            outputs=button_outputs,
        )
        self.add_button_action_button.click(
            fn=self._add_button_action_rule,
            outputs=self.button_action_selector,
        ).then(
            fn=self._load_button_action_values,
            inputs=self.button_action_selector,
            outputs=button_outputs,
        )
        self.delete_button_action_button.click(
            fn=self._delete_button_action_rule,
            inputs=self.button_action_selector,
            outputs=self.button_action_selector,
        ).then(
            fn=self._load_button_action_values,
            inputs=self.button_action_selector,
            outputs=button_outputs,
        )
        self.rename_button_action_button.click(
            fn=lambda: gr.update(visible=True),
            outputs=self.button_action_rename_input,
        )
        self.button_action_rename_input.submit(
            fn=self._rename_button_action_rule,
            inputs=[self.button_action_selector, self.button_action_rename_input],
            outputs=[self.button_action_selector, self.button_action_rename_input],
        )

        app.load(fn=self._load_config_values, outputs=outputs)
        app.load(fn=self._load_default_button_action_values, outputs=button_outputs)

    @staticmethod
    def _update_message_visibility(message: str) -> dict:
        return gr.update(visible=bool(message))

    def _rule_index(self, rule_name: str) -> int:
        names = self.handler.get_rule_names()
        return names.index(rule_name) if rule_name in names else 0

    def _button_action_rule_index(self, rule_name: str) -> int:
        names = self.handler.get_button_action_rule_names()
        return names.index(rule_name) if rule_name in names else 0

    def _load_rule_values(self, rule_name: str):
        config = self.handler.load_rule(self._rule_index(rule_name))
        return [config.get(key, "") for key in self.components]

    def _load_config_values(self):
        config = self.handler.load_config()
        return [config.get(key, "") for key in self.components]

    def _load_button_action_values(self, rule_name: str):
        config = self.handler.load_button_action_rule(
            self._button_action_rule_index(rule_name)
        )
        return [config.get(key, "") for key in self.button_action_components]

    def _load_default_button_action_values(self):
        config = self.handler.load_button_action_rule(0)
        return [config.get(key, "") for key in self.button_action_components]

    def _save_current_rule(self, rule_name, *values):
        return self.handler.save_rule(self._rule_index(rule_name), *values)

    def _save_current_button_action_rule(self, rule_name, *values):
        return self.handler.save_button_action_rule(
            self._button_action_rule_index(rule_name), *values
        )

    def _add_rule(self):
        _, names, new_index = self.handler.add_rule("")
        return gr.update(choices=names, value=names[new_index])

    def _add_button_action_rule(self):
        _, names, new_index = self.handler.add_button_action_rule("")
        return gr.update(choices=names, value=names[new_index])

    def _delete_rule(self, rule_name):
        _, names, new_index = self.handler.delete_rule(self._rule_index(rule_name))
        value = names[new_index] if names else t("ui.status.default_rule")
        return gr.update(choices=names, value=value)

    def _delete_button_action_rule(self, rule_name):
        _, names, new_index = self.handler.delete_button_action_rule(
            self._button_action_rule_index(rule_name)
        )
        value = (
            names[new_index]
            if names
            else t("ui.status.default_button_action_rule")
        )
        return gr.update(choices=names, value=value)

    def _rename_rule(self, rule_name, new_name):
        _, names = self.handler.rename_rule(self._rule_index(rule_name), new_name)
        selector = gr.update(
            choices=names, value=new_name if new_name else rule_name
        )
        return selector, gr.update(visible=False)

    def _rename_button_action_rule(self, rule_name, new_name):
        _, names = self.handler.rename_button_action_rule(
            self._button_action_rule_index(rule_name), new_name
        )
        selector = gr.update(
            choices=names, value=new_name if new_name else rule_name
        )
        return selector, gr.update(visible=False)

    def _toggle_rule(self, rule_name, enabled):
        self.handler.toggle_rule(self._rule_index(rule_name), enabled)
