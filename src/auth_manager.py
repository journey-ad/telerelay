"""Telegram User Authentication Manager"""
import queue
import threading
import asyncio
from typing import Optional
from src.logger import get_logger
from src.i18n import t

logger = get_logger()


class AuthManager:
    """Telegram User Authentication Manager

    Manages the authentication flow for Telegram User mode, passing authentication
    information between WebUI thread and Bot thread through queue mechanism.
    """

    def __init__(self, input_timeout: int = 300):
        """Initialize authentication manager

        Args:
            input_timeout: User input timeout in seconds, default 5 minutes
        """
        self._lock = threading.RLock()

        # Authentication state
        self._auth_state = "idle"
        self._error_message = ""

        # Current logged-in user info
        self._user_info = ""

        # User input queues (each queue can only hold one value)
        self._phone_queue = queue.Queue(maxsize=1)
        self._code_queue = queue.Queue(maxsize=1)
        self._password_queue = queue.Queue(maxsize=1)

        # Timeout configuration
        self._input_timeout = input_timeout

        logger.info(t("log.auth.initialized"))

    def get_state(self) -> dict:
        """Get current authentication state

        Returns:
            Dictionary containing state information
        """
        with self._lock:
            return {
                "state": self._auth_state,
                "error": self._error_message,
                "user_info": self._user_info
            }

    def set_state(self, state: str, error: str = "") -> None:
        """Set authentication state

        Args:
            state: State value
            error: Error message (optional)
        """
        with self._lock:
            self._auth_state = state
            self._error_message = error
            logger.debug(t("log.auth.state_updated", state=state, error=f"({error})" if error else ""))

    def set_user_info(self, user_info: str) -> None:
        """Set current logged-in user info

        Args:
            user_info: User info string
        """
        with self._lock:
            self._user_info = user_info
            logger.debug(t("log.auth.user_info_saved", info=user_info))

    def _submit_to_queue(self, target_queue: queue.Queue, value: str, name: str) -> bool:
        """Generic method to submit to queue

        Args:
            target_queue: Target queue
            value: Value to submit
            name: Input item name (for logging)

        Returns:
            Whether submission was successful
        """
        try:
            target_queue.put_nowait(value)
            logger.info(t("log.auth.submitted", name=name))
            return True
        except queue.Full:
            logger.warning(t("log.auth.queue_full", name=name))
            return False

    def submit_phone(self, phone: str) -> bool:
        """Submit phone number (called by WebUI)"""
        phone = phone.strip()
        if not phone:
            self.set_state("error", t("message.auth.phone_empty"))
            return False
        if not phone.startswith('+'):
            self.set_state("error", t("message.auth.phone_format"))
            return False
        if self._submit_to_queue(self._phone_queue, phone, "phone"):
            logger.info(t("log.auth.phone_masked", phone=phone[:5]))
            return True
        return False

    def submit_code(self, code: str) -> bool:
        """Submit verification code (called by WebUI)"""
        code = code.strip()
        if not code:
            self.set_state("error", t("message.auth.code_empty"))
            return False
        if not code.isdigit():
            self.set_state("error", t("message.auth.code_format"))
            return False
        return self._submit_to_queue(self._code_queue, code, "code")

    def submit_password(self, password: str) -> bool:
        """Submit two-step verification password (called by WebUI)"""
        if not password:
            self.set_state("error", t("message.auth.password_empty"))
            return False
        return self._submit_to_queue(self._password_queue, password, "password")

    async def _wait_for_input(self, input_queue: queue.Queue, state: str, name: str) -> str:
        """Generic method to wait for user input

        Args:
            input_queue: Queue to read from
            state: State while waiting
            name: Input item name (for logging)

        Returns:
            User input

        Raises:
            TimeoutError: Input timeout
        """
        logger.info(t("log.auth.waiting", name=name))
        self.set_state(state)

        try:
            loop = asyncio.get_event_loop()
            value = await loop.run_in_executor(
                None, input_queue.get, True, self._input_timeout
            )
            logger.info(t("log.auth.received", name=name))
            return value
        except queue.Empty:
            error_msg = t("log.auth.timeout", name=name, timeout=self._input_timeout)
            logger.error(error_msg)
            self.set_state("error", error_msg)
            raise TimeoutError(error_msg)
        except Exception as e:
            logger.error(t("log.auth.get_failed", name=name, error=str(e)))
            self.set_state("error", str(e))
            raise

    async def phone_callback(self) -> str:
        """Phone number callback (called by Telethon)"""
        value = await self._wait_for_input(self._phone_queue, "waiting_phone", "phone")
        logger.info(t("log.auth.phone_masked", phone=value[:5]))
        return value

    async def code_callback(self) -> str:
        """Verification code callback (called by Telethon)"""
        return await self._wait_for_input(self._code_queue, "waiting_code", "code")

    async def password_callback(self) -> str:
        """Password callback (called by Telethon)"""
        return await self._wait_for_input(self._password_queue, "waiting_password", "password")

    def reset(self) -> None:
        """Reset authentication state and queues"""
        with self._lock:
            self._auth_state = "idle"
            self._error_message = ""
            self._user_info = ""

            # Clear all queues
            while not self._phone_queue.empty():
                try:
                    self._phone_queue.get_nowait()
                except queue.Empty:
                    break

            while not self._code_queue.empty():
                try:
                    self._code_queue.get_nowait()
                except queue.Empty:
                    break

            while not self._password_queue.empty():
                try:
                    self._password_queue.get_nowait()
                except queue.Empty:
                    break

            logger.info(t("log.auth.reset"))
