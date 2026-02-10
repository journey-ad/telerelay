"""
Bot Lifecycle Management Module
Manages the startup, shutdown, and restart of Telegram Bot
"""
import asyncio
import time
import threading
from typing import Optional
from src.config import Config
from src.client import TelegramClientManager
from src.filters import MessageFilter
from src.forwarder import MessageForwarder
from src.logger import get_logger
from src.i18n import t
from src.constants import (
    BOT_STOP_TIMEOUT,
    BOT_RESTART_DELAY,
    BOT_MAIN_LOOP_INTERVAL,
    UI_UPDATE_DEBOUNCE
)

logger = get_logger()


class BotManager:
    """Bot Lifecycle Manager"""

    def __init__(self, config: Config, auth_manager: Optional['AuthManager'] = None):
        """Initialize Bot Manager

        Args:
            config: Configuration object
            auth_manager: Authentication manager (for User mode authentication)
        """
        self.config = config
        self.auth_manager = auth_manager
        self.client_manager: Optional[TelegramClientManager] = None
        self.forwarder: Optional[MessageForwarder] = None
        self.thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        # Thread-safe state management
        self._lock = threading.RLock()
        self._is_running = False
        self._is_connected = False
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        # UI update flag
        self._ui_update_flag = threading.Event()
        self._last_update_time = 0.0
        # Authenticated user info
        self._auth_success_user_info: Optional[str] = None

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
    
    def start(self) -> bool:
        """
        Start Bot

        Returns:
            Whether successfully started
        """
        if self.is_running:
            logger.warning(t("log.bot.already_running"))
            return False
        
        try:
            self._stop_event.clear()
            self.thread = threading.Thread(target=self._run_bot, daemon=True)
            self.thread.start()
            logger.info(t("log.bot.thread_created"))
            return True
        except Exception as e:
            logger.error(t("log.bot.start_failed", error=str(e)))
            return False
    
    def _run_bot(self) -> None:
        """Run Bot in a separate thread"""
        try:
            # Create new event loop
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)

            # Run Bot
            self.loop.run_until_complete(self._bot_main())
            
        except Exception as e:
            logger.error(t("log.bot.error", error=str(e)), exc_info=True)
        finally:
            if self.loop:
                self.loop.close()
            self.is_running = False
    
    async def _bot_main(self) -> None:
        """Bot main logic"""
        try:
            # Mark as running (even during connection/authentication phase)
            self.is_running = True

            # Validate configuration
            is_valid, error_msg = self.config.validate()
            if not is_valid:
                logger.error(t("log.bot.config_validation_failed", error=error_msg))
                return

            # Initialize client
            self.client_manager = TelegramClientManager(self.config, self.auth_manager)

            # Connect
            if not await self.client_manager.connect():
                logger.error(t("log.bot.connect_failed"))
                return

            # Mark as connected
            self.is_connected = True

            # If in User mode, save authenticated user info
            if self.config.session_type == "user" and self.auth_manager:
                state_info = self.auth_manager.get_state()
                if state_info["state"] == "success":
                    try:
                        from telethon.tl.types import User
                        client = self.client_manager.get_client()
                        if client:
                            me: User = await client.get_me()
                            # Build username (including first and last name)
                            full_name = ' '.join(filter(None, [me.first_name, me.last_name]))
                            user_info = t("misc.login_success", name=full_name)
                            if me.username:
                                user_info += f" (@{me.username})"
                            if me.id:
                                user_info += f" ID: {me.id}"
                            self.set_auth_success_user_info(user_info)
                            self.trigger_ui_update()  # Trigger UI update
                    except Exception as e:
                        logger.warning(t("log.bot.user_info_failed", error=str(e)))

            # Create filter and forwarder for each enabled rule
            rules = self.config.get_enabled_rules()
            self.forwarders = []  # Store all forwarders
            self.rule_forwarder_map = {}  # Rule name -> (rule, filter, forwarder)
            all_source_chats = set()  # Collect all source chats

            for rule in rules:
                # Create filter
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

                # Create forwarder
                forwarder = MessageForwarder(
                    client=self.client_manager.get_client(),
                    rule=rule,
                    message_filter=message_filter,
                    bot_manager=self,
                )
                self.forwarders.append(forwarder)
                self.rule_forwarder_map[rule.name] = (rule, message_filter, forwarder)
                all_source_chats.update(rule.source_chats)
                logger.info(t("log.bot.rule_registered", rule=rule.name, count=len(rule.source_chats)))

            # Register single central message handler (handles all source chats)
            if all_source_chats:
                self.client_manager.add_message_handler(
                    callback=self._central_message_handler,
                    chats=list(all_source_chats)
                )

            # Backward compatibility: self.forwarder points to first forwarder
            self.forwarder = self.forwarders[0] if self.forwarders else None

            logger.info(t("log.bot.started", count=len(rules)))

            # Run until stop signal received
            while not self._stop_event.is_set():
                await asyncio.sleep(BOT_MAIN_LOOP_INTERVAL)

            # Disconnect
            await self.client_manager.disconnect()
            logger.info(t("log.bot.stopped"))
            
        except Exception as e:
            logger.error(t("log.bot.main_error", error=str(e)), exc_info=True)
        finally:
            self.is_running = False
    
    async def _central_message_handler(self, event) -> None:
        """Central message handler: checks all rules, outputs log only once"""
        from src.utils import get_media_description

        message = event.message
        chat_id = event.chat_id
        sender_id = event.sender_id

        # Build source label (prioritize Telethon entity cache, usually no extra request)
        chat = await event.get_chat()
        chat_title = getattr(chat, 'title', None) or str(chat_id)
        sender = await event.get_sender()
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
        logger.info(t("log.bot.message_received",
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
            group_tag = f" gid={message.grouped_id}" if message.grouped_id else ""
            logger.debug(t("log.bot.message_filtered", rules=rules_str, group_tag=group_tag))
            # Update filter count for each rule
            for _, forwarder in filtered_by:
                forwarder.filtered_count += 1
            return

        # Forward to all matching rules
        for rule, forwarder in matched_rules:
            await forwarder.handle_message(event)
    
    def trigger_ui_update(self):
        """Trigger UI update (called by forwarder after forwarding)"""
        with self._lock:
            now = time.time()
            if now - self._last_update_time >= UI_UPDATE_DEBOUNCE:
                self._ui_update_flag.set()
                self._last_update_time = now
    
    def check_and_clear_ui_update(self) -> bool:
        """Check if UI update is needed and clear flag"""
        if self._ui_update_flag.is_set():
            self._ui_update_flag.clear()
            return True
        return False

    def set_auth_success_user_info(self, user_info: str) -> None:
        """Set authenticated user info"""
        with self._lock:
            self._auth_success_user_info = user_info

    def get_and_clear_auth_success_user_info(self) -> Optional[str]:
        """Get and clear authenticated user info"""
        with self._lock:
            user_info = self._auth_success_user_info
            self._auth_success_user_info = None
            return user_info
    
    def stop(self) -> bool:
        """
        Stop Bot

        Returns:
            Whether successfully stopped
        """
        if not self.is_running:
            logger.warning(t("log.bot.not_running"))
            return False
        
        try:
            logger.info(t("log.bot.stopping"))
            self._stop_event.set()
            
            # Wait for thread to end (max 10 seconds)
            if self.thread:
                self.thread.join(timeout=BOT_STOP_TIMEOUT)
            
            self.is_running = False
            logger.info(t("log.bot.stop_success"))
            return True

        except Exception as e:
            logger.error(t("log.bot.stop_failed", error=str(e)))
            return False
    
    def restart(self) -> bool:
        """
        Restart Bot

        Returns:
            Whether successfully restarted
        """
        logger.info(t("log.bot.restarting"))

        if self.is_running:
            if not self.stop():
                logger.error(t("log.bot.restart_failed"))
                return False
            
            # Wait for complete stop
            time.sleep(BOT_RESTART_DELAY)
        
        return self.start()
    
    def get_status(self) -> dict:
        """Get Bot status"""
        with self._lock:
            # Aggregate statistics from all forwarders
            total_forwarded = 0
            total_filtered = 0
            if hasattr(self, 'forwarders'):
                for forwarder in self.forwarders:
                    stats = forwarder.get_stats()
                    total_forwarded += stats.get("forwarded", 0)
                    total_filtered += stats.get("filtered", 0)

            return {
                "is_running": self._is_running,
                "is_connected": self.client_manager.is_connected if self.client_manager else False,
                "stats": {
                    "forwarded": total_forwarded,
                    "filtered": total_filtered,
                    "total": total_forwarded + total_filtered,
                }
            }
