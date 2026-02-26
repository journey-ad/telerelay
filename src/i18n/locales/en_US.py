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
            "rule_registered": "✓ Rule '{rule}' registered, monitoring {count} source(s)",
            "started": "✓ Bot started with {count} rule(s)",
            "stopped": "Bot stopped",
            "main_error": "Bot main logic error: {error}",
            "message_received": "Message received - From: {chat} ({chat_id}), Sender: {sender} ({sender_id}), Content: {preview}",
            "message_filtered": "Message filtered [{rules}]{group_tag}",
            "not_running": "Bot is not running",
            "stopping": "Stopping Bot...",
            "stop_success": "✓ Bot stopped",
            "stop_failed": "Failed to stop Bot: {error}",
            "restarting": "Restarting Bot...",
            "restart_failed": "Unable to stop Bot, restart failed",
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
            "handler_registered": "Message handler registered - Monitoring {count} chat(s)",
            "running": "Telegram client started running...",
            "session_deleted": "Session file deleted: {file}",
            "session_cleared": "Session files cleared",
            "session_clear_failed": "Failed to clear session files: {error}",
        },

        # log.forward.* - forwarder related logs
        "forward": {
            "flood_wait": "Rate limit triggered, retrying after {seconds} seconds",
            "error": "Failed to forward message: {error}",
            "no_target": "No target chat configured",
            "download_failed": "Force download failed, unable to forward",
            "restricted_fallback": "Forward restricted, falling back to download and resend",
            "fallback_failed": "Fallback forward to {target} failed: {error}",
            "target_failed": "Failed to forward message to {target}: {error}",
            "direct_success": "✓ Directly forwarded to {target}",
            "copy_success": "✓ Copied with reference to {target}",
            "text_sent": "✓ Text sent to {target}",
            "uploading": "⬆️ Starting upload to {target}...",
            "force_success": "✓ Force forwarded to {target}",
            "success": "✅ Forward successful{group_info}: \"{preview}\"{group_id_info} → {success}/{total} target(s)",
            "all_failed": "❌ Forward failed: \"{preview}\" → All targets failed",
            "source_label": "📢 Source: https://t.me/{username}/{msg_id}",
            "source_private": "📢 Source: https://t.me/c/{channel_id}/{msg_id}",
            "source_unknown": "📢 Source: {chat_title}",

            # downloader
            "downloader": {
                "downloading": "⬇️ Starting media file download...",
                "complete": "⬇️ Download complete: {filename} ({size} MB)",
                "group_downloading": "⬇️ Starting media group download ({count} items)...",
                "group_progress": "⬇️ Downloading {current}/{total}: {filename}",
                "group_complete": "⬇️ Media group download complete: {count} file(s)",
                "cleanup": "Temporary files cleaned up: {path}",
                "cleanup_failed": "Failed to clean up temporary files: {path}, {error}",
            },

            # media_group
            "media_group": {
                "collected": "📎 Media group grouped_id={group_id}: {count} message(s) total",
                "fetch_failed": "Failed to fetch media group messages: {error}, processing as single message",
                "duplicate": "↩ Media group duplicate trigger, skipping (grouped_id={group_id})",
                "filtered": "Media group filtered (no matching messages) - grouped_id: {group_id}",
            },

            # dedup
            "deduplicated": "↩ Duplicate message skipped (content: {preview})",
        },

        # log.filter.* - filters.py logs
        "filter": {
            "regex_invalid": "Invalid regex pattern '{pattern}': {error}",
            "initialized": "Filter initialized - Mode: {mode}, Regex: {regex_count}, Keywords: {keyword_count}, Media types: {media_types}, File size: {min_size}-{max_size}",
            "media_type_filtered": "Media type filtered: {type} not in allowed list {allowed}",
            "file_too_small": "File too small, filtered: {size} < {min_size}",
            "file_too_large": "File too large, filtered: {size} > {max_size}",
            "regex_matched": "Regex matched: {pattern}",
            "keyword_matched": "Keyword matched: {keyword}",
            "user_ignored": "User ignored: {user_id}",
            "keyword_ignored": "Keyword ignored: {keyword}",
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
            "menu_button_set": "✓ Bot menu button set to Mini App",
            "menu_button_failed": "Failed to set Bot menu button: {error}",
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
            "tab_backup": "💾 Backup",
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
        },

        # ui.accordion.* - accordion titles
        "accordion": {
            "source_target": "📥 Source and Target",
            "filter_rules": "🔍 Filter Rules",
            "ignore_list": "🚫 Ignore List",
            "forward_options": "📤 Forward Options",
        },

        # ui.markdown.* - markdown text
        "markdown": {
            "ignore_warning": "⚠️ Higher priority than filter rules, matched messages will be ignored directly",
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
    "misc": {
        "login_success": "Logged in - {name}",
        "media_group_info": " (Media group {count} items)",
        "no_match_rules": "No matching rules",
        "all_media_types": "All",
        "unlimited": "Unlimited",
        "unknown": "Unknown",
        "rule_name_template": "Rule {count}",
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
