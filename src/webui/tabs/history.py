"""Message history tab components and event bindings."""

import gradio as gr

from src.i18n import t


class HistoryTab:
    def __init__(self, handler):
        self.handler = handler

    def build(self) -> None:
        with gr.Tab(t("ui.title.tab_history")):
            with gr.Row():
                self.rule_filter = gr.Dropdown(
                    choices=self.handler.get_rule_choices(),
                    value="",
                    label=t("ui.label.rule_filter"),
                    scale=1,
                )
                self.keyword = gr.Textbox(
                    label=t("ui.label.search_keyword"),
                    placeholder=t("ui.placeholder.search_keyword"),
                    scale=2,
                )
                self.search_button = gr.Button(
                    t("ui.button.search"), variant="primary", scale=0, min_width=100
                )
            self.table = gr.Dataframe(
                headers=[
                    "time",
                    "rule_name",
                    "source_chat_id",
                    "source_chat_name",
                    "sender_name",
                    "username",
                    "content",
                    "media_type",
                ],
                datatype=["str", "str", "str", "str", "str", "str", "str", "str"],
                interactive=False,
                row_count=(1, "dynamic"),
            )
            with gr.Row():
                self.previous_button = gr.Button(
                    t("ui.button.prev_page"), scale=0, min_width=80
                )
                self.page_info = gr.Textbox(
                    value="1/1 (0)",
                    interactive=False,
                    label=t("ui.label.page_info_label"),
                    scale=1,
                )
                self.next_button = gr.Button(
                    t("ui.button.next_page"), scale=0, min_width=80
                )
                self.page = gr.State(value=1)
                self.total_pages = gr.State(value=1)
            with gr.Row():
                self.export_format = gr.Dropdown(
                    choices=["csv", "json", "html"],
                    value="csv",
                    label=t("ui.label.export_format"),
                    scale=1,
                )
                self.export_button = gr.Button(
                    t("ui.button.export"), scale=0, min_width=100
                )
                self.export_file = gr.File(
                    label=t("ui.label.export_file"), visible=True, scale=2
                )

    def bind(self, app) -> None:
        search_inputs = [self.rule_filter, self.keyword, self.page]
        search_outputs = [self.table, self.page_info, self.total_pages, self.page]
        self.search_button.click(
            fn=self._search, inputs=search_inputs, outputs=search_outputs
        )
        self.keyword.submit(
            fn=self._search, inputs=search_inputs, outputs=search_outputs
        )
        page_inputs = [
            self.rule_filter,
            self.keyword,
            self.page,
            self.total_pages,
        ]
        self.previous_button.click(
            fn=self._previous, inputs=page_inputs, outputs=search_outputs
        )
        self.next_button.click(
            fn=self._next, inputs=page_inputs, outputs=search_outputs
        )
        self.export_button.click(
            fn=self.handler.export_data,
            inputs=[self.rule_filter, self.keyword, self.export_format],
            outputs=self.export_file,
        )

    def _search(self, rule, keyword, _page):
        data, info, total_pages = self.handler.search(rule, keyword, 1)
        return data, info, total_pages, 1

    def _previous(self, rule, keyword, page, _total):
        new_page = max(1, page - 1)
        data, info, total_pages = self.handler.search(rule, keyword, new_page)
        return data, info, total_pages, new_page

    def _next(self, rule, keyword, page, total):
        new_page = min(total, page + 1)
        data, info, total_pages = self.handler.search(rule, keyword, new_page)
        return data, info, total_pages, new_page
