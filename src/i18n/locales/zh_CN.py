"""
中文翻译文件 (zh_CN)
包含所有中文文本的翻译
"""

TRANSLATIONS = {
    # ===== 日志相关 =====

    # log.main.* - main.py 的日志
    "log": {
        "main": {
            "startup_banner": "TeleRelay 启动中...",
            "auth_manager_created": "✓ AuthManager 已创建（User 模式）",
            "session_detected": "检测到 session 缓存，自动启动 Bot...",
            "web_address": "Web 界面地址: http://{host}:{port}",
            "auth_enabled": "✓ HTTP Basic Auth 已启用",
            "auth_warning": "⚠ HTTP Basic Auth 未启用，建议在生产环境配置认证",
            "shutdown": "\\n收到终止信号，正在关闭...",
            "error": "程序运行出错: {error}",
        },

        # log.bot.* - bot_manager.py 的日志
        "bot": {
            "already_running": "Bot 已在运行中",
            "thread_created": "Bot 启动线程已创建",
            "start_failed": "启动 Bot 失败: {error}",
            "error": "Bot 运行出错: {error}",
            "config_validation_failed": "配置验证失败: {error}",
            "connect_failed": "无法连接到 Telegram",
            "user_info_failed": "获取用户信息失败: {error}",
            "rule_registered": "✓ 规则 '{rule}' 已注册，监听 {count} 个源",
            "started": "✓ Bot 已启动，共 {count} 个规则",
            "stopped": "Bot 已停止",
            "main_error": "Bot 主逻辑出错: {error}",
            "message_received": "收到消息 - 来自: {chat} ({chat_id}), 发送者: {sender} ({sender_id}), 内容: {preview}",
            "message_filtered": "消息被过滤 [{rules}]{group_tag}",
            "not_running": "Bot 未在运行",
            "stopping": "正在停止 Bot...",
            "stop_success": "✓ Bot 已停止",
            "stop_failed": "停止 Bot 失败: {error}",
            "restarting": "正在重启 Bot...",
            "restart_failed": "无法停止 Bot，重启失败",
        },

        # log.client.* - client.py 的日志
        "client": {
            "proxy_unsupported": "不支持的代理类型: {type}",
            "proxy_using": "使用代理: {type} {host}:{port}",
            "proxy_parse_failed": "解析代理配置失败: {error}",
            "bot_token_required": "Bot 模式需要 BOT_TOKEN",
            "bot_connected": "已使用 Bot Token 连接到 Telegram",
            "session_detected": "检测到已有 session，尝试自动登录...",
            "user_logged_in": "已登录到 Telegram - 用户: {name} (@{username})",
            "phone_invalid": "手机号格式无效",
            "code_invalid": "验证码错误",
            "password_invalid": "两步验证密码错误",
            "auth_timeout": "认证超时: {error}",
            "connect_failed": "连接 Telegram 失败: {error}",
            "disconnected": "已断开 Telegram 连接",
            "client_not_initialized": "客户端未初始化",
            "flood_wait": "触发速率限制，需要等待 {seconds} 秒",
            "message_error": "处理消息时出错: {error}",
            "handler_registered": "已注册消息处理器 - 监听 {count} 个聊天",
            "running": "Telegram 客户端开始运行...",
            "session_deleted": "已删除 session 文件: {file}",
            "session_cleared": "Session 文件已清除",
            "session_clear_failed": "清除 session 文件失败: {error}",
        },

        # log.forward.* - forwarder 相关的日志
        "forward": {
            "flood_wait": "触发速率限制，等待 {seconds} 秒后重试",
            "error": "转发消息失败: {error}",
            "no_target": "未配置目标聊天",
            "download_failed": "强制下载失败，无法转发",
            "restricted_fallback": "转发受限，降级为下载重传",
            "fallback_failed": "降级转发到 {target} 失败: {error}",
            "target_failed": "转发消息到 {target} 失败: {error}",
            "direct_success": "✓ 已直接转发到 {target}",
            "copy_success": "✓ 已引用复制到 {target}",
            "text_sent": "✓ 已发送文本到 {target}",
            "uploading": "⬆️ 开始上传到 {target}...",
            "force_success": "✓ 已强制转发到 {target}",
            "success": "✅ 转发成功{group_info}: \"{preview}\"{group_id_info} → {success}/{total} 目标",
            "all_failed": "❌ 转发失败: \"{preview}\" → 所有目标均失败",
            "source_label": "📢 来源: https://t.me/{username}/{msg_id}",
            "source_private": "📢 来源: https://t.me/c/{channel_id}/{msg_id}",
            "source_unknown": "📢 来源: {chat_title}",

            # downloader
            "downloader": {
                "downloading": "⬇️ 开始下载媒体文件...",
                "complete": "⬇️ 下载完成: {filename} ({size} MB)",
                "group_downloading": "⬇️ 开始下载媒体组 ({count} 项)...",
                "group_progress": "⬇️ 下载 {current}/{total}: {filename}",
                "group_complete": "⬇️ 媒体组下载完成: {count} 个文件",
                "cleanup": "已清理临时文件: {path}",
                "cleanup_failed": "清理临时文件失败: {path}, {error}",
            },

            # media_group
            "media_group": {
                "collected": "📎 媒体组 grouped_id={group_id}: 共 {count} 条消息",
                "fetch_failed": "获取媒体组消息失败: {error}，作为单条消息处理",
                "duplicate": "↩ 媒体组重复触发，跳过 (grouped_id={group_id})",
                "filtered": "媒体组被过滤 (无匹配消息) - grouped_id: {group_id}",
            },
        },

        # log.filter.* - filters.py 的日志
        "filter": {
            "regex_invalid": "无效的正则表达式 '{pattern}': {error}",
            "initialized": "过滤器初始化 - 模式: {mode}, 正则: {regex_count}, 关键词: {keyword_count}, 媒体类型: {media_types}, 文件大小: {min_size}-{max_size}",
            "media_type_filtered": "媒体类型被过滤: {type} 不在允许列表 {allowed}",
            "file_too_small": "文件太小被过滤: {size} < {min_size}",
            "file_too_large": "文件太大被过滤: {size} > {max_size}",
            "regex_matched": "匹配正则: {pattern}",
            "keyword_matched": "匹配关键词: {keyword}",
            "user_ignored": "忽略用户: {user_id}",
            "keyword_ignored": "忽略关键词: {keyword}",
        },

        # log.auth.* - auth_manager.py 的日志
        "auth": {
            "initialized": "AuthManager 已初始化",
            "state_updated": "认证状态更新: {state} {error}",
            "user_info_saved": "用户信息已保存: {info}",
            "submitted": "{name}已提交",
            "queue_full": "{name}队列已满，请勿重复提交",
            "phone_masked": "手机号: {phone}***",
            "waiting": "等待用户输入{name}...",
            "received": "收到{name}",
            "timeout": "等待{name}输入超时（{timeout}秒）",
            "get_failed": "获取{name}失败: {error}",
            "reset": "认证状态已重置",
            # 认证操作名称
            "auth_state": "认证状态",
            "auth_flow": "认证流程",
            "start_auth": "启动认证",
            "cancel_auth": "取消认证",
            "submit_phone": "提交手机号",
            "submit_code": "提交验证码",
            "submit_password": "提交密码",
            "status": "状态",
        },

        # log.config.* - config.py 的日志
        "config": {
            "env_loaded": "已加载环境变量文件: {path}",
            "env_not_found": "环境变量文件不存在: {path}",
            "yaml_loaded": "已加载 YAML 配置文件: {path}",
            "yaml_not_found": "YAML 配置文件不存在: {path}",
            "saved": "已保存配置到: {path}",
        },
    },

    # ===== UI 相关 =====
    "ui": {
        # ui.title.* - 标题和标签
        "title": {
            "main": "📡 TeleRelay",
            "subtitle": "智能 Telegram 消息中继，支持灵活过滤",
            "tab_config": "⚙️ 配置",
            "tab_log": "📋 日志",
            "tab_auth": "🔐 认证",
        },

        # ui.button.* - 按钮
        "button": {
            "start": "▶️ 启动",
            "stop": "⏸️ 停止",
            "restart": "🔄 重启",
            "refresh_status": "🔄 刷新状态",
            "save_config": "💾 保存配置",
            "refresh_log": "🔄 刷新日志",
            "add_rule": "➕",
            "delete_rule": "🗑️",
            "rename_rule": "✏️",
            "start_auth": "🚀 开始认证",
            "cancel_auth": "❌ 取消认证",
            "send_code": "发送验证码",
            "submit_code": "提交验证码",
            "submit_password": "提交密码",
        },

        # ui.label.* - 标签
        "label": {
            "status": "状态",
            "forwarded": "已转发",
            "filtered": "已过滤",
            "total": "总计",
            "operation_message": "操作消息",
            "current_rule": "📋 当前规则",
            "enable": "启用",
            "new_name": "新名称",
            "source_chats": "源群组/频道",
            "target_chats": "目标群组/频道",
            "regex_patterns": "正则表达式",
            "keywords": "关键词",
            "filter_mode": "过滤模式",
            "media_types": "允许的消息类型",
            "max_file_size": "最大文件大小 (MB)",
            "ignored_user_ids": "忽略的用户 ID",
            "ignored_keywords": "忽略的关键词",
            "preserve_format": "保留原始格式",
            "add_source_info": "添加来源信息",
            "force_forward": "开启强制转发",
            "delay": "转发延迟（秒）",
            "save_result": "保存结果",
            "realtime_log": "实时日志",
            "log_lines": "显示行数",
            "auth_status": "认证状态",
            "phone": "手机号",
            "code": "验证码",
            "password": "两步验证密码",
            "error_info": "错误信息",
        },

        # ui.placeholder.* - 占位符
        "placeholder": {
            "source_chats": "-100123456789\\n@example_channel",
            "target_chats": "-100987654321\\n@target_channel\\n-1001234567890",
            "regex_patterns": "\\\\[重要\\\\].*\\n紧急通知.*",
            "keywords": "关键词1\\n关键词2",
            "ignored_user_ids": "123456789\\n987654321",
            "ignored_keywords": "广告\\n推广\\nspam",
            "new_name": "输入新的规则名称",
            "phone": "+8613800138000",
            "code": "12345",
            "password": "请输入密码",
        },

        # ui.info.* - 提示信息
        "info": {
            "source_chats": "输入要监控的群组 ID 或频道用户名，每行一个",
            "target_chats": "消息将转发到这些位置，每行一个",
            "regex_patterns": "每行一个正则表达式",
            "keywords": "每行一个关键词",
            "filter_mode": "whitelist: 仅转发匹配的消息 | blacklist: 转发不匹配的消息",
            "media_types": "不选则允许所有类型",
            "max_file_size": "0 表示不限制",
            "ignored_user_ids": "这些用户发送的所有消息将被忽略，每行一个数字 ID（可通过 @userinfobot 获取）",
            "ignored_keywords": "包含这些关键词的消息将被忽略，每行一个关键词（不区分大小写）",
            "preserve_format": "保留转发标记和原始格式",
            "add_source_info": "在消息前添加来源群组信息",
            "force_forward": "先下载后上传，可绕过频道/群组的禁止转发限制，可能会产生额外流量",
            "delay": "避免触发 Telegram 限制",
            "phone": "请输入国际格式的手机号",
            "code": "请输入 Telegram 发送的验证码",
            "password": "您启用了两步验证，请输入密码",
        },

        # ui.accordion.* - 折叠面板标题
        "accordion": {
            "source_target": "📥 源和目标",
            "filter_rules": "🔍 过滤规则",
            "ignore_list": "🚫 忽略列表",
            "forward_options": "📤 转发选项",
        },

        # ui.markdown.* - Markdown 文本
        "markdown": {
            "ignore_warning": "⚠️ 优先级高于过滤规则，匹配则直接忽略",
            "auth_guide": """### Telegram User 模式认证

**首次使用或会话过期时，请按以下步骤操作：**

1. 点击下方「🚀 开始认证」按钮）
2. 页面将会显示手机号输入框
3. 输入手机号（国际格式，如 +8613800138000）并点击「发送验证码」
4. 输入 Telegram 发送的验证码并点击「提交验证码」
5. 如果启用了两步验证，输入密码并点击「提交密码」
""",
        },

        # ui.status.* - 状态文本
        "status": {
            "stopped": "⚫ 已停止",
            "running": "🟢 运行中",
            "connecting": "🟡 连接中...",
            "error": "❌ 状态异常",
            "default_rule": "默认规则",
        },

        # ui.auth.* - 认证状态
        "auth": {
            "idle": "未开始认证",
            "connecting": "🔄 正在连接...",
            "waiting_phone": "⏳ 请输入手机号",
            "waiting_code": "⏳ 验证码已发送到您的 Telegram，请查收",
            "waiting_password": "⏳ 检测到两步验证，请输入密码",
            "success": "✅ 认证成功！",
            "error": "❌ 认证失败",
            "logged_in": "✅ 已登录: {user_info}",
            "unknown": "未知状态",
        },
    },

    # ===== 消息反馈 =====
    "message": {
        # message.bot.* - Bot 控制消息
        "bot": {
            "already_running": "Bot 已在运行中",
            "auth_in_progress": "认证正在进行中，{state}",
            "running": "Bot 正在运行中",
            "config_invalid": "配置验证失败: {error}",
            "session_detected": "检测到认证缓存，正在自动登录…",
            "auth_started": "认证流程已启动，请在「🔐 认证」标签页输入认证信息",
            "start_success": "Bot 已成功启动",
            "start_failed": "Bot 启动失败",
            "not_running": "Bot 未在运行",
            "stop_success": "Bot 已成功停止",
            "stop_failed": "Bot 停止失败",
            "restart_success": "Bot 已成功重启",
            "restart_failed": "Bot 重启失败",
        },

        # message.auth.* - 认证消息
        "auth": {
            "in_progress": "认证正在进行中，{state}",
            "completed": "认证已完成，Bot 正在运行中",
            "started": "认证流程已启动，请按提示操作",
            "start_failed": "启动认证流程失败",
            "cancelled": "认证已取消，session 已清除",
            "cancel_failed": "取消认证失败: {error}",
            "phone_submitted": "手机号已提交，等待验证码...",
            "phone_invalid": "提交手机号失败，请检查格式",
            "code_submitted": "验证码已提交，正在验证...",
            "code_failed": "提交验证码失败",
            "password_submitted": "密码已提交，正在验证...",
            "password_failed": "提交密码失败",
            "phone_empty": "手机号不能为空",
            "phone_format": "手机号必须以 + 开头（如 +8613800138000）",
            "code_empty": "验证码不能为空",
            "code_format": "验证码应为纯数字",
            "password_empty": "密码不能为空",
            "phone_invalid_error": "手机号格式无效，请检查格式（如 +8613800138000）",
            "code_invalid_error": "验证码错误，请重新开始认证",
            "password_invalid_error": "两步验证密码错误，请重新开始认证",
        },

        # message.config.* - 配置消息
        "config": {
            "source_required": "请至少配置一个源群组/频道",
            "target_required": "请至少配置一个目标群组/频道",
            "rule_saved": "规则 '{rule}' 已保存",
            "rule_saved_restarted": "{msg}，已重启 Bot",
            "rule_saved_restart_failed": "{msg}，但重启失败",
            "rule_saved_next_start": "{msg}，下次启动时生效",
            "save_failed": "保存失败: {error}",
            "rule_added": "已添加规则 '{name}'",
            "add_failed": "添加失败: {error}",
            "rule_deleted": "已删除规则 '{name}'",
            "delete_failed": "删除失败: {error}",
            "delete_last_rule": "至少需要保留一个规则",
            "invalid_index": "规则索引无效",
            "rule_renamed": "已将 '{old_name}' 重命名为 '{new_name}'",
            "rename_failed": "重命名失败: {error}",
            "name_empty": "规则名称不能为空",
            "rule_toggled": "规则 '{rule}' 已{status}",
            "toggle_failed": "操作失败: {error}",
            "enabled": "启用",
            "disabled": "禁用",
            "load_failed": "加载规则失败: {error}",
        },

        # message.log.* - 日志消息
        "log": {
            "no_logs": "暂无日志",
            "read_failed": "读取日志失败: {error}",
        },

        # message.validation.* - 验证消息
        "validation": {
            "api_missing": "缺少 API_ID 或 API_HASH 配置",
            "bot_token_required": "Bot 模式需要配置 BOT_TOKEN",
            "no_rules": "未配置任何启用的转发规则",
            "no_source": "规则 '{rule}' 未配置源群组",
            "no_target": "规则 '{rule}' 未配置目标群组",
            "passed": "配置验证通过",
        },
    },

    # ===== 其他 =====
    "misc": {
        "login_success": "登录成功 - {name}",
        "media_group_info": " (媒体组 {count} 项)",
        "no_match_rules": "无匹配规则",
        "all_media_types": "全部",
        "unlimited": "不限",
        "unknown": "未知",
        "rule_name_template": "规则 {count}",
        "via_webui": " (通过 WebUI)",
        "via_webui_restart": " (通过 WebUI 重启)",
        "config_updated": " (配置已更新)",
        "restart_suffix": " (重启)",
        "session_cleared": "，session 已清除",

        # 媒体类型描述
        "media": {
            "photo": "[图片]",
            "gif": "[GIF]",
            "video": "[视频]",
            "audio": "[音频]",
            "voice": "[语音]",
            "sticker": "[贴纸]",
            "video_note": "[视频消息]",
            "file": "[文件]",
            "contact": "[联系人]",
            "poll": "[投票]",
            "location": "[位置]",
            "dice": "[表情]",
            "media": "[媒体]",
        },
    },
}
