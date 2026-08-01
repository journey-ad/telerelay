"""Async Telegram user authentication challenge state."""

import asyncio
from collections.abc import Callable
from typing import Optional

from backend.i18n import t
from backend.logger import get_logger

logger = get_logger()


class AuthManager:
    """Bridge Telethon's async login callbacks to HTTP submissions.

    Telethon asks for phone, code and (optionally) password through async
    callbacks.  The API resolves the corresponding Future when the user sends
    the value, so no cross-thread queue or second event loop is needed.
    """

    def __init__(
        self,
        input_timeout: int = 300,
        on_state_change: Callable[[str, str], None] | None = None,
    ):
        self._auth_state = "idle"
        self._error_message = ""
        self._user_info = ""
        self._input_timeout = input_timeout
        self._pending_kind: Optional[str] = None
        self._pending_future: Optional[asyncio.Future[str]] = None
        self._on_state_change = on_state_change

    def get_state(self) -> dict:
        return {
            "state": self._auth_state,
            "error": self._error_message,
            "user_info": self._user_info,
            "waiting_for": self._pending_kind,
        }

    def set_state(self, state: str, error: str = "") -> None:
        self._auth_state = state
        self._error_message = error
        logger.debug(t("log.auth.state_updated", state=state, error=f"({error})" if error else ""))
        if self._on_state_change:
            self._on_state_change(state, error)

    def set_user_info(self, user_info: str) -> None:
        self._user_info = user_info

    def set_on_state_change(self, callback: Callable[[str, str], None] | None) -> None:
        self._on_state_change = callback

    def _submit(self, kind: str, value: str, name: str) -> bool:
        value = value.strip()
        if not value:
            self.set_state("error", t(f"message.auth.{name}_empty"))
            return False
        if self._pending_kind != kind or not self._pending_future or self._pending_future.done():
            return False
        self._pending_future.set_result(value)
        logger.debug(t("log.auth.received", name=name))
        return True

    def submit_phone(self, phone: str) -> bool:
        phone = phone.strip()
        if not phone:
            self.set_state("error", t("message.auth.phone_empty"))
            return False
        if not phone.startswith("+"):
            self.set_state("error", t("message.auth.phone_format"))
            return False
        return self._submit("phone", phone, "phone")

    def submit_code(self, code: str) -> bool:
        code = code.strip()
        if not code:
            self.set_state("error", t("message.auth.code_empty"))
            return False
        if not code.isdigit():
            self.set_state("error", t("message.auth.code_format"))
            return False
        return self._submit("code", code, "code")

    def submit_password(self, password: str) -> bool:
        if not password:
            self.set_state("error", t("message.auth.password_empty"))
            return False
        return self._submit("password", password, "password")

    async def _wait_for_input(self, kind: str, state: str, name: str) -> str:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[str] = loop.create_future()
        self._pending_kind = kind
        self._pending_future = future
        self.set_state(state)
        try:
            return await asyncio.wait_for(future, timeout=self._input_timeout)
        except asyncio.TimeoutError as exc:
            message = t("log.auth.timeout", name=name, timeout=self._input_timeout)
            self.set_state("error", message)
            raise TimeoutError(message) from exc
        finally:
            if self._pending_future is future:
                self._pending_kind = None
                self._pending_future = None

    async def phone_callback(self) -> str:
        return await self._wait_for_input("phone", "waiting_phone", "phone")

    async def code_callback(self) -> str:
        return await self._wait_for_input("code", "waiting_code", "code")

    async def password_callback(self) -> str:
        return await self._wait_for_input("password", "waiting_password", "password")

    def reset(self) -> None:
        if self._pending_future and not self._pending_future.done():
            self._pending_future.cancel()
        self._pending_kind = None
        self._pending_future = None
        self._auth_state = "idle"
        self._error_message = ""
        self._user_info = ""
