"""
Gradio UI构建
"""
import gradio as gr
from src.bot_manager import BotManager
from src.config import Config
from src.constants import (
    UI_REFRESH_INTERVAL,
    DEFAULT_LOG_LINES,
    MIN_LOG_LINES,
    MAX_LOG_LINES
)
from .handlers import BotControlHandler, ConfigHandler, LogHandler


def create_ui(config: Config, bot_manager: BotManager) -> gr.Blocks:
    """创建Gradio界面"""

    # 创建处理器
    bot_handler = BotControlHandler(bot_manager, config)
    config_handler = ConfigHandler(config, bot_manager)
    log_handler = LogHandler()

    # 使用柔和主题
    theme = gr.themes.Soft(
        primary_hue="blue",
        secondary_hue="gray",
    )

    with gr.Blocks(title="Telegram 消息转发工具", theme=theme) as app:

        # 标题
        gr.Markdown("# 📡 Telegram 消息转发工具")
        gr.Markdown("自动监控 Telegram 群组并转发消息到多个目标")

        # 事件驱动刷新定时器（快速轮询检查更新标志）
        timer = gr.Timer(value=UI_REFRESH_INTERVAL)

        # ===== 控制面板 =====
        with gr.Row():
            start_btn = gr.Button("▶️ 启动", variant="primary", size="lg")
            stop_btn = gr.Button("⏸️ 停止", variant="stop", size="lg")
            restart_btn = gr.Button("🔄 重启", variant="secondary", size="lg")
            refresh_status_btn = gr.Button("🔄 刷新状态", size="lg")

        with gr.Row():
            status_text = gr.Textbox(label="状态", value="⚫ 已停止", interactive=False, scale=2)
            forwarded_count = gr.Textbox(label="已转发", value="0", interactive=False, scale=1)
            filtered_count = gr.Textbox(label="已过滤", value="0", interactive=False, scale=1)
            total_count = gr.Textbox(label="总计", value="0", interactive=False, scale=1)

        control_message = gr.Textbox(label="操作消息", visible=False)

        # ===== 标签页 =====
        with gr.Tabs():

            # --- 配置标签 ---
            with gr.Tab("⚙️ 配置"):
                with gr.Group():
                    gr.Markdown("### 📥 源和目标")

                    source_chats = gr.Textbox(
                        label="源群组/频道",
                        placeholder="-100123456789\n@example_channel",
                        lines=4,
                        info="输入要监控的群组 ID 或频道用户名，每行一个"
                    )

                    target_chats = gr.Textbox(
                        label="目标群组/频道",
                        placeholder="-100987654321\n@target_channel\n-1001234567890",
                        lines=4,
                        info="消息将转发到这些位置，每行一个"
                    )

                with gr.Group():
                    gr.Markdown("### 🔍 过滤规则")

                    regex_patterns = gr.Textbox(
                        label="正则表达式",
                        placeholder="\\[重要\\].*\n紧急通知.*",
                        lines=3,
                        info="每行一个正则表达式"
                    )

                    keywords = gr.Textbox(
                        label="关键词",
                        placeholder="关键词1\n关键词2",
                        lines=3,
                        info="每行一个关键词"
                    )

                    filter_mode = gr.Radio(
                        choices=["whitelist", "blacklist"],
                        value="whitelist",
                        label="过滤模式",
                        info="whitelist: 仅转发匹配的消息 | blacklist: 转发不匹配的消息"
                    )

                with gr.Group():
                    gr.Markdown("### 🚫 忽略列表")
                    gr.Markdown("⚠️ 优先级高于过滤规则，匹配则直接忽略")

                    ignored_user_ids = gr.Textbox(
                        label="忽略的用户 ID",
                        placeholder="123456789\n987654321",
                        lines=3,
                        info="这些用户发送的所有消息将被忽略，每行一个数字 ID（可通过 @userinfobot 获取）"
                    )

                    ignored_keywords = gr.Textbox(
                        label="忽略的关键词",
                        placeholder="广告\n推广\nspam",
                        lines=3,
                        info="包含这些关键词的消息将被忽略，每行一个关键词（不区分大小写）"
                    )

                with gr.Group():
                    gr.Markdown("### 📤 转发选项")

                    preserve_format = gr.Checkbox(
                        label="保留原始格式",
                        value=True,
                        info="保留转发标记和原始格式"
                    )

                    add_source_info = gr.Checkbox(
                        label="添加来源信息",
                        value=True,
                        info="在消息前添加来源群组信息"
                    )

                    delay = gr.Slider(
                        minimum=0,
                        maximum=5,
                        value=0.5,
                        step=0.1,
                        label="转发延迟（秒）",
                        info="避免触发 Telegram 限制"
                    )

                save_btn = gr.Button("💾 保存配置", variant="primary", size="lg")
                save_message = gr.Textbox(label="保存结果", visible=False)

            # --- 日志标签 ---
            with gr.Tab("📋 日志"):
                log_output = gr.Textbox(
                    label="实时日志",
                    lines=25,
                    max_lines=25,
                    interactive=False,
                    show_copy_button=True,
                    elem_id="log_output",
                    autoscroll=True
                )

                with gr.Row():
                    refresh_log_btn = gr.Button("🔄 刷新日志", size="lg")
                    log_lines = gr.Slider(
                        minimum=MIN_LOG_LINES,
                        maximum=MAX_LOG_LINES,
                        value=DEFAULT_LOG_LINES,
                        step=10,
                        label="显示行数",
                        scale=2
                    )

        # ===== 配置组件映射（简单字典） =====
        config_components = {
            'source_chats': source_chats,
            'target_chats': target_chats,
            'regex_patterns': regex_patterns,
            'keywords': keywords,
            'filter_mode': filter_mode,
            'ignored_user_ids': ignored_user_ids,
            'ignored_keywords': ignored_keywords,
            'preserve_format': preserve_format,
            'add_source_info': add_source_info,
            'delay': delay
        }

        # ===== 辅助函数 =====
        def update_message_visibility(msg: str) -> dict:
            """根据消息内容更新可见性"""
            return gr.update(visible=bool(msg))

        def load_config_values():
            """加载配置值"""
            config_dict = config_handler.load_config()
            return [config_dict.get(key, "") for key in config_components.keys()]

        def auto_refresh_all(lines):
            """检查是否有更新事件，有则刷新状态和日志"""
            # 检查是否需要更新
            if bot_manager and bot_manager.check_and_clear_ui_update():
                status = bot_handler.get_status()
                logs = log_handler.get_recent_logs(lines)
                return status + (logs,)
            # 无更新则返回 gr.update() 保持不变
            return [gr.update()] * 5

        # ===== 事件绑定 =====

        # Bot 控制
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

        # 配置保存
        save_btn.click(
            fn=config_handler.save_config,
            inputs=[
                source_chats,
                target_chats,
                regex_patterns,
                keywords,
                filter_mode,
                ignored_user_ids,
                ignored_keywords,
                preserve_format,
                add_source_info,
                delay
            ],
            outputs=save_message
        ).then(
            fn=update_message_visibility,
            inputs=save_message,
            outputs=save_message
        )

        # 状态刷新（手动）
        refresh_status_btn.click(
            fn=bot_handler.get_status,
            outputs=[status_text, forwarded_count, filtered_count, total_count]
        )

        # 日志刷新（手动）
        refresh_log_btn.click(
            fn=log_handler.get_recent_logs,
            inputs=log_lines,
            outputs=log_output
        )

        # 事件驱动自动刷新 - 只在转发时更新
        timer.tick(
            fn=auto_refresh_all,
            inputs=log_lines,
            outputs=[status_text, forwarded_count, filtered_count, total_count, log_output]
        )

        # ===== 页面加载时初始化 =====

        # 加载时自动加载配置
        app.load(
            fn=load_config_values,
            outputs=list(config_components.values())
        )

        # 加载时获取一次状态
        app.load(
            fn=bot_handler.get_status,
            outputs=[status_text, forwarded_count, filtered_count, total_count]
        )

        # 加载时自动刷新日志
        app.load(
            fn=log_handler.get_recent_logs,
            inputs=log_lines,
            outputs=log_output
        )

    return app
