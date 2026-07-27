"""Statistics tab components and event bindings."""

import gradio as gr

from src.i18n import t


class StatsTab:
    def __init__(self, handler):
        self.handler = handler

    def build(self) -> None:
        with gr.Tab(t("ui.title.tab_stats")):
            gr.Markdown(f"### {t('ui.label.rule_stats')}")
            self.table = gr.Dataframe(
                headers=[
                    t("ui.label.rule_name"),
                    t("ui.label.forwarded"),
                    t("ui.label.filtered"),
                    t("ui.label.total"),
                ],
                datatype=["str", "number", "number", "number"],
                interactive=False,
                row_count=(1, "dynamic"),
            )
            gr.Markdown(f"### {t('ui.label.daily_trend')}")
            with gr.Row():
                self.days = gr.Slider(
                    minimum=7,
                    maximum=90,
                    value=30,
                    step=1,
                    label=t("ui.label.days_range"),
                    scale=2,
                )
                self.refresh_button = gr.Button(
                    t("ui.button.refresh_stats"), scale=0, min_width=100
                )
            self.plot = gr.Plot(label=t("ui.label.daily_trend"))
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
        self.refresh_button.click(
            fn=self._refresh,
            inputs=self.days,
            outputs=[self.table, self.plot],
        )
        self.export_button.click(
            fn=self.handler.export_stats,
            inputs=self.export_format,
            outputs=self.export_file,
        )
        app.load(fn=self._refresh, inputs=self.days, outputs=[self.table, self.plot])

    def _refresh(self, days):
        return (
            self.handler.get_rule_detail_table(),
            self.handler.get_daily_trend_plot(int(days)),
        )
