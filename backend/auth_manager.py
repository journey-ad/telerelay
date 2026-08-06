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
        # Login method selection: "phone" (default, backwards compatible) or
        # "qr". The frontend picks once; the initial mode wait falls back to
        # phone on timeout so plain phone logins keep working unchanged.
        self._login_mode = "phone"
        self._mode_chosen = False
        self._mode_future: Optional[asyncio.Future[str]] = None
        self._mode_change_future: Optional[asyncio.Future[str]] = None
        self._phone_value: Optional[str] = None
        # Current QR challenge surfaced to the browser through get_state().
        self._qr_url = ""
        self._qr_expires_at = ""

    def get_state(self) -> dict:
        state = {
            "state": self._auth_state,
            "error": self._error_message,
            "user_info": self._user_info,
            "waiting_for": self._pending_kind,
        }
        if self._qr_url:
            state["qr"] = {
                "url": self._qr_url,
                "expires_at": self._qr_expires_at,
            }
        return state

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
        # The phone callback may not be armed yet while the login method is
        # still being chosen. Buffer the value and treat it as an implicit
        # selection of the phone flow.
        self._phone_value = phone
        if self._pending_kind == "phone" and self._pending_future and not self._pending_future.done():
            return self._submit("phone", phone, "phone")
        self.submit_login_mode("phone")
        return True

    def submit_login_mode(self, mode: str) -> bool:
        """Select the login method ("phone" or "qr")."""
        mode = mode.strip().lower()
        if mode not in ("phone", "qr"):
            self.set_state("error", t("message.auth.mode_invalid"))
            return False
        # The method can only change while no code/password challenge is in
        # flight: once send_code_request has happened the phone flow can no
        # longer be replaced by a QR login.
        if self._pending_kind not in (None, "phone") and mode != self._login_mode:
            return False
        self._login_mode = mode
        self._mode_chosen = True
        for future in (self._mode_future, self._mode_change_future):
            if future and not future.done():
                future.set_result(mode)
        logger.debug(t("log.auth.mode_selected", mode=mode))
        return True

    def set_qr(self, url: str, expires_at: str) -> None:
        """Publish the current QR challenge to the browser."""
        self._qr_url = url
        self._qr_expires_at = expires_at
        self.set_state("waiting_qr")
        logger.debug(t("log.auth.qr_updated"))

    def clear_qr(self) -> None:
        self._qr_url = ""
        self._qr_expires_at = ""

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

    async def wait_for_login_mode(self) -> str:
        """Return the login method chosen by the browser.

        Waits until the frontend explicitly picks phone or QR; a timeout falls
        back to phone so the previous phone-only behavior is preserved.
        """
        if self._mode_chosen:
            return self._login_mode
        loop = asyncio.get_running_loop()
        future: asyncio.Future[str] = loop.create_future()
        self._mode_future = future
        self.set_state("waiting_phone")
        try:
            return await asyncio.wait_for(future, timeout=self._input_timeout)
        except asyncio.TimeoutError:
            return "phone"
        finally:
            if self._mode_future is future:
                self._mode_future = None

    async def wait_for_mode_change(self) -> str:
        """Wait until the user switches the login method mid-flow (QR -> phone)."""
        loop = asyncio.get_running_loop()
        future: asyncio.Future[str] = loop.create_future()
        self._mode_change_future = future
        try:
            return await future
        finally:
            if self._mode_change_future is future:
                self._mode_change_future = None

    async def phone_callback(self) -> str:
        value = self._phone_value
        if value is not None:
            self._phone_value = None
            return value
        return await self._wait_for_input("phone", "waiting_phone", "phone")

    async def code_callback(self) -> str:
        return await self._wait_for_input("code", "waiting_code", "code")

    async def password_callback(self) -> str:
        return await self._wait_for_input("password", "waiting_password", "password")

    def reset(self) -> None:
        if self._pending_future and not self._pending_future.done():
            self._pending_future.cancel()
        for future in (self._mode_future, self._mode_change_future):
            if future and not future.done():
                future.cancel()
        self._pending_kind = None
        self._pending_future = None
        self._mode_future = None
        self._mode_change_future = None
        self._login_mode = "phone"
        self._mode_chosen = False
        self._phone_value = None
        self._qr_url = ""
        self._qr_expires_at = ""
        self._auth_state = "idle"
        self._error_message = ""
        self._user_info = ""
