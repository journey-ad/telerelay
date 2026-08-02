"""
Telegram Client Management Module
Encapsulates Telethon client, handles connection and session management
"""
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional
from urllib.parse import urlparse

from telethon import TelegramClient, events
from telethon.errors import (
    PasswordHashInvalidError,
    PhoneCodeInvalidError,
    PhoneNumberInvalidError,
)
from telethon.tl.types import User

from backend.config import Config
from backend.i18n import t
from backend.logger import get_logger

if TYPE_CHECKING:
    from backend.auth_manager import AuthManager

logger = get_logger()


class TelegramClientManager:
    """Telegram Client Manager"""

    def __init__(
        self,
        config: Config,
        auth_manager: Optional['AuthManager'] = None,
        session_name: str | Path | None = None,
        on_user_authenticated: Callable[[dict[str, Any]], None] | None = None,
        bot_token: str | None = None,
    ):
        """
        Initialize client manager

        Args:
            config: Configuration object
            auth_manager: Authentication manager (for User mode authentication)
        """
        self.config = config
        self.auth_manager = auth_manager
        self.on_user_authenticated = on_user_authenticated
        self.bot_token = bot_token
        self.client: Optional[TelegramClient] = None
        self.is_connected = False

        # Ensure session dir
        session_dir = Path("data")
        session_dir.mkdir(exist_ok=True)

        # Session path
        self.session_name = Path(session_name) if session_name else session_dir / "telegram_session"
        self.session_name.parent.mkdir(parents=True, exist_ok=True)
    
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

    async def _publish_identity(self, me: User) -> dict[str, Any]:
        """Capture the authenticated identity once a client is connected."""
        full_name = " ".join(filter(None, [me.first_name, me.last_name]))
        user_info = full_name
        if me.username:
            user_info += f" (@{me.username})"
        if me.id:
            user_info += f" [ID: {me.id}]"
        if self.auth_manager:
            self.auth_manager.set_user_info(user_info)
        identity = {
            "display_name": full_name,
            "username": me.username or "",
            "telegram_user_id": me.id,
        }
        if self.on_user_authenticated:
            try:
                identity["avatar_bytes"] = await self.client.download_profile_photo(
                    me,
                    file=bytes,
                    download_big=False,
                )
            except Exception as exc:
                logger.warning(t("log.client.photo_refresh_failed", error=str(exc)))
            self.on_user_authenticated(identity)
        return identity

    async def refresh_identity(self) -> dict[str, Any]:
        """Reload the connected account identity and profile photo from Telegram."""
        if self.client is None:
            raise RuntimeError(t("message.export.telegram_not_connected"))
        me: User = await self.client.get_me()
        return await self._publish_identity(me)
    
    async def connect(self) -> bool:
        """
        Connect to Telegram

        Returns:
            Whether successfully connected
        """
        try:
            # Init client
            proxy = self._parse_proxy()

            if self.bot_token:
                token = self.bot_token
                if not token:
                    logger.error(t("log.client.bot_token_required"))
                    return False

                self.client = TelegramClient(
                    str(self.session_name),
                    self.config.api_id,
                    self.config.api_hash,
                    proxy=proxy
                )
                
                await self.client.start(bot_token=token)
                logger.info(t("log.client.bot_connected"))
                me: User = await self.client.get_me()
                await self._publish_identity(me)
            else:
                # User mode
                self.client = TelegramClient(
                    str(self.session_name),
                    self.config.api_id,
                    self.config.api_hash,
                    proxy=proxy
                )

                # Check session
                from pathlib import Path
                session_file = Path(f"{self.session_name}.session")
                has_session = session_file.exists()

                try:
                    if has_session:
                        self.auth_manager.set_state("connecting", "")
                        logger.debug(t("log.client.session_detected"))

                    # Auth with callbacks
                    await self.client.start(
                        phone=self.auth_manager.phone_callback,
                        code_callback=self.auth_manager.code_callback,
                        password=self.auth_manager.password_callback
                    )

                    me: User = await self.client.get_me()
                    logger.info(
                        t("log.client.user_logged_in", name=me.first_name, username=me.username)
                    )
                    await self._publish_identity(me)
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
            if self.auth_manager:
                self.auth_manager.set_state("error", str(e))
            return False
    
    async def disconnect(self) -> None:
        """Disconnect"""
        if self.client:
            await self.client.disconnect()
            self.is_connected = False
            logger.debug(t("log.client.disconnected"))
    
    def add_message_handler(
        self,
        callback: Callable,
        chats: list = None,
        incoming: Optional[bool] = None,
    ) -> tuple[Callable, Any] | None:
        """
        Add message handler

        Args:
            callback: Message handling callback function
            chats: List of chat IDs to listen to
            incoming: Restrict updates to incoming or outgoing messages when set
        """
        if not self.client:
            logger.error(t("log.client.client_not_initialized"))
            return None

        async def handler(event):
            try:
                await callback(event)
            except Exception as e:
                logger.error(t("log.client.message_error", error=str(e)), exc_info=True)

        event_builder = events.NewMessage(chats=chats, incoming=incoming)
        self.client.add_event_handler(handler, event_builder)
        logger.debug(t("log.client.handler_registered", count=len(chats) if chats else t("misc.all_media_types")))
        return handler, event_builder

    def remove_message_handler(
        self,
        registration: tuple[Callable, Any] | None,
    ) -> None:
        """Remove a handler previously returned by ``add_message_handler``."""
        if not self.client or not registration:
            return
        callback, event_builder = registration
        self.client.remove_event_handler(callback, event_builder)

    async def run_until_disconnected(self) -> None:
        """Run client until disconnected"""
        if self.client:
            logger.debug(t("log.client.running"))
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
        self.clear_session_files(self.session_name)

    @staticmethod
    def clear_session_files(session_name: str | Path) -> None:
        """Clear a specific Telethon session and its journal."""
        try:
            import os
            session_files = [
                f"{session_name}.session",
                f"{session_name}.session-journal"
            ]

            for session_file in session_files:
                if os.path.exists(session_file):
                    os.remove(session_file)
                    logger.debug(t("log.client.session_deleted", file=session_file))

            logger.info(t("log.client.session_cleared"))
        except Exception as e:
            logger.error(t("log.client.session_clear_failed", error=str(e)), exc_info=True)
