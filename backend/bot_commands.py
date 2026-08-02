"""
Admin Bot Module
Provides Telegram Bot command interface for managing forwarding rules and bot lifecycle.
Uses a separate Bot instance from the main forwarding system.
"""
import asyncio
import os
import shlex
import shutil
import tempfile
import threading
from contextvars import ContextVar
from pathlib import Path
from typing import TYPE_CHECKING, Optional, List

import yaml
from telethon import TelegramClient, events
from telethon.tl.types import (
    KeyboardButtonWebView,
    KeyboardButtonRow,
    ReplyInlineMarkup,
    BotMenuButton,
    DataJSON,
)
from telethon.tl.functions.bots import SetBotMenuButtonRequest
from telethon.errors import FloodWaitError
from backend.config import Config
from backend.logger import get_logger
from backend.rule import ForwardingRule, save_rules_to_config
from backend.i18n import t

if TYPE_CHECKING:
    from backend.application import ApplicationContext

logger = get_logger()


class AdminBotManager:
    """Admin Bot Manager - manages configuration and rules via Telegram commands"""

    def __init__(
        self,
        config: Config,
        bot_manager,
        context: "ApplicationContext | None" = None,
    ):
        """
        Initialize Admin Bot Manager

        Args:
            config: Configuration object
            bot_manager: BotManager instance for controlling the forwarding service
        """
        self.config = config
        self.bot_manager = bot_manager
        self.context = context
        self.client: Optional[TelegramClient] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self._command_account_id: ContextVar[str | None] = ContextVar(
            "admin_bot_account_id",
            default=None,
        )

    def run(self) -> None:
        """Run Admin Bot in a separate thread (blocking)"""
        try:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.loop.run_until_complete(self._start())
        except Exception as e:
            logger.error(t("log.admin_bot.error", error=str(e)), exc_info=True)
        finally:
            if self.loop:
                self.loop.close()

    async def _start(self) -> None:
        """Start Admin Bot client and register command handlers"""
        from urllib.parse import urlparse

        session_dir = Path("data")
        session_dir.mkdir(exist_ok=True)
        session_name = str(session_dir / "admin_bot_session")

        # Parse proxy
        proxy = None
        if self.config.proxy_url:
            try:
                parsed = urlparse(self.config.proxy_url)
                proxy_type = parsed.scheme.lower()
                if proxy_type in ['socks5', 'http', 'socks4']:
                    import python_socks
                    type_map = {
                        'socks5': python_socks.ProxyType.SOCKS5,
                        'socks4': python_socks.ProxyType.SOCKS4,
                        'http': python_socks.ProxyType.HTTP,
                    }
                    proxy = (
                        type_map[proxy_type],
                        parsed.hostname,
                        parsed.port or 1080,
                        True,
                        parsed.username,
                        parsed.password,
                    )
            except Exception as e:
                logger.warning(t("log.admin_bot.proxy_failed", error=str(e)))

        self.client = TelegramClient(
            session_name,
            self.config.api_id,
            self.config.api_hash,
            proxy=proxy,
            connection_retries=5,
            retry_delay=2,
            auto_reconnect=True,
        )

        # Register command handlers
        self._register_handlers()

        # Start with retry for DC migration through proxy
        max_retries = 3
        for attempt in range(max_retries):
            try:
                await self.client.start(bot_token=self.config.admin_bot_token)
                break
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(t("log.admin_bot.retry", attempt=attempt + 1, error=str(e)))
                    await asyncio.sleep(3)
                else:
                    raise

        logger.info(t("log.admin_bot.started"))

        await self._set_menu_button()

        await self.client.run_until_disconnected()

    async def _control_runtime(self, action: str) -> bool:
        """Execute the captured account's lifecycle operation on FastAPI's loop."""
        owner_loop = self.bot_manager.loop
        if owner_loop is None or owner_loop.is_closed():
            return False
        account_id = self._command_account_id.get()
        if account_id and self.context and self.context.accounts:
            if action == "start":
                operation = lambda: self.bot_manager.start_account(account_id)
            elif action == "stop":
                operation = lambda: self.bot_manager.stop_account(account_id)
            else:
                operation = getattr(self.bot_manager.get_runtime(account_id), action)
        else:
            operation = getattr(self.bot_manager, action)
        if asyncio.get_running_loop() is owner_loop:
            return await operation()
        future = asyncio.run_coroutine_threadsafe(operation(), owner_loop)
        return await asyncio.wrap_future(future)

    async def _control_sync(self, operation) -> None:
        """Execute a synchronous runtime mutation on FastAPI's event loop."""
        owner_loop = self.bot_manager.loop
        if owner_loop is None or owner_loop.is_closed():
            operation()
            return

        async def execute() -> None:
            operation()

        if asyncio.get_running_loop() is owner_loop:
            await execute()
            return
        future = asyncio.run_coroutine_threadsafe(execute(), owner_loop)
        await asyncio.wrap_future(future)

    async def _run_account_command(self, event, handler) -> None:
        """Pin a command to one account even if the active account changes mid-command."""
        account_id = None
        if self.context and self.context.accounts:
            try:
                account_id = self.context.scope_for().account_id
            except ValueError:
                await event.reply(t("bot_cmd.account_not_authenticated"))
                return
        token = self._command_account_id.set(account_id)
        try:
            await handler(event)
        finally:
            self._command_account_id.reset(token)

    def _account_scope(self):
        """Return the scope for the account pinned by this command."""
        if not self.context or not self.context.accounts:
            return None
        account_id = self._command_account_id.get()
        return self.context.scope_for(account_id)

    def _active_config(self) -> Config:
        scope = self._account_scope()
        return scope.config if scope else self.config

    def _active_stats(self):
        scope = self._account_scope()
        if scope:
            return scope.stats
        from backend.stats_db import get_stats_db

        return get_stats_db()

    def _active_runtime(self):
        scope = self._account_scope()
        return scope.runtime if scope else self.bot_manager

    def _active_status(self) -> dict:
        scope = self._account_scope()
        if scope:
            return self.bot_manager.get_status(scope.account_id)
        return self.bot_manager.get_status()

    def _register_handlers(self) -> None:
        """Register all command handlers"""

        @self.client.on(events.NewMessage(pattern=r'^/start\b'))
        async def handle_start(event):
            if not self._check_permission(event):
                await event.reply(t("bot_cmd.no_permission"))
                return
            # Welcome message
            webapp_url = self.config.webapp_url
            if webapp_url:
                buttons = ReplyInlineMarkup(
                    rows=[
                        KeyboardButtonRow(
                            buttons=[KeyboardButtonWebView(
                                text=t("bot_cmd.webapp_button"),
                                url=webapp_url,
                            )]
                        )
                    ]
                )
                await event.reply(
                    t("bot_cmd.welcome"),
                    parse_mode='md',
                    buttons=buttons,
                )
            else:
                await event.reply(t("bot_cmd.welcome"), parse_mode='md')

        @self.client.on(events.NewMessage(pattern=r'^/status\b'))
        async def handle_status(event):
            if not self._check_permission(event):
                await event.reply(t("bot_cmd.no_permission"))
                return
            await self._run_account_command(event, self._handle_status)

        @self.client.on(events.NewMessage(pattern=r'^/bot\b'))
        async def handle_bot(event):
            if not self._check_permission(event):
                await event.reply(t("bot_cmd.no_permission"))
                return
            await self._run_account_command(event, self._handle_bot_cmd)

        @self.client.on(events.NewMessage(pattern=r'^/rule\b'))
        async def handle_rule(event):
            if not self._check_permission(event):
                await event.reply(t("bot_cmd.no_permission"))
                return
            await self._run_account_command(event, self._handle_rule_cmd)

        @self.client.on(events.NewMessage(pattern=r'^/webapp\b'))
        async def handle_webapp(event):
            if not self._check_permission(event):
                await event.reply(t("bot_cmd.no_permission"))
                return
            await self._handle_webapp(event)

        @self.client.on(events.NewMessage(pattern=r'^/stats\b'))
        async def handle_stats(event):
            if not self._check_permission(event):
                await event.reply(t("bot_cmd.no_permission"))
                return
            await self._run_account_command(event, self._handle_stats_cmd)

        @self.client.on(events.NewMessage(pattern=r'^/history\b'))
        async def handle_history(event):
            if not self._check_permission(event):
                await event.reply(t("bot_cmd.no_permission"))
                return
            await self._run_account_command(event, self._handle_history_cmd)

        @self.client.on(events.NewMessage(pattern=r'^/config\b'))
        async def handle_config(event):
            if not self._check_permission(event):
                await event.reply(t("bot_cmd.no_permission"))
                return
            await self._run_account_command(event, self._handle_config_cmd)

    def _check_permission(self, event) -> bool:
        """Check if the sender is the authorized admin"""
        return event.sender_id == self.config.admin_chat_id

    def _parse_args(self, text: str, command: str) -> List[str]:
        """Parse command arguments using shlex (handles quoted strings)"""
        # Strip command prefix
        rest = text[len(command):].strip()
        if not rest:
            return []
        try:
            # Use shlex.split to handle "quoted strings"
            return shlex.split(rest)
        except ValueError:
            # Fallback to simple split if shlex fails
            return rest.split()

    # -- Status --

    async def _handle_status(self, event) -> None:
        """Handle /status command"""
        status = self._active_status()
        stats = status.get("stats", {})

        running_icon = "🟢" if status["is_running"] else "⚫"
        connected_icon = "🟢" if status["is_connected"] else "⚫"

        rules = self._active_config().get_forwarding_rules()
        enabled_count = sum(1 for r in rules if r.enabled)

        msg = t("bot_cmd.status_msg",
                running_icon=running_icon,
                running=t("bot_cmd.yes") if status["is_running"] else t("bot_cmd.no"),
                connected_icon=connected_icon,
                connected=t("bot_cmd.yes") if status["is_connected"] else t("bot_cmd.no"),
                forwarded=stats.get("forwarded", 0),
                filtered=stats.get("filtered", 0),
                total=stats.get("total", 0),
                enabled=enabled_count,
                rule_total=len(rules))

        await event.reply(msg, parse_mode='md')

    # -- Bot control --

    async def _handle_bot_cmd(self, event) -> None:
        """Handle /bot <start|stop|restart> commands"""
        args = self._parse_args(event.raw_text, "/bot")

        if not args:
            await event.reply(t("bot_cmd.bot_usage"), parse_mode='md')
            return

        subcmd = args[0].lower()
        runtime = self._active_runtime()
        config = self._active_config()

        if subcmd == "start":
            if runtime.is_running:
                await event.reply(t("bot_cmd.bot_already_running"))
                return
            # Reload config before starting
            config.load()
            success = await self._control_runtime("start")
            if success:
                await event.reply(t("bot_cmd.bot_started"))
            else:
                await event.reply(t("bot_cmd.bot_start_failed"))

        elif subcmd == "stop":
            if not runtime.is_running:
                await event.reply(t("bot_cmd.bot_not_running"))
                return
            success = await self._control_runtime("stop")
            if success:
                await event.reply(t("bot_cmd.bot_stopped"))
            else:
                await event.reply(t("bot_cmd.bot_stop_failed"))

        elif subcmd == "restart":
            await event.reply(t("bot_cmd.bot_restarting"))
            config.load()
            success = await self._control_runtime("restart")
            if success:
                await event.reply(t("bot_cmd.bot_restarted"))
            else:
                await event.reply(t("bot_cmd.bot_restart_failed"))

        else:
            await event.reply(t("bot_cmd.bot_usage"), parse_mode='md')

    # -- Rules --

    async def _handle_rule_cmd(self, event) -> None:
        """Handle /rule <subcommand> commands"""
        args = self._parse_args(event.raw_text, "/rule")

        if not args:
            await event.reply(t("bot_cmd.rule_usage"), parse_mode='md')
            return

        subcmd = args[0].lower()
        sub_args = args[1:]

        if subcmd == "list":
            await self._rule_list(event)
        elif subcmd == "detail":
            await self._rule_detail(event, sub_args)
        elif subcmd == "add":
            await self._rule_add(event, sub_args)
        elif subcmd == "del":
            await self._rule_del(event, sub_args)
        elif subcmd == "rename":
            await self._rule_rename(event, sub_args)
        elif subcmd == "toggle":
            await self._rule_toggle(event, sub_args)
        elif subcmd == "set":
            await self._rule_set(event, sub_args)
        else:
            await event.reply(t("bot_cmd.rule_usage"), parse_mode='md')

    async def _rule_list(self, event) -> None:
        """List all forwarding rules"""
        rules = self._active_config().get_forwarding_rules()
        if not rules:
            await event.reply(t("bot_cmd.no_rules"))
            return

        lines = []
        for i, rule in enumerate(rules):
            icon = "✅" if rule.enabled else "⬜"
            src_count = len(rule.source_chats)
            tgt_count = len(rule.target_chats)
            lines.append(f"{icon} **{rule.name}** ({src_count} → {tgt_count})")

        msg = t("bot_cmd.rules_header") + "\n" + "\n".join(lines)
        await event.reply(msg, parse_mode='md')

    async def _rule_detail(self, event, args: List[str]) -> None:
        """Show rule details"""
        if not args:
            await event.reply(t("bot_cmd.rule_name_required"))
            return

        rule_name = args[0]
        rule = self._find_rule(rule_name)
        if not rule:
            await event.reply(t("bot_cmd.rule_not_found", name=rule_name))
            return

        # Build detail message
        status = "✅ " + t("bot_cmd.enabled") if rule.enabled else "⬜ " + t("bot_cmd.disabled")
        sources = "\n".join(f"  `{s}`" for s in rule.source_chats) or "  -"
        targets = "\n".join(f"  `{t_}`" for t_ in rule.target_chats) or "  -"
        keywords = ", ".join(rule.filter_keywords) or "-"
        regex = ", ".join(rule.filter_regex_patterns) or "-"
        media_types = ", ".join(rule.filter_media_types) if rule.filter_media_types else t("misc.all_media_types")
        max_size = f"{rule.filter_max_file_size / 1048576:.1f} MB" if rule.filter_max_file_size else t("misc.unlimited")
        min_size = f"{rule.filter_min_file_size / 1048576:.1f} MB" if rule.filter_min_file_size else "0"
        ignored_users = ", ".join(str(u) for u in rule.ignored_user_ids) or "-"
        ignored_kw = ", ".join(rule.ignored_keywords) or "-"

        msg = t("bot_cmd.rule_detail_msg",
                name=rule.name,
                status=status,
                mode=rule.filter_mode,
                sources=sources,
                targets=targets,
                keywords=keywords,
                regex=regex,
                media_types=media_types,
                file_size=f"{min_size} ~ {max_size}",
                delay=rule.delay,
                preserve_format=rule.preserve_format,
                add_source_info=rule.add_source_info,
                force_forward=rule.force_forward,
                hide_sender=rule.hide_sender,
                ignored_users=ignored_users,
                ignored_keywords=ignored_kw)

        await event.reply(msg, parse_mode='md')

    async def _rule_add(self, event, args: List[str]) -> None:
        """Add a new forwarding rule"""
        if not args:
            await event.reply(t("bot_cmd.rule_name_required"))
            return

        rule_name = args[0]

        # Check duplicate
        if self._find_rule(rule_name):
            await event.reply(t("bot_cmd.rule_exists", name=rule_name))
            return

        # Create new rule with defaults
        new_rule = ForwardingRule(name=rule_name, enabled=False)

        # Add to config
        rules = self._active_config().get_forwarding_rules()
        rules.append(new_rule)
        self._save_rules(rules)

        await event.reply(t("bot_cmd.rule_added", name=rule_name))

    async def _rule_del(self, event, args: List[str]) -> None:
        """Delete a forwarding rule"""
        if not args:
            await event.reply(t("bot_cmd.rule_name_required"))
            return

        rule_name = args[0]
        rules = self._active_config().get_forwarding_rules()

        # Find the rule
        idx = None
        for i, r in enumerate(rules):
            if r.name == rule_name:
                idx = i
                break

        if idx is None:
            await event.reply(t("bot_cmd.rule_not_found", name=rule_name))
            return

        if len(rules) <= 1:
            await event.reply(t("bot_cmd.rule_delete_last"))
            return

        rules.pop(idx)
        self._save_rules(rules)

        # Delete stats from DB
        self._active_stats().delete_rule(rule_name)

        await event.reply(t("bot_cmd.rule_deleted", name=rule_name))

    async def _rule_rename(self, event, args: List[str]) -> None:
        """Rename a forwarding rule: /rule rename "old_name" "new_name" """
        if len(args) < 2:
            await event.reply(t("bot_cmd.rule_rename_usage"))
            return

        old_name = args[0]
        new_name = args[1]

        if not new_name.strip():
            await event.reply(t("bot_cmd.rule_name_empty"))
            return

        rules = self._active_config().get_forwarding_rules()

        # Find the rule to rename
        rule = None
        for r in rules:
            if r.name == old_name:
                rule = r
                break

        if not rule:
            await event.reply(t("bot_cmd.rule_not_found", name=old_name))
            return

        # Check duplicate
        if self._find_rule(new_name):
            await event.reply(t("bot_cmd.rule_exists", name=new_name))
            return

        rule.name = new_name
        self._save_rules(rules)

        # Also rename in stats DB
        self._active_stats().rename_rule(old_name, new_name)

        await event.reply(t("bot_cmd.rule_renamed", old_name=old_name, new_name=new_name))

    async def _rule_toggle(self, event, args: List[str]) -> None:
        """Toggle rule enabled/disabled"""
        if not args:
            await event.reply(t("bot_cmd.rule_name_required"))
            return

        rule_name = args[0]
        rules = self._active_config().get_forwarding_rules()

        for rule in rules:
            if rule.name == rule_name:
                rule.enabled = not rule.enabled
                self._save_rules(rules)
                status = t("bot_cmd.enabled") if rule.enabled else t("bot_cmd.disabled")
                await event.reply(t("bot_cmd.rule_toggled", name=rule_name, status=status))
                return

        await event.reply(t("bot_cmd.rule_not_found", name=rule_name))

    @staticmethod
    def _is_clear(value: str) -> bool:
        """Check if value means 'clear this field'"""
        return value.lower() in ('clear', '""', "''", 'none', 'empty')

    @staticmethod
    def _parse_list(value: str) -> list:
        """Parse comma-separated list, returns empty list if cleared"""
        return [k.strip() for k in value.split(",") if k.strip()]

    async def _rule_set(self, event, args: List[str]) -> None:
        """Set a rule attribute: /rule set "rule_name" <field> <value>"""
        if len(args) < 3:
            await event.reply(t("bot_cmd.rule_set_usage"), parse_mode='md')
            return

        rule_name = args[0]
        field = args[1].lower()
        value = args[2]

        rules = self._active_config().get_forwarding_rules()

        rule = None
        for r in rules:
            if r.name == rule_name:
                rule = r
                break

        if not rule:
            await event.reply(t("bot_cmd.rule_not_found", name=rule_name))
            return

        try:
            if field == "source":
                rule.source_chats = [] if self._is_clear(value) else self._parse_chat_ids(value)
            elif field == "target":
                rule.target_chats = [] if self._is_clear(value) else self._parse_chat_ids(value)
            elif field == "keywords":
                rule.filter_keywords = [] if self._is_clear(value) else self._parse_list(value)
            elif field == "regex":
                rule.filter_regex_patterns = [] if self._is_clear(value) else self._parse_list(value)
            elif field == "mode":
                if value not in ("whitelist", "blacklist"):
                    await event.reply(t("bot_cmd.invalid_mode"))
                    return
                rule.filter_mode = value
            elif field == "delay":
                rule.delay = float(value)
            elif field == "force_forward":
                rule.force_forward = value.lower() in ("true", "1", "yes", "on")
            elif field == "hide_sender":
                rule.hide_sender = value.lower() in ("true", "1", "yes", "on")
            elif field == "add_source_info":
                rule.add_source_info = value.lower() in ("true", "1", "yes", "on")
            elif field == "preserve_format":
                rule.preserve_format = value.lower() in ("true", "1", "yes", "on")
            elif field == "ignore_users":
                rule.ignored_user_ids = [] if self._is_clear(value) else [int(x.strip()) for x in value.split(",") if x.strip()]
            elif field == "ignore_keywords":
                rule.ignored_keywords = [] if self._is_clear(value) else self._parse_list(value)
            elif field == "media_types":
                if self._is_clear(value):
                    rule.filter_media_types = []
                else:
                    from backend.filters import MEDIA_TYPES
                    types = self._parse_list(value)
                    invalid = [t_ for t_ in types if t_ not in MEDIA_TYPES]
                    if invalid:
                        await event.reply(t("bot_cmd.invalid_media_types",
                                            types=", ".join(invalid),
                                            valid=", ".join(MEDIA_TYPES)))
                        return
                    rule.filter_media_types = types
            elif field == "max_file_size":
                rule.filter_max_file_size = int(float(value) * 1048576)  # MB -> bytes
            elif field == "min_file_size":
                rule.filter_min_file_size = int(float(value) * 1048576)  # MB -> bytes
            else:
                await event.reply(t("bot_cmd.unknown_field", field=field))
                return

            self._save_rules(rules)
            await event.reply(t("bot_cmd.rule_updated", name=rule_name, field=field, value=value))

        except Exception as e:
            await event.reply(t("bot_cmd.rule_set_error", error=str(e)))

    # -- Stats --

    async def _handle_stats_cmd(self, event) -> None:
        """Handle /stats <subcommand> commands"""
        args = self._parse_args(event.raw_text, "/stats")

        if not args:
            await event.reply(t("bot_cmd.stats_usage"), parse_mode='md')
            return

        subcmd = args[0].lower()

        if subcmd == "reset":
            account_id = self._command_account_id.get()
            if account_id and self.context and self.context.accounts:
                await self._control_sync(lambda: self.bot_manager.reset_stats(account_id))
            else:
                await self._control_sync(self.bot_manager.reset_stats)
            await event.reply(t("bot_cmd.stats_reset_done"))
        else:
            await event.reply(t("bot_cmd.stats_usage"), parse_mode='md')

    # -- History --

    async def _handle_history_cmd(self, event) -> None:
        """Handle /history [rule_name] [N] - show recent N forwarding history"""
        args = self._parse_args(event.raw_text, "/history")

        rule_name = None
        limit = 10

        for arg in args:
            if arg.isdigit():
                limit = min(int(arg), 50)  # max 50
            else:
                rule_name = arg

        rows, total = self._active_stats().query_history(
            rule_name=rule_name, limit=limit, offset=0
        )

        if not rows:
            await event.reply(t("bot_cmd.history_empty"))
            return

        lines = [t("bot_cmd.history_header", count=len(rows), total=total)]
        for r in rows:
            time_str = r.get("forwarded_at", "")[:16]  # trim seconds
            source = r.get("source_chat_name", "?")
            preview = (r.get("content", "") or "[media]")[:80]
            lines.append(f"  `{time_str}` [{source}] {preview}")

        await event.reply("\n".join(lines), parse_mode='md')

    # -- Config --

    async def _handle_config_cmd(self, event) -> None:
        """Handle /config <export|import> commands"""
        args = self._parse_args(event.raw_text, "/config")

        if not args:
            await event.reply(t("bot_cmd.config_usage"), parse_mode='md')
            return

        subcmd = args[0].lower()
        config = self._active_config()

        if subcmd == "export":
            config_path = config.config_file
            if os.path.exists(config_path):
                await event.reply(
                    file=config_path,
                    message=t("bot_cmd.config_exported")
                )
            else:
                await event.reply(t("bot_cmd.config_not_found"))

        elif subcmd == "import":
            # Must reply to a file
            reply_msg = await event.get_reply_message()
            if not reply_msg or not reply_msg.file:
                await event.reply(t("bot_cmd.config_import_usage"))
                return

            tmp_path = None
            try:
                # Download the file
                file_descriptor, tmp_path = tempfile.mkstemp(
                    prefix="telerelay-config-import-",
                    suffix=".yaml",
                )
                os.close(file_descriptor)
                await reply_msg.download_media(file=tmp_path)

                # Validate YAML
                with open(tmp_path, "r", encoding="utf-8") as f:
                    new_config = yaml.safe_load(f)

                if not isinstance(new_config, dict) or (
                    "forwarding_rules" not in new_config and "source_chats" not in new_config
                ):
                    await event.reply(t("bot_cmd.config_invalid_file"))
                    return

                # Backup and replace
                config_path = config.config_file
                if os.path.exists(config_path):
                    shutil.copy2(config_path, config_path + ".bak")

                scope = self._account_scope()
                if scope:
                    config = self.context.account_registry.replace_config(
                        scope.account_id,
                        new_config,
                    )
                else:
                    shutil.copy2(tmp_path, config_path)
                    config.load()

                if self._active_runtime().is_running:
                    await self._control_runtime("restart")
                    await event.reply(t("bot_cmd.config_imported_restarted"))
                else:
                    await event.reply(t("bot_cmd.config_imported"))

            except Exception as e:
                await event.reply(t("bot_cmd.config_import_error", error=str(e)))
            finally:
                if tmp_path:
                    Path(tmp_path).unlink(missing_ok=True)

        else:
            await event.reply(t("bot_cmd.config_usage"), parse_mode='md')

    # -- Mini App --

    async def _handle_webapp(self, event) -> None:
        """Handle /webapp command - send a button to open WebUI Mini App"""
        webapp_url = self.config.webapp_url
        if not webapp_url:
            await event.reply(t("bot_cmd.webapp_not_configured"))
            return

        try:
            buttons = ReplyInlineMarkup(
                rows=[
                    KeyboardButtonRow(
                        buttons=[KeyboardButtonWebView(
                            text=t("bot_cmd.webapp_button"),
                            url=webapp_url,
                        )]
                    )
                ]
            )
            await event.reply(
                t("bot_cmd.webapp_open"),
                parse_mode='md',
                buttons=buttons,
            )
        except Exception as e:
            logger.error(t("log.admin_bot.webapp_failed", error=str(e)))
            await event.reply(t("bot_cmd.webapp_url_invalid", error=str(e)))

    async def _set_menu_button(self) -> None:
        """Set Bot menu button to open WebUI Mini App"""
        webapp_url = self.config.webapp_url
        if not webapp_url:
            return

        try:
            await self.client(
                SetBotMenuButtonRequest(
                    user_id=self.config.admin_chat_id,
                    button=BotMenuButton(
                        text="Open",
                        url=webapp_url,
                    ),
                )
            )
            logger.debug(t("log.admin_bot.menu_button_set"))
        except Exception as e:
            logger.warning(t("log.admin_bot.menu_button_failed", error=str(e)))

    # -- Helpers --

    def _find_rule(self, name: str) -> Optional[ForwardingRule]:
        """Find a rule by name"""
        for rule in self._active_config().get_forwarding_rules():
            if rule.name == name:
                return rule
        return None

    def _save_rules(self, rules: List[ForwardingRule]) -> None:
        """Save rules to config file"""
        rules_data = save_rules_to_config(rules)
        config = self._active_config()
        config.config_data.update(rules_data)
        config.save()

    @staticmethod
    def _parse_chat_ids(value: str) -> list:
        """Parse comma-separated chat IDs (support both int and string usernames)"""
        result = []
        for item in value.split(","):
            item = item.strip()
            if not item:
                continue
            try:
                result.append(int(item))
            except ValueError:
                # Could be a username like @channel
                result.append(item)
        return result
