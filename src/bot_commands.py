"""
Admin Bot Module
Provides Telegram Bot command interface for managing forwarding rules and bot lifecycle.
Uses a separate Bot instance from the main forwarding system.
"""
import asyncio
import shlex
import threading
from typing import Optional, List
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
from src.config import Config
from src.logger import get_logger
from src.rule import ForwardingRule, save_rules_to_config
from src.i18n import t

logger = get_logger()


class AdminBotManager:
    """Admin Bot Manager - manages configuration and rules via Telegram commands"""

    def __init__(self, config: Config, bot_manager):
        """
        Initialize Admin Bot Manager

        Args:
            config: Configuration object
            bot_manager: BotManager instance for controlling the forwarding service
        """
        self.config = config
        self.bot_manager = bot_manager
        self.client: Optional[TelegramClient] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None

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
        from pathlib import Path
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

        # Set Menu Button to Mini App if webapp_url is configured
        await self._set_menu_button()

        await self.client.run_until_disconnected()

    def _register_handlers(self) -> None:
        """Register all command handlers"""

        @self.client.on(events.NewMessage(pattern=r'^/start\b'))
        async def handle_start(event):
            if not self._check_permission(event):
                await event.reply(t("bot_cmd.no_permission"))
                return
            # Send welcome message with Mini App button if configured
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
            await self._handle_status(event)

        @self.client.on(events.NewMessage(pattern=r'^/bot\b'))
        async def handle_bot(event):
            if not self._check_permission(event):
                await event.reply(t("bot_cmd.no_permission"))
                return
            await self._handle_bot_cmd(event)

        @self.client.on(events.NewMessage(pattern=r'^/rule\b'))
        async def handle_rule(event):
            if not self._check_permission(event):
                await event.reply(t("bot_cmd.no_permission"))
                return
            await self._handle_rule_cmd(event)

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
            await self._handle_stats_cmd(event)

    def _check_permission(self, event) -> bool:
        """Check if the sender is the authorized admin"""
        return event.sender_id == self.config.admin_chat_id

    def _parse_args(self, text: str, command: str) -> List[str]:
        """Parse command arguments using shlex (handles quoted strings)"""
        # Remove the command prefix (e.g., "/bot " or "/rule ")
        rest = text[len(command):].strip()
        if not rest:
            return []
        try:
            # Use shlex.split to handle "quoted strings"
            return shlex.split(rest)
        except ValueError:
            # Fallback to simple split if shlex fails
            return rest.split()

    # ===== Status Command =====

    async def _handle_status(self, event) -> None:
        """Handle /status command"""
        status = self.bot_manager.get_status()
        stats = status.get("stats", {})

        running_icon = "🟢" if status["is_running"] else "⚫"
        connected_icon = "🟢" if status["is_connected"] else "⚫"

        rules = self.config.get_forwarding_rules()
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

    # ===== Bot Control Commands =====

    async def _handle_bot_cmd(self, event) -> None:
        """Handle /bot <start|stop|restart> commands"""
        args = self._parse_args(event.raw_text, "/bot")

        if not args:
            await event.reply(t("bot_cmd.bot_usage"), parse_mode='md')
            return

        subcmd = args[0].lower()

        if subcmd == "start":
            if self.bot_manager.is_running:
                await event.reply(t("bot_cmd.bot_already_running"))
                return
            # Reload config before starting
            self.config.load()
            success = self.bot_manager.start()
            if success:
                await event.reply(t("bot_cmd.bot_started"))
            else:
                await event.reply(t("bot_cmd.bot_start_failed"))

        elif subcmd == "stop":
            if not self.bot_manager.is_running:
                await event.reply(t("bot_cmd.bot_not_running"))
                return
            success = self.bot_manager.stop()
            if success:
                await event.reply(t("bot_cmd.bot_stopped"))
            else:
                await event.reply(t("bot_cmd.bot_stop_failed"))

        elif subcmd == "restart":
            await event.reply(t("bot_cmd.bot_restarting"))
            self.config.load()
            success = self.bot_manager.restart()
            if success:
                await event.reply(t("bot_cmd.bot_restarted"))
            else:
                await event.reply(t("bot_cmd.bot_restart_failed"))

        else:
            await event.reply(t("bot_cmd.bot_usage"), parse_mode='md')

    # ===== Rule Commands =====

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
        rules = self.config.get_forwarding_rules()
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

        # Check if rule with this name already exists
        if self._find_rule(rule_name):
            await event.reply(t("bot_cmd.rule_exists", name=rule_name))
            return

        # Create new rule with defaults
        new_rule = ForwardingRule(name=rule_name, enabled=False)

        # Add to config
        rules = self.config.get_forwarding_rules()
        rules.append(new_rule)
        self._save_rules(rules)

        await event.reply(t("bot_cmd.rule_added", name=rule_name))

    async def _rule_del(self, event, args: List[str]) -> None:
        """Delete a forwarding rule"""
        if not args:
            await event.reply(t("bot_cmd.rule_name_required"))
            return

        rule_name = args[0]
        rules = self.config.get_forwarding_rules()

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
        from src.stats_db import get_stats_db
        get_stats_db().delete_rule(rule_name)

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

        rules = self.config.get_forwarding_rules()

        # Find the rule to rename
        rule = None
        for r in rules:
            if r.name == old_name:
                rule = r
                break

        if not rule:
            await event.reply(t("bot_cmd.rule_not_found", name=old_name))
            return

        # Check if new name already exists
        if self._find_rule(new_name):
            await event.reply(t("bot_cmd.rule_exists", name=new_name))
            return

        rule.name = new_name
        self._save_rules(rules)

        # Also rename in stats DB
        from src.stats_db import get_stats_db
        get_stats_db().rename_rule(old_name, new_name)

        await event.reply(t("bot_cmd.rule_renamed", old_name=old_name, new_name=new_name))

    async def _rule_toggle(self, event, args: List[str]) -> None:
        """Toggle rule enabled/disabled"""
        if not args:
            await event.reply(t("bot_cmd.rule_name_required"))
            return

        rule_name = args[0]
        rules = self.config.get_forwarding_rules()

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

        rules = self.config.get_forwarding_rules()

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
                    from src.filters import MEDIA_TYPES
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

    # ===== Stats Command =====

    async def _handle_stats_cmd(self, event) -> None:
        """Handle /stats <subcommand> commands"""
        args = self._parse_args(event.raw_text, "/stats")

        if not args:
            await event.reply(t("bot_cmd.stats_usage"), parse_mode='md')
            return

        subcmd = args[0].lower()

        if subcmd == "reset":
            self.bot_manager.reset_stats()
            await event.reply(t("bot_cmd.stats_reset_done"))
        else:
            await event.reply(t("bot_cmd.stats_usage"), parse_mode='md')

    # ===== Mini App Methods =====

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
            logger.error(f"Failed to send WebApp button: {e}")
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
            logger.info(t("log.admin_bot.menu_button_set"))
        except Exception as e:
            logger.warning(t("log.admin_bot.menu_button_failed", error=str(e)))

    # ===== Helper Methods =====

    def _find_rule(self, name: str) -> Optional[ForwardingRule]:
        """Find a rule by name"""
        for rule in self.config.get_forwarding_rules():
            if rule.name == name:
                return rule
        return None

    def _save_rules(self, rules: List[ForwardingRule]) -> None:
        """Save rules to config file"""
        rules_data = save_rules_to_config(rules)
        self.config.config_data.update(rules_data)
        self.config.save()

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
