"""
中文翻译文件 (zh_CN)
包含所有中文文本的翻译
"""

TRANSLATIONS = {
    # ===== 日志相关 =====

    # log.main.* - main.py 的日志
    "log": {
        "main": {
            "startup": "TeleRelay 启动中...",
            "auth_manager_created": "✓ AuthManager 已创建（User 模式）",
            "session_detected": "检测到 session 缓存，自动启动 Bot...",
            "web_address": "Web 界面地址: http://{host}:{port}",
            "auth_enabled": "✓ HTTP Basic Auth 已启用",
            "auth_warning": "⚠ HTTP Basic Auth 未启用，建议在生产环境配置认证",
            "shutdown": "\\n收到终止信号，正在关闭...",
            "error": "程序运行出错: {error}",
            "admin_bot_started": "✓ 管理 Bot 已启动",
            "api_ready": "TeleRelay API 已就绪 {host}:{port}",
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
            "message_received": "收到消息 - 来源={chat} ({chat_id}), 发送者={sender} ({sender_id}), 内容={preview}",
            "not_running": "Bot 未在运行",
            "stopping": "正在停止 Bot...",
            "stop_success": "✓ Bot 已停止",
            "stop_failed": "停止 Bot 失败: {error}",
            "restarting": "正在重启 Bot...",
            "restart_failed": "无法停止 Bot，重启失败",
        },

        "forward_queue": {
            "enqueued": "加入转发队列 - 规则={rule}, 来源={source}, 待处理={queue_depth}",
            "duplicate": "↩ 忽略重复转发任务 - 规则={rule}, 来源={source}",
            "media_group_enqueued": "媒体组加入转发队列 - 规则={rule}, 来源={source}, 待处理={queue_depth}",
            "media_group_merged": "合并媒体组成员 - 规则={rule}, 来源={source}, 待处理={queue_depth}",
            "restored": "持久转发队列已恢复：重新排队 {recovered} 项，清理完成记录 {purged} 项",
            "paused": "触发 FloodWait，整个转发队列暂停 {seconds:.1f} 秒 - 规则: {rule}, 来源: {chat_id}/{message_id}, 目标: {target}",
            "retry": "转发任务处理失败，{seconds:.1f} 秒后重试 - 规则: {rule}, 来源: {chat_id}/{message_id}, 目标: {target}, 错误: {error}",
            "failed": "转发任务在 {attempts} 次尝试后失败 - 规则: {rule}, 来源: {chat_id}/{message_id}, 目标: {target}, 错误: {error}",
            "loop_error": "持久转发队列循环异常，将自动恢复：{error}",
            "recovery_failed": "持久转发队列恢复 processing 状态失败",
        },

        "button_action": {
            "user_mode_required": "消息附加按钮处理仅支持 Telegram User 模式，已跳过全部规则",
            "registered": "✓ 注册按钮规则 - 规则={rules}, 会话={chats}",
            "clicked": "✓ 按钮处理成功 - 规则={rule}, 按钮=[{buttons}], 数量={count}, 消息={chat_id}/{message_id}, 内容={content}",
            "failed": "按钮处理失败 - 消息: {chat_id}/{message_id}, 错误: {error}",
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
            "photo_refresh_failed": "刷新 Telegram 头像失败: {error}",
        },

        # log.forward.* - forwarder 相关的日志
        "forward": {
            "flood_wait": "触发速率限制，等待 {seconds} 秒后重试",
            "error": "转发消息失败: {error}",
            "no_target": "未配置目标聊天",
            "download_failed": "强制下载失败，无法转发",
            "restricted_fallback": "转发受限 - 改用下载重传",
            "fallback_failed": "降级转发到 {target} 失败: {error}",
            "target_failed": "转发消息到 {target} 失败: {error}",
            "direct_success": "✓ 直接转发成功 - 目标={target}",
            "copy_success": "✓ 引用复制成功 - 目标={target}",
            "text_sent": "✓ 文本发送成功 - 目标={target}",
            "uploading": "⬆️ 上传媒体 - 目标={target}",
            "force_success": "✓ 下载重传成功 - 目标={target}",
            "target_resolve_failed": "目标解析失败，使用原值 - 目标={target}, 错误={error}",
            "history_failed": "转发历史写入失败 - 错误={error}",
            "success": "✅ 转发成功 - 规则={rule}, 来源={source}, {group_info}目标=[{targets}], 结果={success}/{total}, 内容={preview}",
            "all_failed": "❌ 转发失败: \"{preview}\" → 所有目标均失败",
            "source_label": "📢 来源: https://t.me/{username}/{msg_id}",
            "source_private": "📢 来源: https://t.me/c/{channel_id}/{msg_id}",
            "source_unknown": "📢 来源: {chat_title}",

            # downloader
            "downloader": {
                "downloading": "⬇️ 下载媒体",
                "complete": "⬇️ 媒体下载完成 - 文件={filename}, 大小={size}MB",
                "group_downloading": "⬇️ 下载媒体组 - 数量={count}",
                "group_progress": "⬇️ 下载媒体组 - 进度={current}/{total}, 文件={filename}",
                "group_complete": "⬇️ 媒体组下载完成 - 文件={count}",
                "cleanup": "清理临时文件 - 路径={path}",
                "cleanup_failed": "清理临时文件失败: {path}, {error}",
                "purge_failed": "清理临时目录失败: {error}",
            },

            # media_group
            "media_group": {
                "collected": "📎 收集媒体组 - 数量={count}",
                "fetch_failed": "获取媒体组消息失败: {error}，作为单条消息处理",
                "duplicate": "↩ 忽略重复媒体组",
                "filtered": "过滤媒体组 - 原因=无匹配消息",
            },

            # dedup
            "deduplicated": "↩ 忽略重复内容 - 内容={preview}",
        },

        # log.filter.* - filters.py 的日志
        "filter": {
            "regex_invalid": "无效的正则表达式 '{pattern}': {error}",
            "initialized": "过滤器初始化 - 模式={mode}, 正则={regex_count}, 关键词={keyword_count}, 媒体={media_types}, 文件大小={min_size}-{max_size}",
            "media_type_filtered": "过滤媒体类型 - 类型={type}, 允许={allowed}",
            "file_too_small": "过滤文件 - 原因=过小, 大小={size}, 下限={min_size}",
            "file_too_large": "过滤文件 - 原因=过大, 大小={size}, 上限={max_size}",
            "regex_matched": "匹配正则 - 表达式={pattern}",
            "keyword_matched": "匹配关键词 - 关键词={keyword}",
            "user_ignored": "忽略用户 - 用户={user_id}",
            "keyword_ignored": "忽略关键词 - 关键词={keyword}",
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

        # log.admin_bot.* - admin bot logs
        "admin_bot": {
            "started": "✓ 管理 Bot 已连接到 Telegram",
            "error": "管理 Bot 运行出错: {error}",
            "proxy_failed": "管理 Bot 代理解析失败: {error}",
            "retry": "管理 Bot 连接重试 ({attempt}): {error}",
            "webapp_failed": "发送 WebApp 按钮失败: {error}",
            "menu_button_set": "✓ 已设置 Bot 菜单按钮为小程序入口",
            "menu_button_failed": "设置 Bot 菜单按钮失败: {error}",
        },

        # log.account.* - telegram_accounts.py 的日志
        "account": {
            "avatar_cache_failed": "缓存 Telegram 账号头像失败: {error}",
        },

        # log.stats.* - statistics logs
        "stats": {
            "reset": "✓ 转发统计已重置",
            "reset_failed": "重置统计失败: {error}",
        },

        # log.backup.* - backup logs
        "backup": {
            "exported": "✓ 配置已导出",
            "export_failed": "导出配置失败: {error}",
            "backup_created": "已备份当前配置: {path}",
            "import_failed": "导入配置失败: {error}",
        },

        # log.export.* - data export logs
        "export": {
            "chats_loaded": "已加载导出聊天列表: count={count}",
            "cancel_requested": "已请求取消导出任务: kind={kind}, job_id={job_id}, task_id={task_id}",
            "group_queued": "群列表导出已入队: job_id={job_id}, formats={formats}, directory={directory}",
            "group_started": "群列表导出开始: job_id={job_id}, run_id={run_id}",
            "group_progress": "群列表导出进度: job_id={job_id}, processed={processed}/{total}",
            "group_completed": "群列表导出完成: job_id={job_id}, run_id={run_id}, records={count}, files={files}",
            "group_cancelled": "群列表导出已取消: job_id={job_id}, run_id={run_id}",
            "group_failed": "群列表导出失败: job_id={job_id}, run_id={run_id}, error={error}",
            "message_queued": "消息导出已入队: job_id={job_id}, task_id={task_id}, chat={chat_title} ({chat_id}), range={start} -> {end}, formats={formats}, directory={directory}",
            "message_started": "消息导出开始: kind={kind}, job_id={job_id}, run_id={run_id}, task_id={task_id}, chat={chat_title} ({chat_id}), range={start} -> {end}, min_message_id={min_message_id}",
            "message_progress": "消息导出进度: kind={kind}, job_id={job_id}, task_id={task_id}, chat_id={chat_id}, records={count}",
            "message_completed": "消息导出完成: kind={kind}, job_id={job_id}, run_id={run_id}, task_id={task_id}, chat={chat_title} ({chat_id}), records={count}, files={files}",
            "message_cancelled": "消息导出已取消: kind={kind}, job_id={job_id}, run_id={run_id}, task_id={task_id}, chat={chat_title} ({chat_id}), records={count}",
            "message_failed": "消息导出失败: kind={kind}, job_id={job_id}, run_id={run_id}, task_id={task_id}, chat={chat_title} ({chat_id}), records={count}, error={error}",
            "task_saved": "定时导出任务已保存: task_id={task_id}, name={name}, chat={chat_title} ({chat_id}), schedule={schedule}, enabled={enabled}, next_run={next_run}",
            "task_state_changed": "定时导出任务状态已更新: task_id={task_id}, name={name}, enabled={enabled}, next_run={next_run}",
            "task_deleted": "定时导出任务已删除: task_id={task_id}, name={name}",
            "scheduler_started": "导出调度器已启动: tasks={count}",
            "scheduler_stopped": "导出调度器已停止",
            "task_scheduled": "定时导出任务已注册: task_id={task_id}, name={name}, next_run={next_run}",
            "task_unscheduled": "定时导出任务已暂停调度: task_id={task_id}, name={name}",
            "task_triggered": "定时导出任务已触发: task_id={task_id}",
            "task_job_started": "定时导出任务已提交: task_id={task_id}, job_id={job_id}",
            "task_overlap": "定时导出任务仍在运行，跳过本次触发: task_id={task_id}",
            "task_start_failed": "定时导出任务启动失败: task_id={task_id}, error={error}",
            "run_record_failed": "无法记录定时导出失败结果: task_id={task_id}",
        },
    },

    # ===== UI 相关 =====
    "ui": {
        # ui.title.* - 标题和标签
        "title": {
            "main": "📡 TeleRelay",
            "subtitle": "Telegram 消息智能转发工具",
            "tab_config": "⚙️ 配置",
            "tab_log": "📋 日志",
            "tab_auth": "🔐 认证",
            "tab_stats": "📊 统计",
            "tab_history": "📜 历史记录",
            "tab_export": "📤 导出数据",
            "tab_backup": "💾 备份",
            "config_forwarding_rules": "转发规则",
            "config_button_actions": "消息附加按钮处理",
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
            "reset_stats": "🔄 重置统计",
            "search": "🔍 搜索",
            "export": "📥 导出",
            "prev_page": "◀ 上一页",
            "next_page": "下一页 ▶",
            "refresh_stats": "🔄 刷新",
            "export_config": "📥 导出配置",
            "import_config": "📤 导入配置",
            "refresh_chats": "🔄 刷新群列表",
            "export_groups": "📥 导出群列表",
            "export_messages": "📥 导出群消息",
            "cancel_export": "⏹ 取消导出",
            "new_task": "➕ 新建任务",
            "save_task": "💾 保存任务",
            "run_now": "▶ 立即运行",
            "toggle_task": "⏯ 暂停/恢复",
            "delete_task": "🗑 删除任务",
            "refresh_tasks": "🔄 刷新任务",
            "save_button_action": "💾 保存按钮处理规则",
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
            "hide_sender": "隐藏发送者",
            "delay": "转发延迟（秒）",
            "save_result": "保存结果",
            "realtime_log": "实时日志",
            "log_lines": "显示行数",
            "auth_status": "认证状态",
            "phone": "手机号",
            "code": "验证码",
            "password": "两步验证密码",
            "error_info": "错误信息",
            "current_button_action_rule": "📋 当前按钮处理规则",
            "button_action_source_chats": "监听 Bot / 会话",
            "button_action_texts": "按钮文字匹配项",
            "button_action_match_mode": "文字匹配方式",
            "button_action_delay": "点击延迟（秒）",
            "button_action_click_all_matches": "点击所有匹配按钮",
            # Stats tab
            "rule_stats": "📋 各规则统计",
            "daily_trend": "📈 每日转发趋势",
            "days_range": "天数范围",
            "export_format": "导出格式",
            "export_file": "导出文件",
            "no_stats_data": "暂无统计数据",
            "rule_name": "规则名称",
            "date": "日期",
            "count": "数量",
            # History tab
            "rule_filter": "规则筛选",
            "search_keyword": "搜索关键词",
            "time": "时间",
            "source": "来源",
            "sender": "发送者",
            "content": "内容",
            "media_type": "媒体类型",
            "page_info": "第 {page}/{total} 页 (共 {count} 条)",
            "page_info_label": "分页",
            # Backup tab
            "export_config": "导出当前配置",
            "import_config": "导入配置文件",
            "upload_config": "上传配置文件 (.yaml)",
            # Export tab
            "export_availability": "导出状态",
            "export_formats": "导出格式",
            "export_subdirectory": "输出子目录",
            "export_status": "执行状态",
            "export_files": "导出文件",
            "export_chat": "群组/频道",
            "start_time": "起始时间",
            "end_time": "结束时间",
            "all_history": "全部历史",
            "task_selector": "定时任务",
            "task_name": "任务名称",
            "schedule_type": "执行频率",
            "schedule_minute": "分钟",
            "schedule_hour": "小时",
            "schedule_weekday": "星期",
            "timezone": "时区",
            "task_enabled": "启用任务",
            "task_table": "任务列表",
            "run_history": "运行记录",
            "task_operation": "任务操作",
        },

        # ui.placeholder.* - 占位符
        "placeholder": {
            "source_chats": "-100123456789\n@example_channel",
            "target_chats": "-100987654321\n@target_channel\n-1001234567890",
            "regex_patterns": "\\[重要\\].*\n紧急通知.*",
            "keywords": "关键词1\n关键词2",
            "ignored_user_ids": "123456789\n987654321",
            "ignored_keywords": "广告\n推广\nspam",
            "new_name": "输入新的规则名称",
            "phone": "+8613800138000",
            "code": "12345",
            "password": "请输入密码",
            "search_keyword": "输入关键词搜索消息内容、来源或发送者",
            "task_name": "例如：每日导出项目群",
            "export_subdirectory": "例如：groups 或 scheduled/project",
            "button_action_source_chats": "@example_bot\n-100123456789",
            "button_action_texts": "确认\n立即签到\n^领取.*奖励$",
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
            "hide_sender": "使用自定义的引用格式转发，并隐藏真实的发送者",
            "force_forward": "先下载后上传，可绕过频道/群组的禁止转发限制，可能会产生额外流量",
            "delay": "避免触发 Telegram 限制",
            "phone": "请输入国际格式的手机号",
            "code": "请输入 Telegram 发送的验证码",
            "password": "您启用了两步验证，请输入密码",
            "export_subdirectory": "只能填写 data/exports 下的相对子目录",
            "all_history": "忽略起始时间，从 Telegram 可访问的最早记录开始",
            "schedule_minute": "每小时任务使用此分钟；每天/每周任务作为执行分钟",
            "schedule_hour": "每天/每周任务的执行小时",
            "schedule_weekday": "仅每周任务使用，0 表示星期一，6 表示星期日",
            "button_action_source_chats": "仅监听这些 Bot、群组或频道，每行一个 ID 或用户名",
            "button_action_texts": "每行一个匹配项；正则模式下每行是一条正则表达式",
            "button_action_match_mode": "exact: 完全一致 | contains: 包含文字 | regex: 正则表达式",
            "button_action_delay": "收到消息后等待再点击，范围 0–30 秒",
        },

        # ui.accordion.* - 折叠面板标题
        "accordion": {
            "source_target": "📥 源和目标",
            "filter_rules": "🔍 过滤规则",
            "ignore_list": "🚫 忽略列表",
            "forward_options": "📤 转发选项",
            "export_groups": "群列表",
            "export_messages": "群消息记录",
            "export_tasks": "定时导出任务",
            "export_runs": "最近运行记录",
        },

        # ui.markdown.* - Markdown 文本
        "markdown": {
            "ignore_warning": "⚠️ 优先级高于过滤规则，匹配则直接忽略",
            "button_action_guide": "仅在 **Telegram User 模式**下生效。收到指定会话的消息后，默认点击第一个符合规则的回调按钮；可按规则启用点击所有匹配按钮。每条消息最多处理一次。URL、支付、手机号、位置和 Mini App 按钮不会被点击。",
            "auth_guide": """### Telegram User 模式认证

**首次使用或会话过期时，请按以下步骤操作：**

1. 点击下方「🚀 开始认证」按钮）
2. 页面将会显示手机号输入框
3. 输入手机号（国际格式，如 +8613800138000）并点击「发送验证码」
4. 输入 Telegram 发送的验证码并点击「提交验证码」
5. 如果启用了两步验证，输入密码并点击「提交密码」
""",
            "backup_guide": """### 配置备份与恢复

- **导出**: 点击「📥 导出配置」下载当前 `config.yaml` 文件
- **导入**: 上传 `.yaml` 配置文件并点击「📤 导入配置」覆盖当前配置

⚠️ 导入会自动备份当前配置为 `config.yaml.bak`
""",
        },

        # ui.status.* - 状态文本
        "status": {
            "stopped": "⚫ 已停止",
            "running": "🟢 运行中",
            "connecting": "🟡 连接中...",
            "error": "❌ 状态异常",
            "default_rule": "默认规则",
            "default_button_action_rule": "默认按钮处理规则",
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
            "button_action_user_mode": "消息附加按钮处理仅支持 Telegram User 模式",
            "button_action_source_required": "启用规则时请至少配置一个监听 Bot 或会话",
            "button_action_text_required": "启用规则时请至少配置一个按钮文字匹配项",
            "button_action_regex_invalid": "无效的按钮文字正则表达式“{pattern}”: {error}",
            "button_action_saved": "按钮处理规则“{rule}”已保存",
            "button_action_saved_restarted": "{msg}，已重启 Bot",
            "button_action_saved_restart_failed": "{msg}，但重启失败",
            "button_action_saved_next_start": "{msg}，下次启动时生效",
            "button_action_save_failed": "保存按钮处理规则失败: {error}",
            "button_action_added": "已添加按钮处理规则“{name}”",
            "button_action_add_failed": "添加按钮处理规则失败: {error}",
            "button_action_deleted": "已删除按钮处理规则“{name}”",
            "button_action_delete_failed": "删除按钮处理规则失败: {error}",
            "button_action_delete_last": "至少需要保留一条按钮处理规则",
            "button_action_renamed": "已将按钮处理规则“{old_name}”重命名为“{new_name}”",
            "button_action_rename_failed": "重命名按钮处理规则失败: {error}",
        },

        # message.stats.* - 统计消息
        "stats": {
            "reset_success": "统计数据已重置",
            "reset_failed": "统计数据重置失败",
        },

        # message.backup.* - 备份消息
        "backup": {
            "no_file": "请先上传配置文件",
            "invalid_yaml": "无效的 YAML 文件",
            "no_rules_found": "配置文件中未找到转发规则",
            "import_success": "配置导入成功，下次启动时生效",
            "import_success_restarted": "配置导入成功，Bot 已重启",
            "yaml_error": "YAML 解析错误: {error}",
            "import_failed": "导入失败: {error}",
        },

        "export": {
            "user_mode_required": "完整导出仅支持 Telegram User 模式",
            "telegram_not_connected": "Telegram 尚未连接，请先启动并完成 User 模式认证",
            "ready": "Telegram 已连接，可以导出",
            "format_required": "请至少选择一种导出格式",
            "invalid_timezone": "无效时区: {timezone}",
            "invalid_datetime": "日期时间格式无效",
            "datetime_required": "请填写日期时间",
            "invalid_directory": "输出目录必须是 data/exports 下的安全相对子目录",
            "cancelled": "导出已取消",
            "invalid_range": "起始时间不能晚于结束时间",
            "chat_required": "请先选择群组或频道",
            "invalid_chat": "群组 ID 无效",
            "task_name_required": "请填写任务名称",
            "invalid_schedule": "定时设置无效",
            "task_running": "该任务正在运行，不能重复执行或删除",
            "chats_loaded": "已加载 {count} 个群组/频道",
            "started": "导出任务已启动",
            "completed": "导出完成，共处理 {count} 条记录，生成 {files} 个文件",
            "failed": "导出失败: {error}",
            "progress": "{phase}，已处理 {progress}",
            "cancelling": "正在取消导出",
            "nothing_to_cancel": "当前没有可取消的导出",
            "task_saved": "定时任务“{name}”已保存",
            "task_required": "请先选择定时任务",
            "task_toggled": "定时任务“{name}”已{status}",
            "task_deleted": "定时任务“{name}”已删除",
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
    "export": {
        "enabled": "启用",
        "disabled": "暂停",
        "schedule": {
            "hourly": "每小时",
            "daily": "每天",
            "weekly": "每周",
        },
        "weekday": {
            "0": "星期一",
            "1": "星期二",
            "2": "星期三",
            "3": "星期四",
            "4": "星期五",
            "5": "星期六",
            "6": "星期日",
        },
        "phase": {
            "queued": "等待执行",
            "reading_groups": "正在读取群元数据和管理员",
            "reading_messages": "正在读取群消息",
            "writing_files": "正在提交导出文件",
            "cancelling": "正在取消",
            "completed": "已完成",
            "failed": "执行失败",
            "cancelled": "已取消",
        },
        "warning": {
            "details": "群详情不可读",
            "administrators": "管理员列表不可读",
            "details_and_administrators": "群详情或管理员列表不可读",
        },
        "placeholder": {
            "photo": "[图片]",
            "document": "[文件]",
            "video": "[视频]",
            "audio": "[音频]",
            "voice": "[语音]",
            "sticker": "[贴纸]",
            "animation": "[GIF]",
            "video_note": "[视频消息]",
            "contact": "[联系人]",
            "poll": "[投票]",
            "location": "[位置]",
            "service": "[系统消息]",
            "media": "[媒体]",
        },
        "html": {
            "language": "zh-CN",
            "title": "聊天记录归档",
            "groups_title": "Telegram 群列表",
            "messages_title": "{chat} 聊天记录",
            "chat_id": "群 ID",
            "kind": "类型",
            "created_at": "创建时间",
            "username": "用户名",
            "member_count": "成员数",
            "description": "简介",
            "administrators": "管理员",
            "bot": "机器人",
            "none": "无可读取数据",
            "reply_to": "回复",
            "search": "搜索",
            "search_placeholder": "内容、发送者或消息 ID",
            "date_from": "开始日期",
            "date_to": "结束日期",
            "apply_filters": "筛选",
            "reset_filters": "重置",
            "page_size": "每页",
            "page_input": "页码",
            "previous_page": "上一页",
            "next_page": "下一页",
            "page_status": "{page} / {pages}",
            "page_of": "/ {pages}",
            "result_status": "第 {start}-{end} 条，共 {total} 条",
            "filter_progress": "正在筛选 {current}/{total}",
            "archive_summary": "{total} 条消息 · 导出于 {exported_at}",
            "range": "范围",
            "loading": "正在加载…",
            "no_results": "没有符合条件的消息",
            "unknown_sender": "未知发送者",
            "edited": "已编辑",
            "open_reply": "定位到被回复的消息",
            "reply_summary": "回复 {sender} · {time} · #{id}",
            "reply_missing": "回复消息 #{id} · 不在本次导出范围",
            "reply_count": "{count} 条回复",
            "open_thread": "单独查看此消息的回复列表",
            "thread_loading_title": "回复列表",
            "thread_loading": "正在整理回复 · 已发现 {count} 条",
            "thread_title": "消息 #{id} 的回复列表",
            "thread_summary": "共 {count} 条消息",
            "back_to_messages": "返回消息列表",
            "load_error": "无法加载数据文件：{file}",
            "archive_readme": "解压整个归档后，使用浏览器打开 index.html。请勿单独移动 index.html 或 data 目录。\n",
        },
    },

    "misc": {
        "login_success": "登录成功 - {name}",
        "media_group_info": "媒体组={count}项, ",
        "no_match_rules": "无匹配规则",
        "all_media_types": "全部",
        "unlimited": "不限",
        "unknown": "未知",
        "rule_name_template": "规则 {count}",
        "button_action_rule_name_template": "按钮处理规则 {count}",
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

    # ===== Admin Bot Commands =====
    "bot_cmd": {
        "no_permission": "⛔ 你没有权限使用此命令",
        "yes": "是",
        "no": "否",
        "enabled": "已启用",
        "disabled": "已禁用",
        "welcome": "🤖 **TeleRelay 管理面板**\n\n"
            "可用命令:\n"
            "`/status` 查看运行状态\n"
            "`/bot start` 启动转发服务\n"
            "`/bot stop` 停止转发服务\n"
            "`/bot restart` 重启转发服务\n"
            "`/rule list` 列出所有规则\n"
            "`/rule detail 规则名` 查看规则详情\n"
            "`/rule add 规则名` 添加规则\n"
            "`/rule del 规则名` 删除规则\n"
            "`/rule rename 旧规则名 新规则名` 重命名规则\n"
            "`/rule toggle 规则名` 启用/禁用规则\n"
            "`/rule set 规则名 <属性> <值>` 修改规则\n"
            "`/stats reset` 重置转发统计\n\n"
            "**可设置的属性:** `source`, `target`, `keywords`, `regex`, `mode`, `delay`, `force_forward`, `hide_sender`, `add_source_info`, `preserve_format`, `ignore_users`, `ignore_keywords`, `media_types`, `max_file_size`, `min_file_size`\n\n"
            "💡 列表型字段可用 `clear` 清空",
        "status_msg": "📊 **运行状态**\n\n"
            "{running_icon} 运行中: {running}\n"
            "{connected_icon} 已连接: {connected}\n"
            "📨 已转发: {forwarded}\n"
            "🚫 已过滤: {filtered}\n"
            "📊 总计: {total}\n"
            "📋 规则: {enabled}/{rule_total} 个启用",
        "stats_usage": "用法: `/stats reset` 重置转发统计",
        "stats_reset_done": "✅ 转发统计已重置",
        "bot_usage": "用法: `/bot start` | `/bot stop` | `/bot restart`",
        "bot_already_running": "⚠️ 转发服务已在运行中",
        "bot_started": "✅ 转发服务已启动",
        "bot_start_failed": "❌ 转发服务启动失败",
        "bot_not_running": "⚠️ 转发服务未在运行",
        "bot_stopped": "✅ 转发服务已停止",
        "bot_stop_failed": "❌ 转发服务停止失败",
        "bot_restarting": "🔄 正在重启转发服务...",
        "bot_restarted": "✅ 转发服务已重启",
        "bot_restart_failed": "❌ 转发服务重启失败",
        "rule_usage": "用法:\n"
            "`/rule list` 列出规则\n"
            "`/rule detail 规则名` 查看详情\n"
            "`/rule add 规则名` 添加规则\n"
            "`/rule del 规则名` 删除规则\n"
            "`/rule rename 旧规则名 新规则名` 重命名\n"
            "`/rule toggle 规则名` 启用/禁用\n"
            "`/rule set 规则名 <属性> <值>` 修改属性",
        "no_rules": "📋 暂无转发规则",
        "rules_header": "📋 **转发规则列表**",
        "rule_name_required": "⚠️ 请指定规则名称",
        "rule_not_found": "❌ 未找到规则: {name}",
        "rule_exists": "⚠️ 规则 '{name}' 已存在",
        "rule_added": "✅ 已添加规则: {name}",
        "rule_deleted": "✅ 已删除规则: {name}",
        "rule_delete_last": "⚠️ 至少需要保留一个规则",
        "rule_toggled": "✅ 规则 '{name}' 已{status}",
        "rule_renamed": "✅ 已将规则 '{old_name}' 重命名为 '{new_name}'",
        "rule_rename_usage": "用法: `/rule rename 旧规则名 新规则名`\n\n💡 名称含空格时请用引号包裹",
        "rule_name_empty": "⚠️ 规则名称不能为空",
        "rule_detail_msg": "📋 **规则: {name}**\n\n"
            "状态: {status}\n"
            "模式: `{mode}`\n\n"
            "**📥 源:**\n{sources}\n\n"
            "**📤 目标:**\n{targets}\n\n"
            "**🔍 关键词:** {keywords}\n"
            "**🔍 正则:** {regex}\n"
            "**🎞️ 媒体类型:** {media_types}\n"
            "**📦 文件大小:** {file_size}\n\n"
            "**⚙️ 选项:**\n"
            "  延迟: `{delay}s`\n"
            "  保留格式: `{preserve_format}`\n"
            "  添加来源: `{add_source_info}`\n"
            "  强制转发: `{force_forward}`\n"
            "  隐藏发送者: `{hide_sender}`\n\n"
            "**🚫 忽略:**\n"
            "  用户: {ignored_users}\n"
            "  关键词: {ignored_keywords}",
        "rule_set_usage": "用法: `/rule set 规则名 <属性> <值>`\n\n"
            "可设置的属性:\n"
            "`source` 源群组 (逗号分隔)\n"
            "`target` 目标群组 (逗号分隔)\n"
            "`keywords` 关键词 (逗号分隔)\n"
            "`regex` 正则表达式 (逗号分隔)\n"
            "`mode` 模式 (whitelist/blacklist)\n"
            "`delay` 延迟秒数\n"
            "`force_forward` 强制转发 (true/false)\n"
            "`hide_sender` 隐藏发送者 (true/false)\n"
            "`add_source_info` 添加来源 (true/false)\n"
            "`preserve_format` 保留格式 (true/false)\n"
            "`ignore_users` 忽略用户ID (逗号分隔)\n"
            "`ignore_keywords` 忽略关键词 (逗号分隔)\n"
            "`media_types` 媒体类型 (逗号分隔)\n"
            "`max_file_size` 最大文件大小 (MB)\n"
            "`min_file_size` 最小文件大小 (MB)\n\n"
            "💡 列表型字段可传 `clear` 清空",
        "invalid_mode": "⚠️ 模式必须是 whitelist 或 blacklist",
        "invalid_media_types": "⚠️ 无效的媒体类型: {types}\n合法值: {valid}",
        "unknown_field": "⚠️ 未知属性: {field}",
        "rule_updated": "✅ 规则 '{name}' 已更新: {field} = {value}",
        "rule_set_error": "❌ 设置失败: {error}",
        "account_not_authenticated": "⚠️ 当前账号尚未完成认证",
        # Mini App
        "webapp_button": "打开配置面板",
        "webapp_open": "点击下方按钮打开 WebUI 配置面板 👇",
        "webapp_not_configured": "⚠️ 未配置 WebApp URL\n\n"
            "请在 `.env` 文件中设置 `WEBAPP_URL` 为你的 WebUI 公网 HTTPS 地址\n"
            "例如: `WEBAPP_URL=https://your-domain.com:8080`",
        "webapp_url_invalid": "❌ 发送 WebApp 按钮失败: {error}\n\n"
            "请确保 `.env` 中的 `WEBAPP_URL` 是一个有效的公网 HTTPS 地址 (Telegram 不允许使用 localhost 或无效的域名)。",
        # History command
        "history_empty": "📜 暂无转发历史记录",
        "history_header": "📜 **最近 {count} 条转发记录** (共 {total} 条)",
        # Config command
        "config_usage": "用法:\n`/config export` 导出配置文件\n`/config import` 导入配置（回复一个 YAML 文件）",
        "config_exported": "📤 当前配置文件",
        "config_not_found": "❌ 配置文件不存在",
        "config_import_usage": "⚠️ 请回复一个 YAML 配置文件使用此命令\n\n用法: 先发送配置文件，然后回复该文件并输入 `/config import`",
        "config_invalid_file": "❌ 无效的配置文件（未找到转发规则）",
        "config_imported": "✅ 配置已导入，下次启动时生效",
        "config_imported_restarted": "✅ 配置已导入，Bot 已重启",
        "config_import_error": "❌ 导入失败: {error}",
    },
}
