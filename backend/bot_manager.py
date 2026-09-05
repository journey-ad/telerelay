"""
Bot Lifecycle Management Module
Manages the startup, shutdown, and restart of Telegram Bot
"""
import asyncio
import threading
from concurrent.futures import Future
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional

from backend.button_actions import ButtonActionEngine
from backend.client import TelegramClientManager
from backend.config import Config
from backend.constants import (
    BOT_RESTART_DELAY,
    BOT_STOP_TIMEOUT,
)
from backend.filters import MessageFilter, get_file_size, get_media_type
from backend.forward_queue import (
    ForwardQueue,
    ForwardQueueItem,
    ForwardQueueStore,
    rule_fingerprint,
)
from backend.forwarder import MessageForwarder
from backend.i18n import t
from backend.logger import account_log_context, get_logger
from backend.rule import ForwardingRule
from backend.stats_db import get_stats_db
from backend.subscriptions import SubscriberStore

if TYPE_CHECKING:
    from backend.auth_manager import AuthManager

logger = get_logger()


class BotManager:
    """Bot Lifecycle Manager"""

    def __init__(
        self,
        config: Config,
        auth_manager: Optional['AuthManager'] = None,
        session_name: str | Path | None = None,
        queue_db_path: str | Path | None = None,
        account_id: str | None = None,
        events: Any = None,
        stats_db=None,
        bot_token: str | None = None,
        session_type: str = "user",
        subscriber_store: Any = None,
    ):
        """Initialize Bot Manager

        Args:
            config: Configuration object
            auth_manager: Authentication manager (for User mode authentication)
        """
        self.config = config
        self.auth_manager = auth_manager
        self.bot_token = bot_token
        self.session_type = session_type
        self.session_name = Path(session_name) if session_name else Path("data/telegram_session")
        self.queue_db_path = Path(queue_db_path) if queue_db_path else None
        self.account_id = account_id
        self.events = events
        self.stats_db = stats_db or get_stats_db()
        self.subscriber_store = subscriber_store
        self.on_user_authenticated: Callable[[dict[str, Any]], None] | None = None
        self.client_manager: Optional[TelegramClientManager] = None
        self.forwarder: Optional[MessageForwarder] = None
        self.forwarders = []
        self.rule_forwarder_map = {}
        self._queue_forwarders = {}
        self._target_label_cache: dict[str, str] = {}
        self._forwarding_handler = None
        self._button_handler = None
        self._chat_recorder_handler = None
        self._command_handler = None
        self.chat_recorder: Callable[[str, Any], None] | None = None
        self.button_action_engine: Optional[ButtonActionEngine] = None
        self.forward_queue_store: Optional[ForwardQueueStore] = None
        self.forward_queue: Optional[ForwardQueue] = None
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        # Thread-safe state management
        self._lock = threading.RLock()
        self._is_running = False
        self._is_connected = False
        self.loop: Optional[asyncio.AbstractEventLoop] = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Bind lifecycle operations to FastAPI's owning event loop."""
        self.loop = loop

    @property
    def is_running(self) -> bool:
        """Thread-safe is_running access"""
        with self._lock:
            return self._is_running

    @is_running.setter
    def is_running(self, value: bool):
        """Thread-safe is_running setter"""
        with self._lock:
            self._is_running = value

    @property
    def is_connected(self) -> bool:
        """Thread-safe is_connected access"""
        with self._lock:
            return self._is_connected

    @is_connected.setter
    def is_connected(self, value: bool):
        """Thread-safe is_connected setter"""
        with self._lock:
            self._is_connected = value
    
    async def start(self) -> bool:
        with account_log_context(self.account_id):
            return await self._start()

    async def _start(self) -> bool:
        """Start the Telegram runtime on the current asyncio event loop."""
        with self._lock:
            if self._is_running or (self._task and not self._task.done()):
                logger.warning(t("log.bot.already_running"))
                return False
            self.loop = asyncio.get_running_loop()
            self._stop_event = asyncio.Event()
            self._is_running = True
            self._task = self.loop.create_task(
                self._bot_main(),
                name=f"telerelay-telegram-runtime-{self.account_id or 'primary'}",
            )
        await asyncio.sleep(0)
        return True

    async def wait(self) -> None:
        """Wait until the active Telegram runtime exits."""
        task = self._task
        if task:
            await task

    async def refresh_identity(self) -> dict[str, Any]:
        """Refresh account metadata and avatar for either user or bot runtimes."""
        with account_log_context(self.account_id):
            with self._lock:
                connected = self._is_connected
                client_manager = self.client_manager
            if not connected or client_manager is None:
                raise RuntimeError(t("message.export.telegram_not_connected"))
            return await client_manager.refresh_identity()

    async def _bot_main(self) -> None:
        """Run the Telegram client and durable forwarding queue."""
        if not self.is_running:
            logger.warning(t("log.bot.already_running"))
            return
        try:
            # Running
            self.is_running = True

            # Validate config
            is_valid, error_msg = self.config.validate_connection(bot_token=self.bot_token)
            if not is_valid:
                logger.error(t("log.bot.config_validation_failed", error=error_msg))
                return

            # Init client
            self.client_manager = TelegramClientManager(
                self.config,
                self.auth_manager,
                session_name=self.session_name,
                on_user_authenticated=self.on_user_authenticated,
                bot_token=self.bot_token,
            )

            # Connect
            if not await self.client_manager.connect():
                logger.error(t("log.bot.connect_failed"))
                return

            # Connected
            self.is_connected = True
            self._publish_event(
                "telegram-account",
                {
                    "action": "connection",
                    "account_id": self.account_id,
                    "connected": True,
                    "running": True,
                },
            )
            self.forwarders = []
            self.rule_forwarder_map = {}
            self._queue_forwarders = {}
            self._target_label_cache = {}
            self._forwarding_handler = None
            self._button_handler = None

            # Start queue before accepting updates; pending jobs use stored rule snapshots.
            self.forward_queue_store = ForwardQueueStore(
                self.queue_db_path or self.config.forward_queue_db_path
            )
            self.forward_queue = ForwardQueue(
                self.forward_queue_store,
                self._process_queue_item,
                max_retries=self.config.forward_queue_max_retries,
                retry_base_seconds=self.config.forward_queue_retry_base_seconds,
                flood_wait_buffer=self.config.forward_queue_flood_wait_buffer,
                poll_interval=self.config.forward_queue_poll_interval,
                completed_retention_days=self.config.forward_queue_completed_retention_days,
                on_outcome=self._queue_outcome,
            )
            await self.forward_queue.start()

            await self.reload_rules()

            if self.session_type == "bot":
                await self._set_bot_commands()

            logger.info(t("log.bot.started", count=len(self.forwarders)))

            # Run until stop signal received
            await self._stop_event.wait()

        except Exception as e:
            logger.error(t("log.bot.main_error", error=str(e)), exc_info=True)
        finally:
            self.is_connected = False
            if self.forward_queue:
                await self.forward_queue.stop(timeout=max(1, BOT_STOP_TIMEOUT - 2))
            if self.client_manager:
                await self.client_manager.disconnect()
            self.is_running = False
            self._publish_event(
                "telegram-account",
                {
                    "action": "connection",
                    "account_id": self.account_id,
                    "connected": False,
                    "running": False,
                },
            )
            logger.info(t("log.bot.stopped"))

    def _create_forwarder(self, rule: ForwardingRule) -> tuple[MessageFilter, MessageForwarder]:
        """Build forwarding dependencies for either a live or snapshotted rule."""
        message_filter = MessageFilter(
            rule_name=rule.name,
            regex_patterns=rule.filter_regex_patterns,
            keywords=rule.filter_keywords,
            mode=rule.filter_mode,
            ignored_user_ids=rule.ignored_user_ids,
            ignored_keywords=rule.ignored_keywords,
            media_types=rule.filter_media_types,
            max_file_size=rule.filter_max_file_size,
            min_file_size=rule.filter_min_file_size,
        )
        forwarder = MessageForwarder(
            client=self.client_manager.get_client(),
            rule=rule,
            message_filter=message_filter,
            bot_manager=self,
            target_label_cache=self._target_label_cache,
            stats_db=self.stats_db,
            suppressed_check=(
                self._is_target_suppressed if self.session_type == "bot" else None
            ),
            delivered_callback=(
                self._record_target_delivery if self.session_type == "bot" else None
            ),
        )
        return message_filter, forwarder

    async def reload_rules(self) -> bool:
        with account_log_context(self.account_id):
            return await self._reload_rules()

    async def _reload_rules(self) -> bool:
        """Replace live rule state and handlers without reconnecting Telegram."""
        if not self.is_connected or not self.client_manager:
            return False

        rules = self.config.get_enabled_rules()
        forwarders = []
        rule_forwarder_map = {}
        queue_forwarders = {}
        forwarding_chats = []
        seen_forwarding_chats = set()
        for rule in rules:
            message_filter, forwarder = self._create_forwarder(rule)
            forwarders.append(forwarder)
            rule_forwarder_map[rule.name] = (rule, message_filter, forwarder)
            queue_forwarders[rule_fingerprint(rule.to_dict())] = forwarder
            for chat in rule.source_chats:
                if chat not in seen_forwarding_chats:
                    seen_forwarding_chats.add(chat)
                    forwarding_chats.append(chat)
            logger.debug(
                t("log.bot.rule_registered", rule=rule.name, count=len(rule.source_chats))
            )

        button_action_engine = None
        button_source_chats = []
        button_action_rules = self.config.get_enabled_button_action_rules()
        session_type = self.session_type
        if button_action_rules and session_type != "user":
            logger.warning(t("log.button_action.user_mode_required"))
        elif button_action_rules:
            valid_button_rules = [
                rule
                for rule in button_action_rules
                if rule.source_chats and rule.button_texts
            ]
            if valid_button_rules:
                button_action_engine = ButtonActionEngine(valid_button_rules)
                button_source_chats = list(
                    dict.fromkeys(
                        chat
                        for rule in valid_button_rules
                        for chat in rule.source_chats
                    )
                )

        self.forwarders = forwarders
        self.rule_forwarder_map = rule_forwarder_map
        self._queue_forwarders.update(queue_forwarders)
        self.forwarder = forwarders[0] if forwarders else None
        self.button_action_engine = button_action_engine

        self.client_manager.remove_message_handler(self._forwarding_handler)
        self.client_manager.remove_message_handler(self._button_handler)
        self.client_manager.remove_message_handler(self._chat_recorder_handler)
        self.client_manager.remove_message_handler(self._command_handler)
        self._forwarding_handler = None
        self._button_handler = None
        self._chat_recorder_handler = None
        self._command_handler = None
        if forwarding_chats:
            self._forwarding_handler = self.client_manager.add_message_handler(
                callback=self._central_message_handler,
                chats=forwarding_chats,
            )
        if session_type == "bot":
            self._chat_recorder_handler = self.client_manager.add_message_handler(
                callback=self._record_chat_entity,
            )
        if session_type == "bot" and getattr(self.config, "bot_commands_enabled", True):
            self._command_handler = self.client_manager.add_message_handler(
                callback=self._bot_command_handler,
                incoming=True,
            )
        if button_action_engine:
            self._button_handler = self.client_manager.add_message_handler(
                callback=self._button_action_handler,
                chats=button_source_chats,
                incoming=True,
            )
            logger.debug(
                t(
                    "log.button_action.registered",
                    rules=len(button_action_engine.rules),
                    chats=len(button_source_chats),
                )
            )
        return True

    async def _record_chat_entity(self, event) -> None:
        """Persist the chat behind an update so bot pickers can list it."""
        recorder = self.chat_recorder
        if recorder is None:
            return
        chat = getattr(event, "chat", None)
        if chat is None:
            chat = getattr(getattr(event, "message", None), "chat", None)
        if chat is None:
            logger.debug(
                "消息事件中没有可用的 chat 实体 (account_id=%s, chat_id=%s)",
                self.account_id,
                getattr(event, "chat_id", None),
            )
            return
        try:
            recorder(self.account_id, chat)
        except Exception:
            logger.exception("记录已知会话失败 (account_id=%s)", self.account_id)

    def get_subscriber_store(self) -> Any:
        """Resolve the persistent push-subscription store for this account."""
        with self._lock:
            if self.subscriber_store is None:
                base_dir = (
                    Path(self.queue_db_path).parent
                    if self.queue_db_path
                    else Path("data")
                )
                self.subscriber_store = SubscriberStore(base_dir / "subscribers.db")
            return self.subscriber_store

    async def _set_bot_commands(self) -> None:
        """Expose the push subscription commands in the bot's command menu."""
        if not self.client_manager:
            return
        client = self.client_manager.get_client()
        if client is None:
            return
        from telethon.tl.functions.bots import ResetBotCommandsRequest, SetBotCommandsRequest
        from telethon.tl.types import BotCommand, BotCommandScopeDefault

        try:
            if getattr(self.config, "bot_commands_enabled", True):
                commands = [
                    BotCommand("start", t("message.bot_command.menu_start")),
                    BotCommand("stop", t("message.bot_command.menu_stop")),
                    BotCommand("resume", t("message.bot_command.menu_resume")),
                    BotCommand("status", t("message.bot_command.menu_status")),
                ]
                await client(
                    SetBotCommandsRequest(
                        scope=BotCommandScopeDefault(),
                        lang_code="",
                        commands=commands,
                    )
                )
                logger.info(t("log.bot.commands_menu_set"))
            else:
                await client(
                    ResetBotCommandsRequest(
                        scope=BotCommandScopeDefault(),
                        lang_code="",
                    )
                )
                logger.info(t("log.bot.commands_menu_cleared"))
        except Exception as exc:
            logger.warning(
                t("log.bot.commands_menu_failed", error=str(exc)),
                exc_info=True,
            )

    @staticmethod
    def _command_name(raw_text: str | None) -> str | None:
        """Extract a bare command word, ignoring any @botname suffix."""
        text = (raw_text or "").strip()
        if not text.startswith("/"):
            return None
        word = text.split()[0].lower()
        if "@" in word:
            word = word.split("@", 1)[0]
        return word[1:] if len(word) > 1 else None

    @staticmethod
    def _sender_identity(event) -> dict[str, Any]:
        """Capture user identity from a private chat update without API calls."""
        sender = getattr(event, "sender", None)
        return {
            "user_id": (
                event.sender_id
                if event.sender_id is not None
                else getattr(event, "chat_id", None)
            ),
            "username": getattr(sender, "username", None),
            "first_name": getattr(sender, "first_name", None),
            "last_name": getattr(sender, "last_name", None),
        }

    @staticmethod
    async def _safe_reply(event, text: str) -> None:
        reply = getattr(event, "reply", None)
        if reply is not None:
            await reply(text)

    async def _bot_command_handler(self, event) -> None:
        """Handle private bot-account commands: /start /stop /resume /status."""
        if (
            self.session_type != "bot"
            or not getattr(self.config, "bot_commands_enabled", True)
            or not getattr(event, "is_private", False)
        ):
            return
        command = self._command_name(
            getattr(getattr(event, "message", None), "raw_text", None)
        )
        if command not in ("start", "stop", "resume", "status"):
            return
        identity = self._sender_identity(event)
        user_id = identity.get("user_id")
        if user_id is None:
            return
        try:
            if command == "start":
                await self._cmd_start(event, identity)
            elif command == "stop":
                await self._cmd_stop(event, int(user_id))
            elif command == "resume":
                await self._cmd_resume(event, int(user_id))
            else:
                await self._cmd_status(event, int(user_id))
        except Exception as exc:
            logger.error(
                t(
                    "log.bot.command_failed",
                    command=command,
                    user_id=user_id,
                    error=str(exc),
                ),
                exc_info=True,
            )

    async def _cmd_start(self, event, identity: dict[str, Any]) -> None:
        """Register the user identity and reply with the command reference."""
        store = self.get_subscriber_store()
        store.record(
            int(identity["user_id"]),
            username=identity.get("username"),
            first_name=identity.get("first_name"),
            last_name=identity.get("last_name"),
        )
        logger.info(
            t(
                "log.bot.command_start",
                user_id=identity["user_id"],
                username=identity.get("username") or "-",
            )
        )
        await self._safe_reply(event, t("message.bot_command.start_help"))

    async def _cmd_stop(self, event, user_id: int) -> None:
        """Opt the user out of push delivery."""
        self.get_subscriber_store().set_status(user_id, "paused")
        logger.info(t("log.bot.command_stop", user_id=user_id))
        await self._safe_reply(event, t("message.bot_command.stopped"))

    async def _cmd_resume(self, event, user_id: int) -> None:
        """Re-enable push delivery for the user."""
        self.get_subscriber_store().set_status(user_id, "active")
        logger.info(t("log.bot.command_resume", user_id=user_id))
        await self._safe_reply(event, t("message.bot_command.resumed"))

    async def _cmd_status(self, event, user_id: int) -> None:
        """Reply with the user's current subscription state."""
        import datetime

        record = self.get_subscriber_store().get(user_id)
        if record is None:
            text = t("message.bot_command.status_unregistered")
        else:
            when = datetime.datetime.fromtimestamp(record["updated_at"]).strftime(
                "%Y-%m-%d %H:%M"
            )
            if record["status"] == "paused":
                text = t("message.bot_command.status_paused", date=when)
            else:
                text = t("message.bot_command.status_active", date=when)
        await self._safe_reply(event, text)

    def _is_target_suppressed(self, target: Any) -> bool:
        """True when a forwarding target has opted out of bot push delivery."""
        store = self.get_subscriber_store()
        if isinstance(target, str) and target.strip().startswith("@"):
            return store.is_suppressed_username(target)
        user_id = self._target_user_id(target)
        if user_id is None:
            return False
        return store.is_suppressed(user_id)

    def _record_target_delivery(self, target: Any) -> None:
        """Record one successful push when the target is a known subscriber."""
        try:
            store = self.get_subscriber_store()
            if isinstance(target, str) and target.strip().startswith("@"):
                store.increment_delivered_username(target)
                return
            user_id = self._target_user_id(target)
            if user_id is not None:
                store.increment_delivered(user_id)
        except Exception:
            logger.exception(
                "记录订阅用户推送数量失败 (account_id=%s, target=%s)",
                self.account_id,
                target,
            )

    @staticmethod
    def _target_user_id(target: Any) -> int | None:
        """Normalize a target chat reference to a positive user id, if possible."""
        if isinstance(target, bool):
            return None
        if isinstance(target, int):
            return target if target > 0 else None
        if isinstance(target, str):
            try:
                value = int(target.strip())
            except (TypeError, ValueError):
                return None
            return value if value > 0 else None
        return None

    async def _process_queue_item(self, item: ForwardQueueItem) -> float:
        """Load the Telegram message and execute one durable queue item."""
        if not self.client_manager or not self.forward_queue_store:
            raise RuntimeError("Telegram client or forward queue is not initialized")
        client = self.client_manager.get_client()
        if client is None:
            raise RuntimeError("Telegram client is not connected")

        forwarder = self._queue_forwarders.get(item.rule_fingerprint)
        if forwarder is None:
            rule = ForwardingRule.from_dict(item.rule_data)
            _, forwarder = self._create_forwarder(rule)
            self._queue_forwarders[item.rule_fingerprint] = forwarder

        messages_override = None
        message = None
        if item.group_member_ids:
            # Bot sessions cannot page history (GetHistoryRequest is forbidden),
            # so fetch the aggregated album members by ID in one call.  Fall
            # back to the single anchor message if the bulk fetch fails.
            try:
                fetched = await client.get_messages(
                    item.source_chat_id, ids=list(item.group_member_ids)
                )
            except Exception:
                fetched = None
            if fetched is not None:
                messages_override = [m for m in fetched if m is not None]
                if messages_override:
                    messages_override.sort(key=lambda m: m.id)
                    message = messages_override[0]
        if message is None:
            message = await client.get_messages(item.source_chat_id, ids=item.source_message_id)
        if message is None:
            raise RuntimeError(
                f"Source message {item.source_chat_id}/{item.source_message_id} is no longer available"
            )
        if not item.source_chat_name:
            source_chat_name = self._chat_display_name(
                getattr(message, "chat", None), item.source_chat_id
            )
            if source_chat_name != str(item.source_chat_id):
                self.forward_queue_store.update_source_chat_name(
                    item.id, source_chat_name
                )

        await forwarder.forward_message(
            message,
            item.sender_id,
            skip_dedup=item.attempt_count > 1 or item.next_target_index > 0,
            start_target_index=item.next_target_index,
            messages_override=messages_override,
            on_target_success=lambda index: self.forward_queue_store.update_target_index(
                item.id, index
            ),
        )
        return max(0.0, float(forwarder.rule.delay))

    def _queue_outcome(
        self, item: ForwardQueueItem, status: str, error: Exception | None
    ) -> None:
        current_item = item
        item_exists = False
        if self.forward_queue_store:
            try:
                current_item = self.forward_queue_store.get_item(item.id)
                item_exists = True
            except KeyError:
                pass
        if status == "failed" and item_exists:
            increment_failed = getattr(self.stats_db, "increment_failed", None)
            if callable(increment_failed):
                increment_failed(current_item.rule_name)
        self._publish_event(
            "forward",
            self._forward_event_payload(
                item, status=status, error=str(error) if error else None
            ),
        )

    def list_queue_items(self, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        store = self.forward_queue_store
        if not store:
            return {"items": [], "total": 0, "limit": limit, "offset": offset}
        account_id = self.account_id or "default"
        items, total = store.list_active_page(limit, offset)
        return {"items": [
            self._queue_item_data(item, account_id, account_id)
            for item in items
        ], "total": total, "limit": max(1, min(int(limit), 100)), "offset": max(0, int(offset))}

    def delete_queue_item(self, item_id: int) -> bool:
        """Remove one pending or processing task from this account's queue."""
        store = self.forward_queue_store
        if not store:
            return False
        return store.delete_item(item_id)

    def _forward_event_payload(
        self, item: ForwardQueueItem, *, status: str, error: str | None = None
    ) -> dict[str, Any]:
        payload = {
            "status": status,
            "account_id": self.account_id,
            "rule": item.rule_name,
            "source_chat_id": item.source_chat_id,
            "source_chat_name": item.source_chat_name,
            "source_message_id": item.source_message_id,
            "target_count": len(item.rule_data.get("target_chats") or []),
            "completed_target_count": item.next_target_index,
            "attempt_count": item.attempt_count,
            "failure_count": item.failure_count,
        }
        if error:
            payload["error"] = error
        return payload

    @staticmethod
    def _queue_item_data(
        item: ForwardQueueItem, account_id: str, account_label: str
    ) -> dict[str, Any]:
        targets = item.rule_data.get("target_chats") or []
        return {
            "id": item.id,
            "account_id": account_id,
            "account_label": account_label,
            "rule_name": item.rule_name,
            "source_chat_id": item.source_chat_id,
            "source_chat_name": item.source_chat_name,
            "source_message_id": item.source_message_id,
            "grouped_id": item.grouped_id,
            "status": item.status,
            "attempt_count": item.attempt_count,
            "failure_count": item.failure_count,
            "next_target_index": item.next_target_index,
            "target_count": len(targets),
            "available_at": item.available_at,
            "last_error": item.last_error,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
            "content_preview": item.content_preview,
            "media_files": list(item.media_files),
            "media_size": item.media_size,
        }

    def _publish_event(self, event_type: str, payload: dict[str, Any]) -> None:
        if self.events:
            self.events.publish(event_type, payload)

    def submit_telegram(
        self,
        callback: Callable[..., Any],
        *args,
    ) -> Future:
        """Run an async Telegram callback on the client's owning event loop."""
        with self._lock:
            loop = self.loop
            client_manager = self.client_manager
            connected = self._is_connected

        if self.session_type != "user":
            raise RuntimeError(t("message.export.user_mode_required"))
        if not connected or not loop or loop.is_closed() or not client_manager:
            raise RuntimeError(t("message.export.telegram_not_connected"))
        client = client_manager.get_client()
        if client is None:
            raise RuntimeError(t("message.export.telegram_not_connected"))

        async def invoke():
            with account_log_context(self.account_id):
                return await callback(client, *args)

        return asyncio.run_coroutine_threadsafe(invoke(), loop)
    
    async def _central_message_handler(self, event) -> None:
        """Match and persist an update without performing Telegram sends."""
        from backend.utils import get_media_description

        message = event.message
        chat_id = event.chat_id
        sender_id = event.sender_id

        # Inline entity resolution — no API calls during ingestion.
        chat = getattr(event, "chat", None) or getattr(message, "chat", None)
        chat_title = self._chat_display_name(chat, chat_id)
        sender = getattr(event, "sender", None) or getattr(message, "sender", None)
        if sender:
            sender_name = ' '.join(filter(None, [
                getattr(sender, 'first_name', None),
                getattr(sender, 'last_name', None),
            ])) or str(sender_id)
        else:
            sender_name = str(sender_id)

        # Preview
        raw_text = message.text or get_media_description(message)
        raw_text = raw_text.replace('\n', ' ')
        message_preview = f"{raw_text[:50]}..." if len(raw_text) > 50 else raw_text
        file_size = get_file_size(message)
        media_files = []
        if file_size or getattr(message, "media", None):
            file = getattr(message, "file", None)
            media_files.append({
                "message_id": int(message.id),
                "name": getattr(file, "name", None),
                "media_type": get_media_type(message),
                "mime_type": getattr(file, "mime_type", None),
                "size": int(file_size or 0),
            })

        # Log received
        logger.debug(t("log.bot.message_received",
                       chat=chat_title, chat_id=chat_id,
                       sender=sender_name, sender_id=sender_id,
                       preview=message_preview))

        # Match rules
        matched_rules = []
        filtered_by = []
        for rule, msg_filter, forwarder in self.rule_forwarder_map.values():
            if chat_id in rule.source_chats:
                # Media groups need the full album to judge
                if message.grouped_id:
                    matched_rules.append((rule, forwarder))
                elif msg_filter.should_forward(message, sender_id=sender_id):
                    matched_rules.append((rule, forwarder))
                else:
                    filtered_by.append((rule.name, forwarder))

        if not matched_rules:
            # Bump filter counts
            for _, forwarder in filtered_by:
                forwarder.filtered_count += 1
                forwarder._stats_db.increment_filtered(forwarder.rule.name)
                forwarder._stats_db.increment_daily(forwarder.rule.name, is_forwarded=False)
            return

        if not self.forward_queue:
            raise RuntimeError("Forward queue is not running")

        # Media group events share one durable key with a settle window.
        for rule, forwarder in matched_rules:
            _, inserted = self.forward_queue.enqueue(
                rule_data=rule.to_dict(),
                source_chat_id=chat_id,
                source_chat_name=(
                    chat_title if chat_title != str(chat_id) else None
                ),
                source_message_id=message.id,
                sender_id=sender_id,
                grouped_id=message.grouped_id,
                settle_seconds=self.config.forward_queue_media_group_settle_seconds,
                content_preview=message_preview,
                media_files=media_files,
                media_size=file_size,
            )
            source = self._message_source_label(chat_title, chat_id, message.id)
            if message.grouped_id:
                queue_depth = self.forward_queue.active_count()
                log_key = (
                    "log.forward_queue.media_group_enqueued"
                    if inserted
                    else "log.forward_queue.media_group_merged"
                )
                log_method = logger.info if inserted else logger.debug
                log_method(
                    t(
                        log_key,
                        rule=rule.name,
                        source=source,
                        queue_depth=queue_depth,
                    )
                )
            else:
                if inserted:
                    queue_depth = self.forward_queue.active_count()
                    logger.info(
                        t(
                            "log.forward_queue.enqueued",
                            rule=rule.name,
                            source=source,
                            queue_depth=queue_depth,
                        )
                    )
                else:
                    logger.debug(
                        t(
                            "log.forward_queue.duplicate",
                            rule=rule.name,
                            source=source,
                        )
                    )

    @staticmethod
    def _chat_display_name(chat: Any, chat_id: int) -> str:
        title = getattr(chat, "title", None)
        if title:
            return str(title)
        name = " ".join(
            filter(
                None,
                [
                    getattr(chat, "first_name", None),
                    getattr(chat, "last_name", None),
                ],
            )
        )
        return str(name or getattr(chat, "username", None) or chat_id)

    @staticmethod
    def _message_source_label(chat_title: Any, chat_id: int, message_id: int) -> str:
        title = str(chat_title or chat_id)
        if title == str(chat_id):
            return f"{chat_id}/{message_id}"
        return f"{title} ({chat_id})/{message_id}"

    async def _button_action_handler(self, event) -> None:
        """Run message actions selected by an independent rule."""
        from backend.utils import get_media_description

        if not self.button_action_engine:
            return
        try:
            result = await self.button_action_engine.handle(event)
            if result:
                rule_name, button_texts = result
                self.stats_db.increment_button_action(rule_name)
                message = event.message
                raw_content = message.text or get_media_description(message)
                raw_content = raw_content.replace('\n', ' ')
                content = (
                    f"{raw_content[:50]}..." if len(raw_content) > 50 else raw_content
                )
                logger.info(
                    t(
                        "log.button_action.clicked",
                        rule=rule_name,
                        buttons=", ".join(button_texts),
                        count=len(button_texts),
                        chat_id=event.chat_id,
                        message_id=message.id,
                        content=content,
                    )
                )
                self._publish_event(
                    "button-action",
                    {
                        "status": "completed",
                        "account_id": self.account_id,
                        "rule": rule_name,
                        "buttons": button_texts,
                        "chat_id": event.chat_id,
                        "message_id": message.id,
                    },
                )
        except Exception as exc:
            logger.error(
                t(
                    "log.button_action.failed",
                    chat_id=getattr(event, "chat_id", None),
                    message_id=getattr(getattr(event, "message", None), "id", None),
                    error=str(exc),
                ),
                exc_info=True,
            )
            self._publish_event(
                "button-action",
                {
                    "status": "failed",
                    "account_id": self.account_id,
                    "chat_id": getattr(event, "chat_id", None),
                    "message_id": getattr(getattr(event, "message", None), "id", None),
                    "error": str(exc),
                },
            )
    
    async def stop(self) -> bool:
        with account_log_context(self.account_id):
            return await self._stop()

    async def _stop(self) -> bool:
        """Stop the Telegram runtime and wait for cleanup."""
        task = self._task
        if not self.is_running and (not task or task.done()):
            logger.warning(t("log.bot.not_running"))
            return False

        logger.debug(t("log.bot.stopping"))
        was_connected = self.is_connected
        # Stop serving new Telegram API requests before disconnecting the
        # underlying client. This closes the window where callers see a stale
        # connected flag while Telethon is already shutting down.
        self.is_connected = False
        if task and not was_connected:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        else:
            self._stop_event.set()
        if task and not task.done():
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=BOT_STOP_TIMEOUT)
            except asyncio.TimeoutError:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        self.is_running = False
        self._task = None
        logger.debug(t("log.bot.stop_success"))
        return True

    async def restart(self) -> bool:
        with account_log_context(self.account_id):
            return await self._restart()

    async def _restart(self) -> bool:
        """Restart the Telegram runtime on the current event loop."""
        logger.debug(t("log.bot.restarting"))

        if self.is_running:
            if not await self.stop():
                logger.error(t("log.bot.restart_failed"))
                return False

            await asyncio.sleep(BOT_RESTART_DELAY)

        return await self.start()
    
    def get_status(self) -> dict:
        """Get Bot status"""
        with self._lock:
            # Aggregate statistics from all forwarders
            total_forwarded = 0
            total_filtered = 0
            if hasattr(self, 'forwarders') and self.forwarders:
                for forwarder in self.forwarders:
                    stats = forwarder.get_stats()
                    total_forwarded += stats.get("forwarded", 0)
                    total_filtered += stats.get("filtered", 0)
            else:
                # Bot not running, read from DB
                db = self.stats_db
                all_stats = db.get_all_stats()
                for stats in all_stats.values():
                    total_forwarded += stats.get("forwarded", 0)
                    total_filtered += stats.get("filtered", 0)

            queue_status = {"counts": {}, "paused_until": 0, "pause_reason": None}
            if self.forward_queue_store:
                paused_until, pause_reason = self.forward_queue_store.get_pause()
                queue_status = {
                    "counts": self.forward_queue_store.counts(),
                    "paused_until": paused_until,
                    "pause_reason": pause_reason,
                }

            return {
                "is_running": self._is_running,
                "is_connected": self.client_manager.is_connected if self.client_manager else False,
                "stats": {
                    "forwarded": total_forwarded,
                    "filtered": total_filtered,
                    "total": total_forwarded + total_filtered,
                },
                "queue": queue_status,
            }

    def reset_stats(self) -> None:
        """Reset all forwarding statistics"""
        db = self.stats_db
        db.reset_stats()
        # Also reset in-memory counters if forwarders are active
        if hasattr(self, 'forwarders'):
            for forwarder in self.forwarders:
                forwarder.forwarded_count = 0
                forwarder.filtered_count = 0
