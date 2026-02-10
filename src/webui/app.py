"""
Gradio UI构建
"""
import gradio as gr
from typing import Optional
from src.bot_manager import BotManager
from src.config import Config
from src.auth_manager import AuthManager
from src.logger import get_logger
from src.constants import (
    UI_REFRESH_INTERVAL,
    DEFAULT_LOG_LINES,
    MIN_LOG_LINES,
    MAX_LOG_LINES
)
from .handlers import BotControlHandler, ConfigHandler, LogHandler, AuthHandler

logger = get_logger()


def create_ui(config: Config, bot_manager: BotManager, auth_manager: Optional[AuthManager] = None) -> gr.Blocks:
    """创建Gradio界面

    参数:
        config: 配置对象
        bot_manager: Bot 管理器
        auth_manager: 认证管理器（可选，用于 User 模式）
    """

    # 创建处理器
    bot_handler = BotControlHandler(bot_manager, config)
    config_handler = ConfigHandler(config, bot_manager)
    log_handler = LogHandler()

    # 创建认证处理器（如果提供了 auth_manager）
    auth_handler = None
    if auth_manager:
        auth_handler = AuthHandler(auth_manager, bot_manager)

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
                # 规则选择器
                with gr.Group():
                    with gr.Row():
                        rule_selector = gr.Dropdown(
                            choices=config_handler.get_rule_names(),
                            value=config_handler.get_rule_names()[0] if config_handler.get_rule_names() else "默认规则",
                            label="📋 当前规则",
                            scale=3,
                            interactive=True,
                        )
                        add_rule_btn = gr.Button("➕", scale=0, min_width=50)
                        delete_rule_btn = gr.Button("🗑️", scale=0, min_width=50)
                        rename_rule_btn = gr.Button("✏️", scale=0, min_width=50)
                        rule_enabled = gr.Checkbox(label="启用", value=True, scale=0, min_width=80)
                    
                    # 重命名输入框（默认隐藏）
                    rename_input = gr.Textbox(
                        label="新名称",
                        placeholder="输入新的规则名称",
                        visible=False,
                    )

                with gr.Accordion("📥 源和目标", open=True):

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

                with gr.Accordion("🔍 过滤规则", open=True):

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

                    media_types = gr.CheckboxGroup(
                        choices=["text", "photo", "video", "document", "audio", "voice", "sticker", "animation"],
                        label="允许的消息类型",
                        info="不选则允许所有类型"
                    )

                    max_file_size = gr.Number(
                        label="最大文件大小 (MB)",
                        value=0,
                        minimum=0,
                        info="0 表示不限制"
                    )

                with gr.Accordion("🚫 忽略列表", open=True):
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

                with gr.Accordion("📤 转发选项", open=True):

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

                    force_forward = gr.Checkbox(
                        label="开启强制转发",
                        value=False,
                        info="先下载后上传，可绕过频道/群组的禁止转发限制，可能会产生额外流量"
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

            # --- 认证标签（仅在 User 模式下显示）---
            if auth_handler:
                with gr.Tab("🔐 认证"):
                    gr.Markdown("""
                    ### Telegram User 模式认证

                    **首次使用或会话过期时，请按以下步骤操作：**

                    1. 点击下方「🚀 开始认证」按钮）
                    2. 页面将会显示手机号输入框
                    3. 输入手机号（国际格式，如 +8613800138000）并点击「发送验证码」
                    4. 输入 Telegram 发送的验证码并点击「提交验证码」
                    5. 如果启用了两步验证，输入密码并点击「提交密码」
                    """)

                    # 状态显示
                    auth_status = gr.Textbox(
                        label="认证状态",
                        value="未开始认证",
                        interactive=False
                    )

                    # 控制按钮
                    with gr.Row():
                        start_auth_btn = gr.Button("🚀 开始认证", variant="primary")
                        cancel_auth_btn = gr.Button("❌ 取消认证", variant="stop")

                    # 手机号输入（初始隐藏）
                    phone_input = gr.Textbox(
                        label="手机号",
                        placeholder="+8613800138000",
                        info="请输入国际格式的手机号",
                        visible=False
                    )
                    submit_phone_btn = gr.Button("发送验证码", variant="primary", visible=False)

                    # 验证码输入（初始隐藏）
                    code_input = gr.Textbox(
                        label="验证码",
                        placeholder="12345",
                        info="请输入 Telegram 发送的验证码",
                        visible=False
                    )
                    submit_code_btn = gr.Button("提交验证码", variant="primary", visible=False)

                    # 密码输入（初始隐藏）
                    password_input = gr.Textbox(
                        label="两步验证密码",
                        type="password",
                        placeholder="请输入密码",
                        info="您启用了两步验证，请输入密码",
                        visible=False
                    )
                    submit_password_btn = gr.Button("提交密码", variant="primary", visible=False)

                    # 错误消息
                    auth_error = gr.Textbox(label="错误信息", visible=False)

        # ===== 配置组件映射（简单字典） =====
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
            'delay': delay,
            'enabled': rule_enabled,
        }
        config_outputs = list(config_components.values())

        # ===== 辅助函数 =====
        def update_message_visibility(msg: str) -> dict:
            """根据消息内容更新可见性"""
            return gr.update(visible=bool(msg))

        def get_rule_index(rule_name: str) -> int:
            """根据规则名称获取索引"""
            names = config_handler.get_rule_names()
            return names.index(rule_name) if rule_name in names else 0

        def load_rule_values(rule_name: str):
            """加载指定规则的配置值"""
            index = get_rule_index(rule_name)
            config_dict = config_handler.load_rule(index)
            return [config_dict.get(key, "") for key in config_components.keys()]

        def load_config_values():
            """加载配置值（兼容旧接口）"""
            config_dict = config_handler.load_config()
            return [config_dict.get(key, "") for key in config_components.keys()]

        def auto_refresh_all(lines):
            """合并刷新逻辑：定期检查 Bot 状态更新和认证状态"""
            results = []

            # 1. Bot 状态和日志 (基于事件标志)
            if bot_manager and bot_manager.check_and_clear_ui_update():
                status = bot_handler.get_status()
                logs = log_handler.get_recent_logs(lines)
                
                # 认证成功消息
                auth_msg = bot_handler.get_auth_success_message()
                msg_update = gr.update(value=auth_msg, visible=True) if auth_msg else gr.update()

                results.extend([*status, logs, msg_update])
            else:
                results.extend([gr.update()] * 6)

            # 2. 认证状态 (总是检查，因为 AuthManager 没有 dirty flag，依靠轮询)
            if auth_handler:
                auth_updates = auth_handler.get_auth_state()
                results.extend(auth_updates)

            return tuple(results)

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

        # 配置保存（使用当前选中的规则索引）
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
                delay,
                rule_enabled,
            ],
            outputs=save_message
        ).then(
            fn=update_message_visibility,
            inputs=save_message,
            outputs=save_message
        )

        # ===== 规则选择器事件 =====
        # 切换规则时加载对应配置
        rule_selector.change(
            fn=load_rule_values,
            inputs=rule_selector,
            outputs=config_outputs
        )

        # 添加规则
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

        # 删除规则
        def handle_delete_rule(rule_name):
            index = get_rule_index(rule_name)
            _, names, new_idx = config_handler.delete_rule(index)
            return gr.update(choices=names, value=names[new_idx] if names else "默认规则")

        delete_rule_btn.click(
            fn=handle_delete_rule,
            inputs=rule_selector,
            outputs=rule_selector
        ).then(
            fn=load_rule_values,
            inputs=rule_selector,
            outputs=config_outputs
        )

        # 重命名规则（显示/隐藏输入框）
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

        # 启用/禁用规则
        def handle_toggle_rule(rule_name, enabled):
            index = get_rule_index(rule_name)
            config_handler.toggle_rule(index, enabled)

        rule_enabled.change(
            fn=handle_toggle_rule,
            inputs=[rule_selector, rule_enabled]
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



        # 认证事件绑定（仅在 User 模式下）
        if auth_handler:
            # 开始认证
            start_auth_btn.click(
                fn=auth_handler.start_auth,
                outputs=auth_status
            )

            # 取消认证
            cancel_auth_btn.click(
                fn=auth_handler.cancel_auth,
                outputs=auth_status
            )

            # 提交手机号
            submit_phone_btn.click(
                fn=auth_handler.submit_phone,
                inputs=phone_input,
                outputs=auth_status
            ).then(
                fn=lambda: "",  # 清空输入框
                outputs=phone_input
            )

            # 提交验证码
            submit_code_btn.click(
                fn=auth_handler.submit_code,
                inputs=code_input,
                outputs=auth_status
            ).then(
                fn=lambda: "",  # 清空输入框
                outputs=code_input
            )

            # 提交密码
            submit_password_btn.click(
                fn=auth_handler.submit_password,
                inputs=password_input,
                outputs=auth_status
            ).then(
                fn=lambda: "",  # 清空输入框
                outputs=password_input
            )



        # ===== 全局定时刷新 (合并了 Bot 状态和 Auth 状态) =====
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
