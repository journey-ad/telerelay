"""
Gradio UI Builder
"""
import gradio as gr
from typing import Optional
from src.bot_manager import BotManager
from src.config import Config
from src.auth_manager import AuthManager
from src.logger import get_logger
from src.i18n import t, set_language, get_language, get_available_languages
from src.constants import (
    UI_REFRESH_INTERVAL,
    DEFAULT_LOG_LINES,
    MIN_LOG_LINES,
    MAX_LOG_LINES
)
from .handlers import BotControlHandler, ConfigHandler, LogHandler, AuthHandler, HistoryHandler, StatsHandler, BackupHandler

logger = get_logger()


def create_ui(config: Config, bot_manager: BotManager, auth_manager: Optional[AuthManager] = None) -> gr.Blocks:
    """Create Gradio interface

    Args:
        config: Configuration object
        bot_manager: Bot manager
        auth_manager: Authentication manager (optional, for User mode)
    """

    # Create handlers
    bot_handler = BotControlHandler(bot_manager, config)
    config_handler = ConfigHandler(config, bot_manager)
    log_handler = LogHandler()

    # Create authentication handler (if auth_manager is provided)
    auth_handler = None
    if auth_manager:
        auth_handler = AuthHandler(auth_manager, bot_manager)

    # Create new handlers
    history_handler = HistoryHandler()
    stats_handler = StatsHandler()
    backup_handler = BackupHandler(config, bot_manager)

    # Use soft theme
    theme = gr.themes.Soft(
        primary_hue="blue",
        secondary_hue="gray",
    )

    with gr.Blocks(title=t("ui.title.main"), theme=theme) as app:

        # Title
        gr.Markdown(f"# {t('ui.title.main')}")
        gr.Markdown(t("ui.title.subtitle"))

        # Event-driven refresh timer (fast polling to check update flag)
        timer = gr.Timer(value=UI_REFRESH_INTERVAL)

        # ===== Control Panel =====
        with gr.Row():
            start_btn = gr.Button(t("ui.button.start"), variant="primary", size="lg")
            stop_btn = gr.Button(t("ui.button.stop"), variant="stop", size="lg")
            restart_btn = gr.Button(t("ui.button.restart"), variant="secondary", size="lg")
            refresh_status_btn = gr.Button(t("ui.button.refresh_status"), size="lg")

        with gr.Row():
            status_text = gr.Textbox(label=t("ui.label.status"), value=t("ui.status.stopped"), interactive=False, scale=2)
            forwarded_count = gr.Textbox(label=t("ui.label.forwarded"), value="0", interactive=False, scale=1)
            filtered_count = gr.Textbox(label=t("ui.label.filtered"), value="0", interactive=False, scale=1)
            total_count = gr.Textbox(label=t("ui.label.total"), value="0", interactive=False, scale=1)
            reset_stats_btn = gr.Button(t("ui.button.reset_stats"), size="sm", scale=0, min_width=80)

        control_message = gr.Textbox(label=t("ui.label.operation_message"), visible=False)

        # ===== Tabs =====
        with gr.Tabs():

            # --- Configuration Tab ---
            with gr.Tab(t("ui.title.tab_config")):
                # Rule selector
                with gr.Group():
                    with gr.Row():
                        rule_selector = gr.Dropdown(
                            choices=config_handler.get_rule_names(),
                            value=config_handler.get_rule_names()[0] if config_handler.get_rule_names() else t("ui.status.default_rule"),
                            label=t("ui.label.current_rule"),
                            scale=3,
                            interactive=True,
                        )
                        add_rule_btn = gr.Button(t("ui.button.add_rule"), scale=0, min_width=50)
                        delete_rule_btn = gr.Button(t("ui.button.delete_rule"), scale=0, min_width=50)
                        rename_rule_btn = gr.Button(t("ui.button.rename_rule"), scale=0, min_width=50)
                        rule_enabled = gr.Checkbox(label=t("ui.label.enable"), value=True, scale=0, min_width=80)

                    # Rename input box (hidden by default)
                    rename_input = gr.Textbox(
                        label=t("ui.label.new_name"),
                        placeholder=t("ui.placeholder.new_name"),
                        visible=False,
                    )

                with gr.Accordion(t("ui.accordion.source_target"), open=True):

                    source_chats = gr.Textbox(
                        label=t("ui.label.source_chats"),
                        placeholder=t("ui.placeholder.source_chats"),
                        lines=4,
                        info=t("ui.info.source_chats")
                    )

                    target_chats = gr.Textbox(
                        label=t("ui.label.target_chats"),
                        placeholder=t("ui.placeholder.target_chats"),
                        lines=4,
                        info=t("ui.info.target_chats")
                    )

                with gr.Accordion(t("ui.accordion.filter_rules"), open=True):

                    regex_patterns = gr.Textbox(
                        label=t("ui.label.regex_patterns"),
                        placeholder=t("ui.placeholder.regex_patterns"),
                        lines=3,
                        info=t("ui.info.regex_patterns")
                    )

                    keywords = gr.Textbox(
                        label=t("ui.label.keywords"),
                        placeholder=t("ui.placeholder.keywords"),
                        lines=3,
                        info=t("ui.info.keywords")
                    )

                    filter_mode = gr.Radio(
                        choices=["whitelist", "blacklist"],
                        value="whitelist",
                        label=t("ui.label.filter_mode"),
                        info=t("ui.info.filter_mode")
                    )

                    media_types = gr.CheckboxGroup(
                        choices=["text", "photo", "video", "document", "audio", "voice", "sticker", "animation"],
                        label=t("ui.label.media_types"),
                        info=t("ui.info.media_types")
                    )

                    max_file_size = gr.Number(
                        label=t("ui.label.max_file_size"),
                        value=0,
                        minimum=0,
                        info=t("ui.info.max_file_size")
                    )

                with gr.Accordion(t("ui.accordion.ignore_list"), open=True):
                    gr.Markdown(t("ui.markdown.ignore_warning"))

                    ignored_user_ids = gr.Textbox(
                        label=t("ui.label.ignored_user_ids"),
                        placeholder=t("ui.placeholder.ignored_user_ids"),
                        lines=3,
                        info=t("ui.info.ignored_user_ids")
                    )

                    ignored_keywords = gr.Textbox(
                        label=t("ui.label.ignored_keywords"),
                        placeholder=t("ui.placeholder.ignored_keywords"),
                        lines=3,
                        info=t("ui.info.ignored_keywords")
                    )

                with gr.Accordion(t("ui.accordion.forward_options"), open=True):

                    preserve_format = gr.Checkbox(
                        label=t("ui.label.preserve_format"),
                        value=True,
                        info=t("ui.info.preserve_format")
                    )

                    add_source_info = gr.Checkbox(
                        label=t("ui.label.add_source_info"),
                        value=True,
                        info=t("ui.info.add_source_info")
                    )

                    force_forward = gr.Checkbox(
                        label=t("ui.label.force_forward"),
                        value=False,
                        info=t("ui.info.force_forward")
                    )

                    hide_sender = gr.Checkbox(
                        label=t("ui.label.hide_sender"),
                        value=False,
                        info=t("ui.info.hide_sender")
                    )

                    delay = gr.Slider(
                        minimum=0,
                        maximum=5,
                        value=0.5,
                        step=0.1,
                        label=t("ui.label.delay"),
                        info=t("ui.info.delay")
                    )

                save_btn = gr.Button(t("ui.button.save_config"), variant="primary", size="lg")
                save_message = gr.Textbox(label=t("ui.label.save_result"), visible=False)

            # --- Log Tab ---
            with gr.Tab(t("ui.title.tab_log")):
                log_output = gr.Textbox(
                    label=t("ui.label.realtime_log"),
                    lines=25,
                    max_lines=25,
                    interactive=False,
                    show_copy_button=True,
                    elem_id="log_output",
                    autoscroll=True
                )

                with gr.Row():
                    refresh_log_btn = gr.Button(t("ui.button.refresh_log"), size="lg")
                    log_lines = gr.Slider(
                        minimum=MIN_LOG_LINES,
                        maximum=MAX_LOG_LINES,
                        value=DEFAULT_LOG_LINES,
                        step=10,
                        label=t("ui.label.log_lines"),
                        scale=2
                    )

            # --- Stats Tab ---
            with gr.Tab(t("ui.title.tab_stats")):
                gr.Markdown(f"### {t('ui.label.rule_stats')}")
                stats_table = gr.Dataframe(
                    headers=[t("ui.label.rule_name"), t("ui.label.forwarded"),
                             t("ui.label.filtered"), t("ui.label.total")],
                    datatype=["str", "number", "number", "number"],
                    interactive=False,
                    row_count=(1, "dynamic"),
                )

                gr.Markdown(f"### {t('ui.label.daily_trend')}")
                with gr.Row():
                    stats_days = gr.Slider(
                        minimum=7, maximum=90, value=30, step=1,
                        label=t("ui.label.days_range"), scale=2
                    )
                    refresh_stats_btn = gr.Button(t("ui.button.refresh_stats"), scale=0, min_width=100)

                stats_plot = gr.Plot(label=t("ui.label.daily_trend"))

                with gr.Row():
                    stats_export_fmt = gr.Dropdown(
                        choices=["csv", "json", "html"], value="csv",
                        label=t("ui.label.export_format"), scale=1
                    )
                    export_stats_btn = gr.Button(t("ui.button.export"), scale=0, min_width=100)
                    stats_export_file = gr.File(label=t("ui.label.export_file"), visible=True, scale=2)

            # --- History Tab ---
            with gr.Tab(t("ui.title.tab_history")):
                with gr.Row():
                    history_rule_filter = gr.Dropdown(
                        choices=history_handler.get_rule_choices(),
                        value="",
                        label=t("ui.label.rule_filter"),
                        scale=1
                    )
                    history_keyword = gr.Textbox(
                        label=t("ui.label.search_keyword"),
                        placeholder=t("ui.placeholder.search_keyword"),
                        scale=2
                    )
                    search_btn = gr.Button(t("ui.button.search"), variant="primary", scale=0, min_width=100)

                history_table = gr.Dataframe(
                    headers=["time", "rule_name", "source_chat_id", "source_chat_name",
                             "sender_name", "username", "content", "media_type"],
                    datatype=["str", "str", "str", "str", "str", "str", "str", "str"],
                    interactive=False,
                    row_count=(1, "dynamic"),
                )

                with gr.Row():
                    prev_page_btn = gr.Button(t("ui.button.prev_page"), scale=0, min_width=80)
                    history_page_info = gr.Textbox(
                        value="1/1 (0)", interactive=False,
                        label=t("ui.label.page_info_label"), scale=1
                    )
                    next_page_btn = gr.Button(t("ui.button.next_page"), scale=0, min_width=80)
                    history_page = gr.State(value=1)
                    history_total_pages = gr.State(value=1)

                with gr.Row():
                    history_export_fmt = gr.Dropdown(
                        choices=["csv", "json", "html"], value="csv",
                        label=t("ui.label.export_format"), scale=1
                    )
                    export_history_btn = gr.Button(t("ui.button.export"), scale=0, min_width=100)
                    history_export_file = gr.File(label=t("ui.label.export_file"), visible=True, scale=2)

            # --- Backup Tab ---
            with gr.Tab(t("ui.title.tab_backup")):
                gr.Markdown(t("ui.markdown.backup_guide"))

                with gr.Group():
                    gr.Markdown(f"#### {t('ui.label.export_config')}")
                    export_config_btn = gr.Button(t("ui.button.export_config"), variant="primary")
                    config_export_file = gr.File(label=t("ui.label.export_file"), visible=True)

                with gr.Group():
                    gr.Markdown(f"#### {t('ui.label.import_config')}")
                    config_upload = gr.File(
                        label=t("ui.label.upload_config"),
                        file_types=[".yaml", ".yml"],
                    )
                    import_config_btn = gr.Button(t("ui.button.import_config"), variant="secondary")
                    import_message = gr.Textbox(label=t("ui.label.operation_message"), visible=False)

            # --- Authentication Tab (only shown in User mode) ---
            if auth_handler:
                with gr.Tab(t("ui.title.tab_auth")):
                    gr.Markdown(t("ui.markdown.auth_guide"))

                    # Status display
                    auth_status = gr.Textbox(
                        label=t("ui.label.auth_status"),
                        value=t("ui.auth.idle"),
                        interactive=False
                    )

                    # Control buttons
                    with gr.Row():
                        start_auth_btn = gr.Button(t("ui.button.start_auth"), variant="primary")
                        cancel_auth_btn = gr.Button(t("ui.button.cancel_auth"), variant="stop")

                    # Phone number input (initially hidden)
                    phone_input = gr.Textbox(
                        label=t("ui.label.phone"),
                        placeholder=t("ui.placeholder.phone"),
                        info=t("ui.info.phone"),
                        visible=False
                    )
                    submit_phone_btn = gr.Button(t("ui.button.send_code"), variant="primary", visible=False)

                    # Verification code input (initially hidden)
                    code_input = gr.Textbox(
                        label=t("ui.label.code"),
                        placeholder=t("ui.placeholder.code"),
                        info=t("ui.info.code"),
                        visible=False
                    )
                    submit_code_btn = gr.Button(t("ui.button.submit_code"), variant="primary", visible=False)

                    # Password input (initially hidden)
                    password_input = gr.Textbox(
                        label=t("ui.label.password"),
                        type="password",
                        placeholder=t("ui.placeholder.password"),
                        info=t("ui.info.password"),
                        visible=False
                    )
                    submit_password_btn = gr.Button(t("ui.button.submit_password"), variant="primary", visible=False)

                    # Error message
                    auth_error = gr.Textbox(label=t("ui.label.error_info"), visible=False)

        # ===== Configuration component mapping (simple dictionary) =====
        config_components = {
            'source_chats': source_chats,
            'target_chats': target_chats,
            'regex_patterns': regex_patterns,
            'keywords': keywords,
            'filter_mode': filter_mode,
            'media_types': media_types,
            'max_file_size': max_file_size,
            'ignored_user_ids': ignored_user_ids,
            'ignored_keywords': ignored_keywords,
            'preserve_format': preserve_format,
            'add_source_info': add_source_info,
            'force_forward': force_forward,
            'hide_sender': hide_sender,
            'delay': delay,
            'enabled': rule_enabled,
        }
        config_outputs = list(config_components.values())

        # ===== Helper functions =====
        def update_message_visibility(msg: str) -> dict:
            """Update visibility based on message content"""
            return gr.update(visible=bool(msg))

        def get_rule_index(rule_name: str) -> int:
            """Get index by rule name"""
            names = config_handler.get_rule_names()
            return names.index(rule_name) if rule_name in names else 0

        def load_rule_values(rule_name: str):
            """Load configuration values for specified rule"""
            index = get_rule_index(rule_name)
            config_dict = config_handler.load_rule(index)
            return [config_dict.get(key, "") for key in config_components.keys()]

        def load_config_values():
            """Load configuration values (compatible with old interface)"""
            config_dict = config_handler.load_config()
            return [config_dict.get(key, "") for key in config_components.keys()]

        def auto_refresh_all(lines):
            """Merge refresh logic: periodically check Bot status updates and authentication status"""
            results = []

            # 1. Bot status and logs (based on event flag)
            if bot_manager and bot_manager.check_and_clear_ui_update():
                status = bot_handler.get_status()
                logs = log_handler.get_recent_logs(lines)

                # Authentication success message
                auth_msg = bot_handler.get_auth_success_message()
                msg_update = gr.update(value=auth_msg, visible=True) if auth_msg else gr.update()

                results.extend([*status, logs, msg_update])
            else:
                results.extend([gr.update()] * 6)

            # 2. Authentication status (always check, as AuthManager has no dirty flag, relies on polling)
            if auth_handler:
                auth_updates = auth_handler.get_auth_state()
                results.extend(auth_updates)

            return tuple(results)

        # ===== Event bindings =====

        # Bot control
        start_btn.click(
            fn=bot_handler.start_bot,
            outputs=control_message
        ).then(
            fn=update_message_visibility,
            inputs=control_message,
            outputs=control_message
        )

        stop_btn.click(
            fn=bot_handler.stop_bot,
            outputs=control_message
        ).then(
            fn=update_message_visibility,
            inputs=control_message,
            outputs=control_message
        )

        restart_btn.click(
            fn=bot_handler.restart_bot,
            outputs=control_message
        ).then(
            fn=update_message_visibility,
            inputs=control_message,
            outputs=control_message
        )

        # Configuration save (using currently selected rule index)
        def save_current_rule(rule_name, *args):
            index = get_rule_index(rule_name)
            return config_handler.save_rule(index, *args)

        save_btn.click(
            fn=save_current_rule,
            inputs=[
                rule_selector,
                source_chats,
                target_chats,
                regex_patterns,
                keywords,
                filter_mode,
                media_types,
                max_file_size,
                ignored_user_ids,
                ignored_keywords,
                preserve_format,
                add_source_info,
                force_forward,
                hide_sender,
                delay,
                rule_enabled,
            ],
            outputs=save_message
        ).then(
            fn=update_message_visibility,
            inputs=save_message,
            outputs=save_message
        )

        # ===== Rule selector events =====
        # Load corresponding configuration when switching rules
        rule_selector.change(
            fn=load_rule_values,
            inputs=rule_selector,
            outputs=config_outputs
        )

        # Add rule
        def handle_add_rule():
            _, names, new_idx = config_handler.add_rule("")
            return gr.update(choices=names, value=names[new_idx])

        add_rule_btn.click(
            fn=handle_add_rule,
            outputs=rule_selector
        ).then(
            fn=load_rule_values,
            inputs=rule_selector,
            outputs=config_outputs
        )

        # Delete rule
        def handle_delete_rule(rule_name):
            index = get_rule_index(rule_name)
            _, names, new_idx = config_handler.delete_rule(index)
            return gr.update(choices=names, value=names[new_idx] if names else t("ui.status.default_rule"))

        delete_rule_btn.click(
            fn=handle_delete_rule,
            inputs=rule_selector,
            outputs=rule_selector
        ).then(
            fn=load_rule_values,
            inputs=rule_selector,
            outputs=config_outputs
        )

        # Rename rule (show/hide input box)
        rename_rule_btn.click(
            fn=lambda: gr.update(visible=True),
            outputs=rename_input
        )

        def handle_rename_rule(rule_name, new_name):
            index = get_rule_index(rule_name)
            _, names = config_handler.rename_rule(index, new_name)
            return gr.update(choices=names, value=new_name if new_name else rule_name), gr.update(visible=False)

        rename_input.submit(
            fn=handle_rename_rule,
            inputs=[rule_selector, rename_input],
            outputs=[rule_selector, rename_input]
        )

        # Enable/disable rule
        def handle_toggle_rule(rule_name, enabled):
            index = get_rule_index(rule_name)
            config_handler.toggle_rule(index, enabled)

        rule_enabled.change(
            fn=handle_toggle_rule,
            inputs=[rule_selector, rule_enabled]
        )

        # Status refresh (manual)
        refresh_status_btn.click(
            fn=bot_handler.get_status,
            outputs=[status_text, forwarded_count, filtered_count, total_count]
        )

        # Reset stats
        reset_stats_btn.click(
            fn=bot_handler.reset_stats,
            outputs=control_message
        ).then(
            fn=update_message_visibility,
            inputs=control_message,
            outputs=control_message
        ).then(
            fn=bot_handler.get_status,
            outputs=[status_text, forwarded_count, filtered_count, total_count]
        )

        # Log refresh (manual)
        refresh_log_btn.click(
            fn=log_handler.get_recent_logs,
            inputs=log_lines,
            outputs=log_output
        )



        # ===== Stats Tab event bindings =====
        def refresh_stats(days):
            table = stats_handler.get_rule_detail_table()
            plot = stats_handler.get_daily_trend_plot(int(days))
            return table, plot

        refresh_stats_btn.click(
            fn=refresh_stats,
            inputs=stats_days,
            outputs=[stats_table, stats_plot]
        )

        export_stats_btn.click(
            fn=stats_handler.export_stats,
            inputs=stats_export_fmt,
            outputs=stats_export_file
        )

        # ===== History Tab event bindings =====
        def do_search(rule, kw, _page):
            data, info, total_pages = history_handler.search(rule, kw, 1)
            return data, info, total_pages, 1

        search_btn.click(
            fn=do_search,
            inputs=[history_rule_filter, history_keyword, history_page],
            outputs=[history_table, history_page_info, history_total_pages, history_page]
        )

        history_keyword.submit(
            fn=do_search,
            inputs=[history_rule_filter, history_keyword, history_page],
            outputs=[history_table, history_page_info, history_total_pages, history_page]
        )

        def go_prev(rule, kw, page, total):
            new_page = max(1, page - 1)
            data, info, tp = history_handler.search(rule, kw, new_page)
            return data, info, tp, new_page

        def go_next(rule, kw, page, total):
            new_page = min(total, page + 1)
            data, info, tp = history_handler.search(rule, kw, new_page)
            return data, info, tp, new_page

        prev_page_btn.click(
            fn=go_prev,
            inputs=[history_rule_filter, history_keyword, history_page, history_total_pages],
            outputs=[history_table, history_page_info, history_total_pages, history_page]
        )

        next_page_btn.click(
            fn=go_next,
            inputs=[history_rule_filter, history_keyword, history_page, history_total_pages],
            outputs=[history_table, history_page_info, history_total_pages, history_page]
        )

        export_history_btn.click(
            fn=history_handler.export_data,
            inputs=[history_rule_filter, history_keyword, history_export_fmt],
            outputs=history_export_file
        )

        # ===== Backup Tab event bindings =====
        export_config_btn.click(
            fn=backup_handler.export_config,
            outputs=config_export_file
        )

        import_config_btn.click(
            fn=backup_handler.import_config,
            inputs=config_upload,
            outputs=import_message
        ).then(
            fn=update_message_visibility,
            inputs=import_message,
            outputs=import_message
        )


        # Authentication event bindings (only in User mode)
        if auth_handler:
            # Start authentication
            start_auth_btn.click(
                fn=auth_handler.start_auth,
                outputs=auth_status
            )

            # Cancel authentication
            cancel_auth_btn.click(
                fn=auth_handler.cancel_auth,
                outputs=auth_status
            )

            # Submit phone number
            submit_phone_btn.click(
                fn=auth_handler.submit_phone,
                inputs=phone_input,
                outputs=auth_status
            ).then(
                fn=lambda: "",  # Clear input box
                outputs=phone_input
            )

            # Submit verification code
            submit_code_btn.click(
                fn=auth_handler.submit_code,
                inputs=code_input,
                outputs=auth_status
            ).then(
                fn=lambda: "",  # Clear input box
                outputs=code_input
            )

            # Submit password
            submit_password_btn.click(
                fn=auth_handler.submit_password,
                inputs=password_input,
                outputs=auth_status
            ).then(
                fn=lambda: "",  # Clear input box
                outputs=password_input
            )



        # ===== Global timed refresh (merged Bot status and Auth status) =====
        refresh_outputs = [status_text, forwarded_count, filtered_count, total_count, log_output, control_message]
        if auth_handler:
            refresh_outputs.extend([
                auth_status,
                phone_input, submit_phone_btn,
                code_input, submit_code_btn,
                password_input, submit_password_btn,
                auth_error
            ])

        timer.tick(
            fn=auto_refresh_all,
            inputs=log_lines,
            outputs=refresh_outputs
        )

        # ===== Initialize on page load =====

        # Automatically load configuration on load
        app.load(
            fn=load_config_values,
            outputs=list(config_components.values())
        )

        # Get status once on load
        app.load(
            fn=bot_handler.get_status,
            outputs=[status_text, forwarded_count, filtered_count, total_count]
        )

        # Automatically refresh logs on load
        app.load(
            fn=log_handler.get_recent_logs,
            inputs=log_lines,
            outputs=log_output
        )

        # Load stats on page load
        app.load(
            fn=refresh_stats,
            inputs=stats_days,
            outputs=[stats_table, stats_plot]
        )

    return app
