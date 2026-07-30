"""
Bot Lifecycle Management Module
Manages the startup, shutdown, and restart of Telegram Bot
"""
import asyncio
import threading
from concurrent.futures import Future
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Optional

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
from backend.logger import get_logger
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
    ):
        """Initialize Bot Manager

        Args:
            config: Configuration object
            auth_manager: Authentication manager (for User mode authentication)
        """
        self.config = config
        self.auth_manager = auth_manager
        self.session_name = Path(session_name) if session_name else Path("data/telegram_session")
        self.on_user_authenticated: Callable[[dict[str, Any]], None] | None = None
        self.on_preview_message: Callable[[Any], Awaitable[None]] | None = None
        self.client_manager: Optional[TelegramClientManager] = None
        self.forwarder: Optional[MessageForwarder] = None
        self.forwarders = []
        self.rule_forwarder_map = {}
        self._queue_forwarders = {}
        self._target_label_cache: dict[str, str] = {}
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

    def set_session_name(self, session_name: str | Path) -> None:
        """Select the session used by the next runtime start."""
        if self.is_running:
            raise RuntimeError("Cannot change Telegram session while runtime is active")
        self.session_name = Path(session_name)

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
                name="telerelay-telegram-runtime",
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
            # Purge residual temp files from previous runs
            from backend.forwarder.downloader import MediaDownloader
            MediaDownloader.purge_temp_dir()

            # Mark as running (even during connection/authentication phase)
            self.is_running = True

            # Validate configuration
            is_valid, error_msg = self.config.validate_connection()
            if not is_valid:
                logger.error(t("log.bot.config_validation_failed", error=error_msg))
                return

            # Initialize client
            self.client_manager = TelegramClientManager(
                self.config,
                self.auth_manager,
                session_name=self.session_name,
                on_user_authenticated=self.on_user_authenticated,
            )

            # Connect
            if not await self.client_manager.connect():
                logger.error(t("log.bot.connect_failed"))
                return

            # Mark as connected
            self.is_connected = True

            if self.on_preview_message:
                self.client_manager.add_message_handler(self.on_preview_message)

            # Create filter and forwarder for each enabled rule
            rules = self.config.get_enabled_rules()
            self.forwarders = []
            self.rule_forwarder_map = {}
            self._queue_forwarders = {}
            self._target_label_cache = {}
            all_source_chats = set()  # Collect all source chats

            for rule in rules:
                message_filter, forwarder = self._create_forwarder(rule)
                self.forwarders.append(forwarder)
                self.rule_forwarder_map[rule.name] = (rule, message_filter, forwarder)
                self._queue_forwarders[rule_fingerprint(rule.to_dict())] = forwarder
                all_source_chats.update(rule.source_chats)
                logger.debug(t("log.bot.rule_registered", rule=rule.name, count=len(rule.source_chats)))

            # Start the durable consumer before accepting new updates. Pending
            # jobs use their stored rule snapshot, even if configuration changed.
            self.forward_queue_store = ForwardQueueStore(self.config.forward_queue_db_path)
            self.forward_queue = ForwardQueue(
                self.forward_queue_store,
                self._process_queue_item,
                max_retries=self.config.forward_queue_max_retries,
                retry_base_seconds=self.config.forward_queue_retry_base_seconds,
                flood_wait_buffer=self.config.forward_queue_flood_wait_buffer,
                poll_interval=self.config.forward_queue_poll_interval,
                completed_retention_days=self.config.forward_queue_completed_retention_days,
            )
            await self.forward_queue.start()

            # Register single central message handler (handles all source chats)
            if all_source_chats:
                self.client_manager.add_message_handler(
                    callback=self._central_message_handler,
                    chats=list(all_source_chats)
                )

            # Button interaction rules are independent from forwarding rules.
            self.button_action_engine = None
            button_action_rules = self.config.get_enabled_button_action_rules()
            if button_action_rules and self.config.session_type != "user":
                logger.warning(t("log.button_action.user_mode_required"))
            elif button_action_rules:
                valid_button_rules = [
                    rule
                    for rule in button_action_rules
                    if rule.source_chats and rule.button_texts
                ]
                if valid_button_rules:
                    self.button_action_engine = ButtonActionEngine(valid_button_rules)
                    button_source_chats = list(dict.fromkeys(
                        chat
                        for rule in valid_button_rules
                        for chat in rule.source_chats
                    ))
                    self.client_manager.add_message_handler(
                        callback=self._button_action_handler,
                        chats=button_source_chats,
                        incoming=True,
                    )
                    logger.debug(
                        t(
                            "log.button_action.registered",
                            rules=len(valid_button_rules),
                            chats=len(button_source_chats),
                        )
                    )

            # Backward compatibility: self.forwarder points to first forwarder
            self.forwarder = self.forwarders[0] if self.forwarders else None

            logger.info(t("log.bot.started", count=len(rules)))

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
        )
        return message_filter, forwarder

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

        await forwarder.forward_message(
            message,
            item.sender_id,
            skip_dedup=item.attempt_count > 1 or item.next_target_index > 0,
            start_target_index=item.next_target_index,
            on_target_success=lambda index: self.forward_queue_store.update_target_index(item.id, index),
        )
        return max(0.0, float(forwarder.rule.delay))

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

        if self.config.session_type != "user":
            raise RuntimeError(t("message.export.user_mode_required"))
        if not connected or not loop or loop.is_closed() or not client_manager:
            raise RuntimeError(t("message.export.telegram_not_connected"))
        client = client_manager.get_client()
        if client is None:
            raise RuntimeError(t("message.export.telegram_not_connected"))

        async def invoke():
            return await callback(client, *args)

        return asyncio.run_coroutine_threadsafe(invoke(), loop)
    
    async def _central_message_handler(self, event) -> None:
        """Match and persist an update without performing Telegram sends."""
        from backend.utils import get_media_description

        message = event.message
        chat_id = event.chat_id
        sender_id = event.sender_id

        # Use entities already attached to the update. The ingestion path must
        # not add Telegram API calls that could block durable enqueueing.
        chat = getattr(event, "chat", None) or getattr(message, "chat", None)
        chat_title = getattr(chat, 'title', None) or str(chat_id)
        sender = getattr(event, "sender", None) or getattr(message, "sender", None)
        if sender:
            sender_name = ' '.join(filter(None, [
                getattr(sender, 'first_name', None),
                getattr(sender, 'last_name', None),
            ])) or str(sender_id)
        else:
            sender_name = str(sender_id)

        # Get message preview
        raw_text = message.text or get_media_description(message)
        raw_text = raw_text.replace('\n', ' ')
        message_preview = f"{raw_text[:50]}..." if len(raw_text) > 50 else raw_text

        # Output "message received" log
        logger.debug(t("log.bot.message_received",
                       chat=chat_title, chat_id=chat_id,
                       sender=sender_name, sender_id=sender_id,
                       preview=message_preview))

        # Find all rules matching this message
        matched_rules = []
        filtered_by = []  # Record which rules filtered it
        for rule, msg_filter, forwarder in self.rule_forwarder_map.values():
            if chat_id in rule.source_chats:
                # Skip filtering for media group messages (text may be on any message, need complete group to judge)
                if message.grouped_id:
                    matched_rules.append((rule, forwarder))
                elif msg_filter.should_forward(message, sender_id=sender_id):
                    matched_rules.append((rule, forwarder))
                else:
                    filtered_by.append((rule.name, forwarder))

        if not matched_rules:
            rules_str = ', '.join(name for name, _ in filtered_by) if filtered_by else t("misc.no_match_rules")
            logger.debug(t("log.bot.message_filtered", rules=rules_str))
            # Update filter count for each rule
            for _, forwarder in filtered_by:
                forwarder.filtered_count += 1
                forwarder._stats_db.increment_filtered(forwarder.rule.name)
                forwarder._stats_db.increment_daily(forwarder.rule.name, is_forwarded=False)
            return

        if not self.forward_queue:
            raise RuntimeError("Forward queue is not running")

        # Persist all matching rules. Media group events share one durable key
        # and extend a short settle window instead of creating duplicate jobs.
        for rule, forwarder in matched_rules:
            _, inserted = self.forward_queue.enqueue(
                rule_data=rule.to_dict(),
                source_chat_id=chat_id,
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
    
    async def stop(self) -> bool:
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
                db = get_stats_db()
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
        db = get_stats_db()
        db.reset_stats()
        # Also reset in-memory counters if forwarders are active
        if hasattr(self, 'forwarders'):
            for forwarder in self.forwarders:
                forwarder.forwarded_count = 0
                forwarder.filtered_count = 0
