"""Gradio UI composition and global controls."""

from typing import Optional

import gradio as gr

from src.auth_manager import AuthManager
from src.bot_manager import BotManager
from src.config import Config
from src.constants import UI_REFRESH_INTERVAL
from src.i18n import t

from .handlers import (
    AuthHandler,
    BackupHandler,
    BotControlHandler,
    ConfigHandler,
    ExportHandler,
    HistoryHandler,
    LogHandler,
    StatsHandler,
)
from .tabs import (
    AuthTab,
    BackupTab,
    ConfigTab,
    ExportTab,
    HistoryTab,
    LogTab,
    StatsTab,
)


def create_ui(
    config: Config,
    bot_manager: BotManager,
    auth_manager: Optional[AuthManager] = None,
    export_service=None,
    export_scheduler=None,
) -> gr.Blocks:
    """Create the Gradio interface."""
    bot_handler = BotControlHandler(bot_manager, config)
    auth_handler = AuthHandler(auth_manager, bot_manager) if auth_manager else None

    config_tab = ConfigTab(ConfigHandler(config, bot_manager))
    log_handler = LogHandler()
    log_tab = LogTab(log_handler)
    stats_tab = StatsTab(StatsHandler())
    history_tab = HistoryTab(HistoryHandler())
    backup_tab = BackupTab(BackupHandler(config, bot_manager))
    auth_tab = AuthTab(auth_handler) if auth_handler else None

    export_handler = (
        ExportHandler(export_service, export_scheduler)
        if export_service and export_scheduler
        else None
    )
    export_tab = ExportTab(config, export_handler) if export_handler else None

    theme = gr.themes.Soft(primary_hue="blue", secondary_hue="gray")
    with gr.Blocks(title=t("ui.title.main"), theme=theme) as app:
        gr.Markdown(f"# {t('ui.title.main')}")
        gr.Markdown(t("ui.title.subtitle"))

        timer = gr.Timer(value=UI_REFRESH_INTERVAL)
        export_timer = gr.Timer(value=1.0) if export_tab else None
        export_table_timer = gr.Timer(value=5.0) if export_tab else None

        with gr.Row():
            start_button = gr.Button(
                t("ui.button.start"), variant="primary", size="lg"
            )
            stop_button = gr.Button(t("ui.button.stop"), variant="stop", size="lg")
            restart_button = gr.Button(
                t("ui.button.restart"), variant="secondary", size="lg"
            )
            refresh_status_button = gr.Button(
                t("ui.button.refresh_status"), size="lg"
            )

        with gr.Row():
            status_text = gr.Textbox(
                label=t("ui.label.status"),
                value=t("ui.status.stopped"),
                interactive=False,
                scale=2,
            )
            forwarded_count = gr.Textbox(
                label=t("ui.label.forwarded"),
                value="0",
                interactive=False,
                scale=1,
            )
            filtered_count = gr.Textbox(
                label=t("ui.label.filtered"),
                value="0",
                interactive=False,
                scale=1,
            )
            total_count = gr.Textbox(
                label=t("ui.label.total"),
                value="0",
                interactive=False,
                scale=1,
            )
            reset_stats_button = gr.Button(
                t("ui.button.reset_stats"), size="sm", scale=0, min_width=80
            )

        control_message = gr.Textbox(
            label=t("ui.label.operation_message"), visible=False
        )

        with gr.Tabs():
            config_tab.build()
            log_tab.build()
            stats_tab.build()
            history_tab.build()
            if export_tab:
                export_tab.build()
            backup_tab.build()
            if auth_tab:
                auth_tab.build()

        def update_message_visibility(message: str) -> dict:
            return gr.update(visible=bool(message))

        def auto_refresh_all(lines):
            results = []
            if bot_manager and bot_manager.check_and_clear_ui_update():
                status = bot_handler.get_status()
                logs = log_handler.get_recent_logs(lines)
                auth_message = bot_handler.get_auth_success_message()
                message_update = (
                    gr.update(value=auth_message, visible=True)
                    if auth_message
                    else gr.update()
                )
                results.extend([*status, logs, message_update])
            else:
                results.extend([gr.update()] * 6)

            if auth_handler:
                results.extend(auth_handler.get_auth_state())
            return tuple(results)

        status_outputs = [
            status_text,
            forwarded_count,
            filtered_count,
            total_count,
        ]

        start_button.click(
            fn=bot_handler.start_bot, outputs=control_message
        ).then(
            fn=update_message_visibility,
            inputs=control_message,
            outputs=control_message,
        )
        stop_button.click(fn=bot_handler.stop_bot, outputs=control_message).then(
            fn=update_message_visibility,
            inputs=control_message,
            outputs=control_message,
        )
        restart_button.click(
            fn=bot_handler.restart_bot, outputs=control_message
        ).then(
            fn=update_message_visibility,
            inputs=control_message,
            outputs=control_message,
        )
        refresh_status_button.click(fn=bot_handler.get_status, outputs=status_outputs)
        reset_stats_button.click(
            fn=bot_handler.reset_stats, outputs=control_message
        ).then(
            fn=update_message_visibility,
            inputs=control_message,
            outputs=control_message,
        ).then(fn=bot_handler.get_status, outputs=status_outputs)

        config_tab.bind(app)
        log_tab.bind(app)
        stats_tab.bind(app)
        history_tab.bind(app)
        backup_tab.bind(app)
        if auth_tab:
            auth_tab.bind(app)

        refresh_outputs = [*status_outputs, log_tab.output, control_message]
        if auth_tab:
            refresh_outputs.extend(auth_tab.refresh_outputs)
        timer.tick(
            fn=auto_refresh_all,
            inputs=log_tab.lines,
            outputs=refresh_outputs,
        )

        app.load(fn=bot_handler.get_status, outputs=status_outputs)
        if export_tab:
            export_tab.bind(app, export_timer, export_table_timer)

    return app
