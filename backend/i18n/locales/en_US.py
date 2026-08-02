"""
English translation file (en_US)
Contains all English text translations
"""

TRANSLATIONS = {
    # ===== Log Related =====

    # log.main.* - main.py logs
    "log": {
        "main": {
            "startup": "TeleRelay starting...",
            "auth_manager_created": "✓ AuthManager created (User mode)",
            "session_detected": "Session cache detected, starting Bot automatically...",
            "web_address": "Web interface address: http://{host}:{port}",
            "auth_enabled": "✓ HTTP Basic Auth enabled",
            "auth_warning": "⚠ HTTP Basic Auth not enabled, authentication recommended for production",
            "shutdown": "\\nShutdown signal received, closing...",
            "error": "Program error: {error}",
            "admin_bot_started": "✓ Admin Bot started",
            "api_ready": "TeleRelay API ready on {host}:{port}",
        },

        # log.bot.* - bot_manager.py logs
        "bot": {
            "already_running": "Bot is already running",
            "thread_created": "Bot startup thread created",
            "start_failed": "Failed to start Bot: {error}",
            "error": "Bot error: {error}",
            "config_validation_failed": "Configuration validation failed: {error}",
            "connect_failed": "Unable to connect to Telegram",
            "user_info_failed": "Failed to get user info: {error}",
            "rule_registered": "✓ Rule '{rule}' registered, monitoring {count} sources",
            "started": "✓ Bot started with {count} rules",
            "stopped": "Bot stopped",
            "main_error": "Bot main logic error: {error}",
            "message_received": "Message received - source={chat} ({chat_id}), sender={sender} ({sender_id}), content={preview}",
            "not_running": "Bot is not running",
            "stopping": "Stopping Bot...",
            "stop_success": "✓ Bot stopped",
            "stop_failed": "Failed to stop Bot: {error}",
            "restarting": "Restarting Bot...",
            "restart_failed": "Unable to stop Bot, restart failed",
        },

        "forward_queue": {
            "enqueued": "Added to forwarding queue - rule={rule}, source={source}, pending={queue_depth}",
            "duplicate": "↩ Duplicate forward task ignored - rule={rule}, source={source}",
            "media_group_enqueued": "Media group added to forwarding queue - rule={rule}, source={source}, pending={queue_depth}",
            "media_group_merged": "Media group member merged - rule={rule}, source={source}, pending={queue_depth}",
            "restored": "Persistent forward queue restored: requeued {recovered}, purged {purged} completed items",
            "paused": "FloodWait triggered; entire forward queue paused for {seconds:.1f}s - Rule: {rule}, Source: {chat_id}/{message_id}, Target: {target}",
            "retry": "Forward task failed; retrying in {seconds:.1f}s - Rule: {rule}, Source: {chat_id}/{message_id}, Target: {target}, Error: {error}",
            "failed": "Forward task failed after {attempts} attempts - Rule: {rule}, Source: {chat_id}/{message_id}, Target: {target}, Error: {error}",
            "loop_error": "Persistent forward queue loop failed and will recover: {error}",
            "recovery_failed": "Failed to recover persistent forward queue processing state",
        },

        "button_action": {
            "user_mode_required": "Message button handling requires Telegram User mode; all rules were skipped",
            "registered": "✓ Button rules registered - rules={rules}, chats={chats}",
            "clicked": "✓ Button handled - rule={rule}, buttons=[{buttons}], count={count}, message={chat_id}/{message_id}, content={content}",
            "failed": "Button handling failed - Message: {chat_id}/{message_id}, Error: {error}",
        },

        # log.client.* - client.py logs
        "client": {
            "proxy_unsupported": "Unsupported proxy type: {type}",
            "proxy_using": "Using proxy: {type} {host}:{port}",
            "proxy_parse_failed": "Failed to parse proxy configuration: {error}",
            "bot_token_required": "Bot mode requires BOT_TOKEN",
            "bot_connected": "Connected to Telegram using Bot Token",
            "session_detected": "Existing session detected, attempting auto-login...",
            "user_logged_in": "Logged in to Telegram - User: {name} (@{username})",
            "phone_invalid": "Invalid phone number format",
            "code_invalid": "Invalid verification code",
            "password_invalid": "Invalid two-step verification password",
            "auth_timeout": "Authentication timeout: {error}",
            "connect_failed": "Failed to connect to Telegram: {error}",
            "disconnected": "Disconnected from Telegram",
            "client_not_initialized": "Client not initialized",
            "flood_wait": "Rate limit triggered, need to wait {seconds} seconds",
            "message_error": "Error processing message: {error}",
            "handler_registered": "Message handler registered - Monitoring {count} chats",
            "running": "Telegram client started running...",
            "session_deleted": "Session file deleted: {file}",
            "session_cleared": "Session files cleared",
            "session_clear_failed": "Failed to clear session files: {error}",
            "photo_refresh_failed": "Failed to refresh Telegram profile photo: {error}",
        },

        # log.forward.* - forwarder related logs
        "forward": {
            "flood_wait": "Rate limit triggered, retrying after {seconds} seconds",
            "error": "Failed to forward message: {error}",
            "no_target": "No target chat configured",
            "download_failed": "Force download failed, unable to forward",
            "restricted_fallback": "Forward restricted - using download and resend",
            "fallback_failed": "Fallback forward to {target} failed: {error}",
            "target_failed": "Failed to forward message to {target}: {error}",
            "direct_success": "✓ Direct forward succeeded - target={target}",
            "copy_success": "✓ Attributed copy succeeded - target={target}",
            "text_sent": "✓ Text sent - target={target}",
            "uploading": "⬆️ Uploading media - target={target}",
            "force_success": "✓ Download and resend succeeded - target={target}",
            "target_resolve_failed": "Target resolution failed; using raw value - target={target}, error={error}",
            "history_failed": "Forward history write failed - error={error}",
            "success": "✅ Forward succeeded - rule={rule}, source={source}, {group_info}targets=[{targets}], result={success}/{total}, content={preview}",
            "all_failed": "❌ Forward failed: \"{preview}\" → All targets failed",
            "source_label": "📢 Source: https://t.me/{username}/{msg_id}",
            "source_private": "📢 Source: https://t.me/c/{channel_id}/{msg_id}",
            "source_unknown": "📢 Source: {chat_title}",

            # downloader
            "downloader": {
                "downloading": "⬇️ Downloading media",
                "complete": "⬇️ Media download complete - file={filename}, size={size}MB",
                "group_downloading": "⬇️ Downloading media group - count={count}",
                "group_progress": "⬇️ Downloading media group - progress={current}/{total}, file={filename}",
                "group_complete": "⬇️ Media group download complete - files={count}",
                "cleanup": "Temporary files cleaned - path={path}",
                "cleanup_failed": "Failed to clean up temporary files: {path}, {error}",
                "purge_failed": "Failed to purge temp directory: {error}",
            },

            # media_group
            "media_group": {
                "collected": "📎 Media group collected - count={count}",
                "fetch_failed": "Failed to fetch media group messages: {error}, processing as single message",
                "duplicate": "↩ Duplicate media group ignored",
                "filtered": "Media group filtered - reason=no matching messages",
            },

            # dedup
            "deduplicated": "↩ Duplicate content ignored - content={preview}",
        },

        # log.filter.* - filters.py logs
        "filter": {
            "regex_invalid": "Invalid regex pattern '{pattern}': {error}",
            "initialized": "Filter initialized - mode={mode}, regex={regex_count}, keywords={keyword_count}, media={media_types}, file_size={min_size}-{max_size}",
            "media_type_filtered": "Media type filtered - type={type}, allowed={allowed}",
            "file_too_small": "File filtered - reason=too small, size={size}, minimum={min_size}",
            "file_too_large": "File filtered - reason=too large, size={size}, maximum={max_size}",
            "regex_matched": "Regex matched - pattern={pattern}",
            "keyword_matched": "Keyword matched - keyword={keyword}",
            "user_ignored": "User ignored - user={user_id}",
            "keyword_ignored": "Keyword ignored - keyword={keyword}",
        },

        # log.auth.* - auth_manager.py logs
        "auth": {
            "initialized": "AuthManager initialized",
            "state_updated": "Authentication state updated: {state} {error}",
            "user_info_saved": "User info saved: {info}",
            "submitted": "{name} submitted",
            "queue_full": "{name} queue is full, please do not submit repeatedly",
            "phone_masked": "Phone number: {phone}***",
            "waiting": "Waiting for user to input {name}...",
            "received": "Received {name}",
            "timeout": "Waiting for {name} input timeout ({timeout} seconds)",
            "get_failed": "Failed to get {name}: {error}",
            "reset": "Authentication state reset",
            # Authentication operation names
            "auth_state": "authentication state",
            "auth_flow": "authentication flow",
            "start_auth": "start authentication",
            "cancel_auth": "cancel authentication",
            "submit_phone": "submit phone number",
            "submit_code": "submit verification code",
            "submit_password": "submit password",
            "status": "status",
        },

        # log.config.* - config.py logs
        "config": {
            "env_loaded": "Environment file loaded: {path}",
            "env_not_found": "Environment file not found: {path}",
            "yaml_loaded": "YAML configuration file loaded: {path}",
            "yaml_not_found": "YAML configuration file not found: {path}",
            "saved": "Configuration saved to: {path}",
        },

        # log.admin_bot.* - admin bot logs
        "admin_bot": {
            "started": "✓ Admin Bot connected to Telegram",
            "error": "Admin Bot error: {error}",
            "proxy_failed": "Admin Bot proxy parse failed: {error}",
            "retry": "Admin Bot connection retry ({attempt}): {error}",
            "webapp_failed": "Failed to send WebApp button: {error}",
            "menu_button_set": "✓ Bot menu button set to Mini App",
            "menu_button_failed": "Failed to set Bot menu button: {error}",
        },

        # log.account.* - telegram_accounts.py logs
        "account": {
            "avatar_cache_failed": "Failed to cache Telegram account avatar: {error}",
        },

        # log.stats.* - statistics logs
        "stats": {
            "reset": "✓ Forwarding statistics reset",
            "reset_failed": "Failed to reset statistics: {error}",
        },

        # log.backup.* - backup logs
        "backup": {
            "exported": "✓ Configuration exported",
            "export_failed": "Failed to export configuration: {error}",
            "backup_created": "Current config backed up: {path}",
            "import_failed": "Failed to import configuration: {error}",
        },

        # log.export.* - data export logs
        "export": {
            "chats_loaded": "Export chat list loaded: count={count}",
            "cancel_requested": "Export cancellation requested: kind={kind}, job_id={job_id}, task_id={task_id}",
            "group_queued": "Group list export queued: job_id={job_id}, formats={formats}, directory={directory}",
            "group_started": "Group list export started: job_id={job_id}, run_id={run_id}",
            "group_progress": "Group list export progress: job_id={job_id}, processed={processed}/{total}",
            "group_completed": "Group list export completed: job_id={job_id}, run_id={run_id}, records={count}, files={files}",
            "group_cancelled": "Group list export cancelled: job_id={job_id}, run_id={run_id}",
            "group_failed": "Group list export failed: job_id={job_id}, run_id={run_id}, error={error}",
            "message_queued": "Message export queued: job_id={job_id}, task_id={task_id}, chat={chat_title} ({chat_id}), range={start} -> {end}, formats={formats}, directory={directory}",
            "message_started": "Message export started: kind={kind}, job_id={job_id}, run_id={run_id}, task_id={task_id}, chat={chat_title} ({chat_id}), range={start} -> {end}, min_message_id={min_message_id}",
            "message_progress": "Message export progress: kind={kind}, job_id={job_id}, task_id={task_id}, chat_id={chat_id}, records={count}",
            "message_completed": "Message export completed: kind={kind}, job_id={job_id}, run_id={run_id}, task_id={task_id}, chat={chat_title} ({chat_id}), records={count}, files={files}",
            "message_cancelled": "Message export cancelled: kind={kind}, job_id={job_id}, run_id={run_id}, task_id={task_id}, chat={chat_title} ({chat_id}), records={count}",
            "message_failed": "Message export failed: kind={kind}, job_id={job_id}, run_id={run_id}, task_id={task_id}, chat={chat_title} ({chat_id}), records={count}, error={error}",
            "task_saved": "Scheduled export task saved: task_id={task_id}, name={name}, chat={chat_title} ({chat_id}), schedule={schedule}, enabled={enabled}, next_run={next_run}",
            "task_state_changed": "Scheduled export task state updated: task_id={task_id}, name={name}, enabled={enabled}, next_run={next_run}",
            "task_deleted": "Scheduled export task deleted: task_id={task_id}, name={name}",
            "scheduler_started": "Export scheduler started: tasks={count}",
            "scheduler_stopped": "Export scheduler stopped",
            "task_scheduled": "Scheduled export task registered: task_id={task_id}, name={name}, next_run={next_run}",
            "task_unscheduled": "Scheduled export task paused: task_id={task_id}, name={name}",
            "task_triggered": "Scheduled export task triggered: task_id={task_id}",
            "task_job_started": "Scheduled export task submitted: task_id={task_id}, job_id={job_id}",
            "task_overlap": "Scheduled export task is still running; trigger skipped: task_id={task_id}",
            "task_start_failed": "Scheduled export task failed to start: task_id={task_id}, error={error}",
            "run_record_failed": "Could not record scheduled export failure: task_id={task_id}",
        },
    },

    # ===== UI Related =====
    "ui": {
        # ui.title.* - titles and labels
        "title": {
            "main": "📡 TeleRelay",
            "subtitle": "Telegram message relay tool",
            "tab_config": "⚙️ Configuration",
            "tab_log": "📋 Logs",
            "tab_auth": "🔐 Authentication",
            "tab_stats": "📊 Statistics",
            "tab_history": "📜 History",
            "tab_export": "📤 Export Data",
            "tab_backup": "💾 Backup",
            "config_forwarding_rules": "Forwarding Rules",
            "config_button_actions": "Message Button Handling",
        },

        # ui.button.* - buttons
        "button": {
            "start": "▶️ Start",
            "stop": "⏸️ Stop",
            "restart": "🔄 Restart",
            "refresh_status": "🔄 Refresh Status",
            "save_config": "💾 Save Configuration",
            "refresh_log": "🔄 Refresh Logs",
            "add_rule": "➕",
            "delete_rule": "🗑️",
            "rename_rule": "✏️",
            "start_auth": "🚀 Start Authentication",
            "cancel_auth": "❌ Cancel Authentication",
            "send_code": "Send Code",
            "submit_code": "Submit Code",
            "submit_password": "Submit Password",
            "reset_stats": "🔄 Reset Stats",
            "search": "🔍 Search",
            "export": "📥 Export",
            "prev_page": "◀ Prev",
            "next_page": "Next ▶",
            "refresh_stats": "🔄 Refresh",
            "export_config": "📥 Export Config",
            "import_config": "📤 Import Config",
            "refresh_chats": "🔄 Refresh Chats",
            "export_groups": "📥 Export Group List",
            "export_messages": "📥 Export Group Messages",
            "cancel_export": "⏹ Cancel Export",
            "new_task": "➕ New Task",
            "save_task": "💾 Save Task",
            "run_now": "▶ Run Now",
            "toggle_task": "⏯ Pause/Resume",
            "delete_task": "🗑 Delete Task",
            "refresh_tasks": "🔄 Refresh Tasks",
            "save_button_action": "💾 Save Button Rule",
        },

        # ui.label.* - labels
        "label": {
            "status": "Status",
            "forwarded": "Forwarded",
            "filtered": "Filtered",
            "total": "Total",
            "operation_message": "Operation Message",
            "current_rule": "📋 Current Rule",
            "enable": "Enable",
            "new_name": "New Name",
            "source_chats": "Source Groups/Channels",
            "target_chats": "Target Groups/Channels",
            "regex_patterns": "Regex Patterns",
            "keywords": "Keywords",
            "filter_mode": "Filter Mode",
            "media_types": "Allowed Message Types",
            "max_file_size": "Max File Size (MB)",
            "ignored_user_ids": "Ignored User IDs",
            "ignored_keywords": "Ignored Keywords",
            "preserve_format": "Preserve Original Format",
            "add_source_info": "Add Source Info",
            "force_forward": "Enable Force Forward",
            "hide_sender": "Hide Sender",
            "delay": "Forward Delay (seconds)",
            "save_result": "Save Result",
            "realtime_log": "Realtime Logs",
            "log_lines": "Display Lines",
            "auth_status": "Authentication Status",
            "phone": "Phone Number",
            "code": "Verification Code",
            "password": "Two-Step Verification Password",
            "error_info": "Error Info",
            "current_button_action_rule": "📋 Current Button Rule",
            "button_action_source_chats": "Bots / Chats to Monitor",
            "button_action_texts": "Button Text Patterns",
            "button_action_match_mode": "Text Match Mode",
            "button_action_delay": "Click Delay (seconds)",
            "button_action_click_all_matches": "Click All Matching Buttons",
            # Stats tab
            "rule_stats": "📋 Per-Rule Statistics",
            "daily_trend": "📈 Daily Forwarding Trend",
            "days_range": "Days Range",
            "export_format": "Export Format",
            "export_file": "Export File",
            "no_stats_data": "No statistics data available",
            "rule_name": "Rule Name",
            "date": "Date",
            "count": "Count",
            # History tab
            "rule_filter": "Rule Filter",
            "search_keyword": "Search Keyword",
            "time": "Time",
            "source": "Source",
            "sender": "Sender",
            "content": "Content",
            "media_type": "Media Type",
            "page_info": "Page {page}/{total} ({count} total)",
            "page_info_label": "Pagination",
            # Backup tab
            "export_config": "Export Current Config",
            "import_config": "Import Config File",
            "upload_config": "Upload config file (.yaml)",
            # Export tab
            "export_availability": "Export Status",
            "export_formats": "Export Formats",
            "export_subdirectory": "Output Subdirectory",
            "export_status": "Run Status",
            "export_files": "Export Files",
            "export_chat": "Group/Channel",
            "start_time": "Start Time",
            "end_time": "End Time",
            "all_history": "All History",
            "task_selector": "Scheduled Task",
            "task_name": "Task Name",
            "schedule_type": "Frequency",
            "schedule_minute": "Minute",
            "schedule_hour": "Hour",
            "schedule_weekday": "Weekday",
            "timezone": "Timezone",
            "task_enabled": "Enable Task",
            "task_table": "Task List",
            "run_history": "Run History",
            "task_operation": "Task Operation",
        },

        # ui.placeholder.* - placeholders
        "placeholder": {
            "source_chats": "-100123456789\n@example_channel",
            "target_chats": "-100987654321\n@target_channel\n-1001234567890",
            "regex_patterns": "\\[Important\\].*\nUrgent Notice.*",
            "keywords": "keyword1\nkeyword2",
            "ignored_user_ids": "123456789\n987654321",
            "ignored_keywords": "ad\npromotion\nspam",
            "new_name": "Enter new rule name",
            "phone": "+1234567890",
            "code": "12345",
            "password": "Enter password",
            "search_keyword": "Search message content, source, or sender",
            "task_name": "Example: Daily project group export",
            "export_subdirectory": "Example: groups or scheduled/project",
            "button_action_source_chats": "@example_bot\n-100123456789",
            "button_action_texts": "Confirm\nCheck in now\n^Claim .* reward$",
        },

        # ui.info.* - info messages
        "info": {
            "source_chats": "Enter group IDs or channel usernames to monitor, one per line",
            "target_chats": "Messages will be forwarded to these locations, one per line",
            "regex_patterns": "One regex pattern per line",
            "keywords": "One keyword per line",
            "filter_mode": "whitelist: Only forward matching messages | blacklist: Forward non-matching messages",
            "media_types": "Leave empty to allow all types",
            "max_file_size": "0 means no limit",
            "ignored_user_ids": "All messages from these users will be ignored, one numeric ID per line (get ID via @userinfobot)",
            "ignored_keywords": "Messages containing these keywords will be ignored, one per line (case-insensitive)",
            "preserve_format": "Preserve forward mark and original format",
            "add_source_info": "Add source group info before message",
            "hide_sender": "Use custom reference format and hide real sender source",
            "force_forward": "Download then upload, can bypass channel/group forward restrictions, may incur additional traffic",
            "delay": "Avoid triggering Telegram rate limits",
            "phone": "Enter phone number in international format",
            "code": "Enter the verification code sent by Telegram",
            "password": "You have two-step verification enabled, please enter password",
            "export_subdirectory": "Must be a relative subdirectory under data/exports",
            "all_history": "Ignore the start time and begin at the earliest Telegram record available",
            "schedule_minute": "Minute for hourly tasks; execution minute for daily/weekly tasks",
            "schedule_hour": "Execution hour for daily/weekly tasks",
            "schedule_weekday": "Weekly tasks only; 0 is Monday and 6 is Sunday",
            "button_action_source_chats": "Monitor only these bots, groups, or channels; one ID or username per line",
            "button_action_texts": "One pattern per line; in regex mode each line is a regular expression",
            "button_action_match_mode": "exact: identical text | contains: contains text | regex: regular expression",
            "button_action_delay": "Wait before clicking after receiving the message, from 0 to 30 seconds",
        },

        # ui.accordion.* - accordion titles
        "accordion": {
            "source_target": "📥 Source and Target",
            "filter_rules": "🔍 Filter Rules",
            "ignore_list": "🚫 Ignore List",
            "forward_options": "📤 Forward Options",
            "export_groups": "Group List",
            "export_messages": "Group Message History",
            "export_tasks": "Scheduled Export Tasks",
            "export_runs": "Recent Export Runs",
        },

        # ui.markdown.* - markdown text
        "markdown": {
            "ignore_warning": "⚠️ Higher priority than filter rules, matched messages will be ignored directly",
            "button_action_guide": "Available only in **Telegram User mode**. The first matching callback button is clicked by default; each rule can instead click all matching buttons. Each message is handled at most once. URL, payment, phone, location, and Mini App buttons are never clicked.",
            "auth_guide": """### Telegram User Mode Authentication

**For first-time use or when session expires, follow these steps:**

1. Click the "🚀 Start Authentication" button below
2. The page will display a phone number input field
3. Enter your phone number (international format, e.g., +8613800138000) and click "Send Code"
4. Enter the verification code sent by Telegram and click "Submit Code"
5. If two-step verification is enabled, enter your password and click "Submit Password"
""",
            "backup_guide": """### Configuration Backup & Restore

- **Export**: Click "📥 Export Config" to download current `config.yaml`
- **Import**: Upload a `.yaml` config file and click "📤 Import Config" to overwrite

⚠️ Import will automatically backup current config as `config.yaml.bak`
""",
        },

        # ui.status.* - status text
        "status": {
            "stopped": "⚫ Stopped",
            "running": "🟢 Running",
            "connecting": "🟡 Connecting...",
            "error": "❌ Status Error",
            "default_rule": "Default Rule",
            "default_button_action_rule": "Default Button Rule",
        },

        # ui.auth.* - authentication status
        "auth": {
            "idle": "Authentication not started",
            "connecting": "🔄 Connecting...",
            "waiting_phone": "⏳ Please enter phone number",
            "waiting_code": "⏳ Verification code sent to your Telegram, please check",
            "waiting_password": "⏳ Two-step verification detected, please enter password",
            "success": "✅ Authentication successful!",
            "error": "❌ Authentication failed",
            "logged_in": "✅ Logged in: {user_info}",
            "unknown": "Unknown status",
        },
    },

    # ===== Message Feedback =====
    "message": {
        # message.bot.* - bot control messages
        "bot": {
            "already_running": "Bot is already running",
            "auth_in_progress": "Authentication in progress, {state}",
            "running": "Bot is running",
            "config_invalid": "Configuration validation failed: {error}",
            "session_detected": "Authentication cache detected, auto-login in progress...",
            "auth_started": "Authentication process started, please enter credentials in the \"🔐 Authentication\" tab",
            "start_success": "Bot started successfully",
            "start_failed": "Bot failed to start",
            "not_running": "Bot is not running",
            "stop_success": "Bot stopped successfully",
            "stop_failed": "Bot failed to stop",
            "restart_success": "Bot restarted successfully",
            "restart_failed": "Bot failed to restart",
        },

        # message.auth.* - authentication messages
        "auth": {
            "in_progress": "Authentication in progress, {state}",
            "completed": "Authentication completed, Bot is running",
            "started": "Authentication process started, please follow the prompts",
            "start_failed": "Failed to start authentication process",
            "cancelled": "Authentication cancelled, session cleared",
            "cancel_failed": "Failed to cancel authentication: {error}",
            "phone_submitted": "Phone number submitted, waiting for verification code...",
            "phone_invalid": "Failed to submit phone number, please check format",
            "code_submitted": "Verification code submitted, verifying...",
            "code_failed": "Failed to submit verification code",
            "password_submitted": "Password submitted, verifying...",
            "password_failed": "Failed to submit password",
            "phone_empty": "Phone number cannot be empty",
            "phone_format": "Phone number must start with + (e.g., +8613800138000)",
            "code_empty": "Verification code cannot be empty",
            "code_format": "Verification code should be numeric only",
            "password_empty": "Password cannot be empty",
            "phone_invalid_error": "Invalid phone number format, please check format (e.g., +8613800138000)",
            "code_invalid_error": "Invalid verification code, please restart authentication",
            "password_invalid_error": "Invalid two-step verification password, please restart authentication",
        },

        # message.config.* - configuration messages
        "config": {
            "source_required": "Please configure at least one source group/channel",
            "target_required": "Please configure at least one target group/channel",
            "rule_saved": "Rule '{rule}' saved",
            "rule_saved_restarted": "{msg}, Bot restarted",
            "rule_saved_restart_failed": "{msg}, but restart failed",
            "rule_saved_next_start": "{msg}, will take effect on next start",
            "save_failed": "Save failed: {error}",
            "rule_added": "Rule '{name}' added",
            "add_failed": "Add failed: {error}",
            "rule_deleted": "Rule '{name}' deleted",
            "delete_failed": "Delete failed: {error}",
            "delete_last_rule": "At least one rule must be kept",
            "invalid_index": "Invalid rule index",
            "rule_renamed": "Renamed '{old_name}' to '{new_name}'",
            "rename_failed": "Rename failed: {error}",
            "name_empty": "Rule name cannot be empty",
            "rule_toggled": "Rule '{rule}' {status}",
            "toggle_failed": "Operation failed: {error}",
            "enabled": "enabled",
            "disabled": "disabled",
            "load_failed": "Failed to load rule: {error}",
            "button_action_user_mode": "Message button handling is available only in Telegram User mode",
            "button_action_source_required": "Configure at least one bot or chat before enabling this rule",
            "button_action_text_required": "Configure at least one button text pattern before enabling this rule",
            "button_action_regex_invalid": "Invalid button text regular expression \"{pattern}\": {error}",
            "button_action_saved": "Button rule \"{rule}\" saved",
            "button_action_saved_restarted": "{msg}, Bot restarted",
            "button_action_saved_restart_failed": "{msg}, but restart failed",
            "button_action_saved_next_start": "{msg}, will take effect on next start",
            "button_action_save_failed": "Failed to save button rule: {error}",
            "button_action_added": "Button rule \"{name}\" added",
            "button_action_add_failed": "Failed to add button rule: {error}",
            "button_action_deleted": "Button rule \"{name}\" deleted",
            "button_action_delete_failed": "Failed to delete button rule: {error}",
            "button_action_delete_last": "At least one button rule must be kept",
            "button_action_renamed": "Renamed button rule \"{old_name}\" to \"{new_name}\"",
            "button_action_rename_failed": "Failed to rename button rule: {error}",
        },

        # message.stats.* - statistics messages
        "stats": {
            "reset_success": "Statistics have been reset",
            "reset_failed": "Failed to reset statistics",
        },

        # message.backup.* - backup messages
        "backup": {
            "no_file": "Please upload a config file first",
            "invalid_yaml": "Invalid YAML file",
            "no_rules_found": "No forwarding rules found in config file",
            "import_success": "Config imported successfully, takes effect on next start",
            "import_success_restarted": "Config imported successfully, Bot restarted",
            "yaml_error": "YAML parse error: {error}",
            "import_failed": "Import failed: {error}",
        },

        "export": {
            "user_mode_required": "Full export is available only in Telegram User mode",
            "telegram_not_connected": "Telegram is not connected; start the service and finish User mode authentication",
            "ready": "Telegram is connected and ready to export",
            "format_required": "Select at least one export format",
            "invalid_timezone": "Invalid timezone: {timezone}",
            "invalid_datetime": "Invalid date/time value",
            "datetime_required": "A date/time value is required",
            "invalid_directory": "The output must be a safe relative directory under data/exports",
            "cancelled": "Export cancelled",
            "invalid_range": "Start time cannot be later than end time",
            "chat_required": "Select a group or channel first",
            "invalid_chat": "Invalid group ID",
            "task_name_required": "Enter a task name",
            "invalid_schedule": "Invalid schedule settings",
            "task_running": "This task is running and cannot be started again or deleted",
            "chats_loaded": "Loaded {count} groups/channels",
            "started": "Export job started",
            "completed": "Export completed: {count} records and {files} files",
            "failed": "Export failed: {error}",
            "progress": "{phase}; processed {progress}",
            "cancelling": "Cancelling export",
            "nothing_to_cancel": "There is no active export to cancel",
            "task_saved": "Scheduled task \"{name}\" saved",
            "task_required": "Select a scheduled task first",
            "task_toggled": "Scheduled task \"{name}\" is now {status}",
            "task_deleted": "Scheduled task \"{name}\" deleted",
        },

        # message.log.* - log messages
        "log": {
            "no_logs": "No logs available",
            "read_failed": "Failed to read logs: {error}",
        },

        # message.validation.* - validation messages
        "validation": {
            "api_missing": "Missing API_ID or API_HASH configuration",
            "bot_token_required": "Bot mode requires BOT_TOKEN configuration",
            "no_rules": "No enabled forwarding rules configured",
            "no_source": "Rule '{rule}' has no source group configured",
            "no_target": "Rule '{rule}' has no target group configured",
            "passed": "Configuration validation passed",
        },
    },

    # ===== Miscellaneous =====
    "export": {
        "enabled": "enabled",
        "disabled": "paused",
        "schedule": {
            "hourly": "Hourly",
            "daily": "Daily",
            "weekly": "Weekly",
        },
        "weekday": {
            "0": "Monday",
            "1": "Tuesday",
            "2": "Wednesday",
            "3": "Thursday",
            "4": "Friday",
            "5": "Saturday",
            "6": "Sunday",
        },
        "phase": {
            "queued": "Waiting to run",
            "reading_groups": "Reading group metadata and administrators",
            "reading_messages": "Reading group messages",
            "writing_files": "Publishing export files",
            "cancelling": "Cancelling",
            "completed": "Completed",
            "failed": "Failed",
            "cancelled": "Cancelled",
        },
        "warning": {
            "details": "Group details unavailable",
            "administrators": "Administrator list unavailable",
            "details_and_administrators": "Group details or administrators unavailable",
        },
        "placeholder": {
            "photo": "[Photo]",
            "document": "[File]",
            "video": "[Video]",
            "audio": "[Audio]",
            "voice": "[Voice]",
            "sticker": "[Sticker]",
            "animation": "[GIF]",
            "video_note": "[Video message]",
            "contact": "[Contact]",
            "poll": "[Poll]",
            "location": "[Location]",
            "service": "[Service message]",
            "media": "[Media]",
        },
        "html": {
            "language": "en",
            "title": "Message Archive",
            "groups_title": "Telegram Group List",
            "messages_title": "{chat} Message History",
            "chat_id": "Group ID",
            "kind": "Type",
            "created_at": "Created At",
            "username": "Username",
            "member_count": "Members",
            "description": "Description",
            "administrators": "Administrators",
            "bot": "bot",
            "none": "No readable data",
            "reply_to": "Reply to",
            "search": "Search",
            "search_placeholder": "Content, sender, or message ID",
            "date_from": "Start date",
            "date_to": "End date",
            "apply_filters": "Filter",
            "reset_filters": "Reset",
            "page_size": "Per page",
            "page_input": "Page",
            "previous_page": "Previous page",
            "next_page": "Next page",
            "page_status": "{page} / {pages}",
            "page_of": "/ {pages}",
            "result_status": "{start}-{end} of {total}",
            "filter_progress": "Filtering {current}/{total}",
            "archive_summary": "{total} messages · exported {exported_at}",
            "range": "Range",
            "loading": "Loading...",
            "no_results": "No matching messages",
            "unknown_sender": "Unknown sender",
            "edited": "edited",
            "open_reply": "Open the original message",
            "reply_summary": "Reply to {sender} · {time} · #{id}",
            "reply_missing": "Reply to #{id} · outside this export",
            "reply_count": "{count} replies",
            "open_thread": "Open this message's reply list",
            "thread_loading_title": "Reply list",
            "thread_loading": "Loading replies · {count} found",
            "thread_title": "Reply list for message #{id}",
            "thread_summary": "{count} messages",
            "back_to_messages": "Back to messages",
            "load_error": "Unable to load data file: {file}",
            "archive_readme": "Extract the complete archive, then open index.html in a browser. Keep index.html and the data directory together.\n",
        },
    },

    "misc": {
        "login_success": "Logged in - {name}",
        "media_group_info": "media_group={count}, ",
        "no_match_rules": "No matching rules",
        "all_media_types": "All",
        "unlimited": "Unlimited",
        "unknown": "Unknown",
        "rule_name_template": "Rule {count}",
        "button_action_rule_name_template": "Button Rule {count}",
        "via_webui": " (via WebUI)",
        "via_webui_restart": " (via WebUI restart)",
        "config_updated": " (config updated)",
        "restart_suffix": " (restart)",
        "session_cleared": ", session cleared",

        # Media type descriptions
        "media": {
            "photo": "[Photo]",
            "gif": "[GIF]",
            "video": "[Video]",
            "audio": "[Audio]",
            "voice": "[Voice]",
            "sticker": "[Sticker]",
            "video_note": "[Video Message]",
            "file": "[File]",
            "contact": "[Contact]",
            "poll": "[Poll]",
            "location": "[Location]",
            "dice": "[Emoji]",
            "media": "[Media]",
        },
    },

    # ===== Admin Bot Commands =====
    "bot_cmd": {
        "no_permission": "⛔ You don't have permission to use this command",
        "yes": "Yes",
        "no": "No",
        "enabled": "enabled",
        "disabled": "disabled",
        "welcome": "🤖 **TeleRelay Admin Panel**\n\n"
            "Available commands:\n"
            "`/status` View running status\n"
            "`/bot start` Start forwarding service\n"
            "`/bot stop` Stop forwarding service\n"
            "`/bot restart` Restart forwarding service\n"
            "`/rule list` List all rules\n"
            "`/rule detail rule_name` View rule details\n"
            "`/rule add rule_name` Add rule\n"
            "`/rule del rule_name` Delete rule\n"
            "`/rule rename old_name new_name` Rename rule\n"
            "`/rule toggle rule_name` Enable/disable rule\n"
            "`/rule set rule_name <field> <value>` Modify rule\n"
            "`/stats reset` Reset forwarding statistics\n\n"
            "**Available fields:** `source`, `target`, `keywords`, `regex`, `mode`, `delay`, `force_forward`, `hide_sender`, `add_source_info`, `preserve_format`, `ignore_users`, `ignore_keywords`, `media_types`, `max_file_size`, `min_file_size`\n\n"
            "💡 Use `clear` to empty list-type fields",
        "status_msg": "📊 **Status**\n\n"
            "{running_icon} Running: {running}\n"
            "{connected_icon} Connected: {connected}\n"
            "📨 Forwarded: {forwarded}\n"
            "🚫 Filtered: {filtered}\n"
            "📊 Total: {total}\n"
            "📋 Rules: {enabled}/{rule_total} enabled",
        "stats_usage": "Usage: `/stats reset` Reset forwarding statistics",
        "stats_reset_done": "✅ Forwarding statistics have been reset",
        "bot_usage": "Usage: `/bot start` | `/bot stop` | `/bot restart`",
        "bot_already_running": "⚠️ Forwarding service is already running",
        "bot_started": "✅ Forwarding service started",
        "bot_start_failed": "❌ Failed to start forwarding service",
        "bot_not_running": "⚠️ Forwarding service is not running",
        "bot_stopped": "✅ Forwarding service stopped",
        "bot_stop_failed": "❌ Failed to stop forwarding service",
        "bot_restarting": "🔄 Restarting forwarding service...",
        "bot_restarted": "✅ Forwarding service restarted",
        "bot_restart_failed": "❌ Failed to restart forwarding service",
        "rule_usage": "Usage:\n"
            "`/rule list` List rules\n"
            "`/rule detail rule_name` View details\n"
            "`/rule add rule_name` Add rule\n"
            "`/rule del rule_name` Delete rule\n"
            "`/rule rename old_name new_name` Rename\n"
            "`/rule toggle rule_name` Enable/disable\n"
            "`/rule set rule_name <field> <value>` Modify field",
        "no_rules": "📋 No forwarding rules configured",
        "rules_header": "📋 **Forwarding Rules**",
        "rule_name_required": "⚠️ Please specify a rule name",
        "rule_not_found": "❌ Rule not found: {name}",
        "rule_exists": "⚠️ Rule '{name}' already exists",
        "rule_added": "✅ Rule added: {name}",
        "rule_deleted": "✅ Rule deleted: {name}",
        "rule_delete_last": "⚠️ At least one rule must be kept",
        "rule_toggled": "✅ Rule '{name}' {status}",
        "rule_renamed": "✅ Rule '{old_name}' renamed to '{new_name}'",
        "rule_rename_usage": "Usage: `/rule rename old_name new_name`\n\n💡 Use quotes for names with spaces",
        "rule_name_empty": "⚠️ Rule name cannot be empty",
        "rule_detail_msg": "📋 **Rule: {name}**\n\n"
            "Status: {status}\n"
            "Mode: `{mode}`\n\n"
            "**📥 Sources:**\n{sources}\n\n"
            "**📤 Targets:**\n{targets}\n\n"
            "**🔍 Keywords:** {keywords}\n"
            "**🔍 Regex:** {regex}\n"
            "**🎞️ Media types:** {media_types}\n"
            "**📦 File size:** {file_size}\n\n"
            "**⚙️ Options:**\n"
            "  Delay: `{delay}s`\n"
            "  Preserve format: `{preserve_format}`\n"
            "  Add source info: `{add_source_info}`\n"
            "  Force forward: `{force_forward}`\n"
            "  Hide sender: `{hide_sender}`\n\n"
            "**🚫 Ignore:**\n"
            "  Users: {ignored_users}\n"
            "  Keywords: {ignored_keywords}",
        "rule_set_usage": "Usage: `/rule set rule_name <field> <value>`\n\n"
            "Available fields:\n"
            "`source` Source chats (comma-separated)\n"
            "`target` Target chats (comma-separated)\n"
            "`keywords` Keywords (comma-separated)\n"
            "`regex` Regex patterns (comma-separated)\n"
            "`mode` Mode (whitelist/blacklist)\n"
            "`delay` Delay in seconds\n"
            "`force_forward` Force forward (true/false)\n"
            "`hide_sender` Hide sender (true/false)\n"
            "`add_source_info` Add source info (true/false)\n"
            "`preserve_format` Preserve format (true/false)\n"
            "`ignore_users` Ignored user IDs (comma-separated)\n"
            "`ignore_keywords` Ignored keywords (comma-separated)\n"
            "`media_types` Media types (comma-separated)\n"
            "`max_file_size` Max file size (MB)\n"
            "`min_file_size` Min file size (MB)\n\n"
            "💡 Use `clear` to empty list-type fields",
        "invalid_mode": "⚠️ Mode must be whitelist or blacklist",
        "invalid_media_types": "⚠️ Invalid media types: {types}\nValid types: {valid}",
        "unknown_field": "⚠️ Unknown field: {field}",
        "rule_updated": "✅ Rule '{name}' updated: {field} = {value}",
        "rule_set_error": "❌ Set failed: {error}",
        "account_not_authenticated": "⚠️ The current account is not authenticated yet",
        # Mini App
        "webapp_button": "Open Config Panel",
        "webapp_open": "Click the button below to open WebUI config panel 👇",
        "webapp_not_configured": "⚠️ WebApp URL not configured\n\n"
            "Please set `WEBAPP_URL` in your `.env` file to your WebUI public HTTPS address\n"
            "Example: `WEBAPP_URL=https://your-domain.com:8080`",
        "webapp_url_invalid": "❌ Failed to send WebApp button: {error}\n\n"
            "Ensure your `WEBAPP_URL` in `.env` is a valid public HTTPS URL (Telegram rejects localhost or invalid URLs).",
        # History command
        "history_empty": "📜 No forwarding history yet",
        "history_header": "📜 **Recent {count} forwarding records** ({total} total)",
        # Config command
        "config_usage": "Usage:\n`/config export` Export config file\n`/config import` Import config (reply to a YAML file)",
        "config_exported": "📤 Current configuration file",
        "config_not_found": "❌ Configuration file not found",
        "config_import_usage": "⚠️ Please reply to a YAML config file with this command\n\nUsage: Send a config file first, then reply to it with `/config import`",
        "config_invalid_file": "❌ Invalid config file (no forwarding rules found)",
        "config_imported": "✅ Config imported, takes effect on next start",
        "config_imported_restarted": "✅ Config imported, Bot restarted",
        "config_import_error": "❌ Import failed: {error}",
    },
}
