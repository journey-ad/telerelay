"""
Telegram Client Management Module
Encapsulates Telethon client, handles connection and session management
"""
import asyncio
from pathlib import Path
from typing import Optional, Callable
from urllib.parse import urlparse
from telethon import TelegramClient, events
from telethon.errors import (
    SessionPasswordNeededError,
    FloodWaitError,
    PhoneNumberInvalidError,
    PhoneCodeInvalidError,
    PasswordHashInvalidError
)
from telethon.tl.types import User
from src.config import Config
from src.logger import get_logger
from src.i18n import t

logger = get_logger()


class TelegramClientManager:
    """Telegram Client Manager"""

    def __init__(self, config: Config, auth_manager: Optional['AuthManager'] = None):
        """
        Initialize client manager

        Args:
            config: Configuration object
            auth_manager: Authentication manager (for User mode authentication)
        """
        self.config = config
        self.auth_manager = auth_manager
        self.client: Optional[TelegramClient] = None
        self.is_connected = False

        # Ensure session directory exists
        session_dir = Path("sessions")
        session_dir.mkdir(exist_ok=True)

        # Session file path
        self.session_name = session_dir / "telegram_session"
    
    def _parse_proxy(self) -> Optional[tuple]:
        """
        Parse proxy configuration

        Returns:
            (proxy_type, proxy_host, proxy_port) or None
        """
        if not self.config.proxy_url:
            return None
        
        try:
            parsed = urlparse(self.config.proxy_url)
            proxy_type = parsed.scheme.lower()
            
            if proxy_type not in ['socks5', 'http', 'socks4']:
                logger.warning(t("log.client.proxy_unsupported", type=proxy_type))
                return None
            
            # Convert to Telethon-supported proxy type
            if proxy_type == 'socks5':
                import python_socks
                proxy_type = python_socks.ProxyType.SOCKS5
            elif proxy_type == 'socks4':
                import python_socks
                proxy_type = python_socks.ProxyType.SOCKS4
            elif proxy_type == 'http':
                import python_socks
                proxy_type = python_socks.ProxyType.HTTP
            
            proxy_host = parsed.hostname
            proxy_port = parsed.port or 1080

            # If username and password exist
            proxy_username = parsed.username
            proxy_password = parsed.password

            logger.info(t("log.client.proxy_using", type=proxy_type, host=proxy_host, port=proxy_port))

            return (proxy_type, proxy_host, proxy_port, True, proxy_username, proxy_password)

        except Exception as e:
            logger.error(t("log.client.proxy_parse_failed", error=str(e)))
            return None
    
    async def connect(self) -> bool:
        """
        Connect to Telegram

        Returns:
            Whether successfully connected
        """
        try:
            # Parse proxy configuration
            proxy = self._parse_proxy()

            # Create client
            if self.config.session_type == "bot":
                # Bot mode
                if not self.config.bot_token:
                    logger.error(t("log.client.bot_token_required"))
                    return False
                
                self.client = TelegramClient(
                    str(self.session_name),
                    self.config.api_id,
                    self.config.api_hash,
                    proxy=proxy
                )
                
                await self.client.start(bot_token=self.config.bot_token)
                logger.info(t("log.client.bot_connected"))
            else:
                # User mode
                self.client = TelegramClient(
                    str(self.session_name),
                    self.config.api_id,
                    self.config.api_hash,
                    proxy=proxy
                )

                # Check if session file exists
                from pathlib import Path
                session_file = Path(f"{self.session_name}.session")
                has_session = session_file.exists()

                try:
                    # If session exists, set "connecting" state; otherwise state will be set in callback
                    if has_session:
                        self.auth_manager.set_state("connecting", "")
                        logger.info(t("log.client.session_detected"))

                    # Use callback for authentication
                    await self.client.start(
                        phone=self.auth_manager.phone_callback,
                        code_callback=self.auth_manager.code_callback,
                        password=self.auth_manager.password_callback
                    )

                    # Get user info
                    me: User = await self.client.get_me()
                    logger.info(t("log.client.user_logged_in", name=me.first_name, username=me.username))

                    # Build user info (including first and last name)
                    full_name = ' '.join(filter(None, [me.first_name, me.last_name]))
                    user_info = full_name
                    if me.username:
                        user_info += f" (@{me.username})"
                    if me.id:
                        user_info += f" [ID: {me.id}]"

                    # Save user info to AuthManager
                    self.auth_manager.set_user_info(user_info)

                    # Set authentication success state
                    self.auth_manager.set_state("success")

                except PhoneNumberInvalidError:
                    logger.error(t("log.client.phone_invalid"))
                    self.auth_manager.set_state("error", t("message.auth.phone_invalid_error"))
                    return False

                except PhoneCodeInvalidError:
                    logger.error(t("log.client.code_invalid"))
                    self.auth_manager.set_state("error", t("message.auth.code_invalid_error"))
                    return False

                except PasswordHashInvalidError:
                    logger.error(t("log.client.password_invalid"))
                    self.auth_manager.set_state("error", t("message.auth.password_invalid_error"))
                    return False

                except TimeoutError as e:
                    logger.error(t("log.client.auth_timeout", error=str(e)))
                    self.auth_manager.set_state("error", str(e))
                    return False
            
            self.is_connected = True
            return True

        except Exception as e:
            logger.error(t("log.client.connect_failed", error=str(e)))
            return False
    
    async def disconnect(self) -> None:
        """Disconnect"""
        if self.client:
            await self.client.disconnect()
            self.is_connected = False
            logger.info(t("log.client.disconnected"))
    
    def add_message_handler(
        self,
        callback: Callable,
        chats: list = None
    ) -> None:
        """
        Add message handler

        Args:
            callback: Message handling callback function
            chats: List of chat IDs to listen to
        """
        if not self.client:
            logger.error(t("log.client.client_not_initialized"))
            return
        
        # Register new message event handler
        @self.client.on(events.NewMessage(chats=chats))
        async def handler(event):
            try:
                await callback(event)
            except FloodWaitError as e:
                logger.warning(t("log.client.flood_wait", seconds=e.seconds))
                await asyncio.sleep(e.seconds)
            except Exception as e:
                logger.error(t("log.client.message_error", error=str(e)), exc_info=True)

        logger.info(t("log.client.handler_registered", count=len(chats) if chats else t("misc.all_media_types")))
    
    async def run_until_disconnected(self) -> None:
        """Run client until disconnected"""
        if self.client:
            logger.info(t("log.client.running"))
            await self.client.run_until_disconnected()
    
    def get_client(self) -> Optional[TelegramClient]:
        """
        Get Telethon client instance

        Returns:
            TelegramClient object or None
        """
        return self.client

    def clear_session(self) -> None:
        """Clear session file"""
        try:
            import os
            session_files = [
                f"{self.session_name}.session",
                f"{self.session_name}.session-journal"
            ]

            for session_file in session_files:
                if os.path.exists(session_file):
                    os.remove(session_file)
                    logger.info(t("log.client.session_deleted", file=session_file))

            logger.info(t("log.client.session_cleared"))
        except Exception as e:
            logger.error(t("log.client.session_clear_failed", error=str(e)), exc_info=True)
