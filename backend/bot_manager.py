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
from backend.filters import MessageFilter
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

            logger.info(t("log.bot.started", count=len(self.forwarders)))

            # Run until stop signal received
            await self._stop_event.wait()

        except Exception as e:
            logger.error(t("log.bot.main_error", error=str(e)), exc_info=True)
        finally:
            if self.forward_queue:
                await self.forward_queue.stop(timeout=max(1, BOT_STOP_TIMEOUT - 2))
            if self.client_manager:
                await self.client_manager.disconnect()
            self.is_connected = False
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
        self._forwarding_handler = None
        self._button_handler = None
        self._chat_recorder_handler = None
        if forwarding_chats:
            self._forwarding_handler = self.client_manager.add_message_handler(
                callback=self._central_message_handler,
                chats=forwarding_chats,
            )
        if session_type == "bot":
            self._chat_recorder_handler = self.client_manager.add_message_handler(
                callback=self._record_chat_entity,
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
        logger.debug(
            "收到消息,记录已知会话 (account_id=%s, chat_id=%s, entity=%s)",
            self.account_id,
            getattr(chat, "id", None),
            type(chat).__name__,
        )
        try:
            recorder(self.account_id, chat)
        except Exception:
            logger.exception("记录已知会话失败 (account_id=%s)", self.account_id)

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
            on_target_success=lambda index: self.forward_queue_store.update_target_index(
                item.id, index
            ),
        )
        return max(0.0, float(forwarder.rule.delay))

    def _queue_outcome(
        self, item: ForwardQueueItem, status: str, error: Exception | None
    ) -> None:
        if self.forward_queue_store:
            try:
                item = self.forward_queue_store.get_item(item.id)
            except KeyError:
                pass
        self._publish_event(
            "forward",
            self._forward_event_payload(
                item, status=status, error=str(error) if error else None
            ),
        )

    def list_queue_items(self, limit: int = 50) -> list[dict[str, Any]]:
        store = self.forward_queue_store
        if not store:
            return []
        account_id = self.account_id or "default"
        return [
            self._queue_item_data(item, account_id, account_id)
            for item in store.list_active(limit)
        ]

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
        """Click callback buttons selected by an independent rule."""
        from backend.utils import get_media_description

        if not self.button_action_engine:
            return
        try:
            result = await self.button_action_engine.handle(event)
            if result:
                rule_name, button_texts = result
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
        if task and not self.is_connected:
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
