"""Browser-direct Telegram media authorization.

This module is deliberately separate from the existing preview download code. It
delivers the target DC authorization state to an in-memory browser worker;
Telegram file bytes never enter this process.
"""

from __future__ import annotations

import base64
import secrets
from typing import Any

from telethon.crypto import AuthKey
from telethon.tl import alltlobjects, types

from backend.logger import get_logger
from backend.telegram_accounts import TelegramAccountError
from backend.telegram_preview import TelegramPreviewError


logger = get_logger()


DC_WEB_HOSTS = {
    dc_id: f"kws{dc_id}-1.web.telegram.org" for dc_id in range(1, 6)
}


def _base64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _auth_key_id(auth_key: AuthKey) -> int:
    if auth_key.key_id is None:
        raise ValueError("Auth key is not initialized")
    return int(auth_key.key_id)


class TelegramMediaService:
    """Issue browser-direct video credentials using Web K's no-PFS path."""

    def __init__(self, bot_manager: Any, account_store: Any, config: Any):
        self.bot_manager = bot_manager
        self.account_store = account_store
        self.config = config

    def _active_account(self, account_id: str | None) -> str:
        target = account_id or self.account_store.active_account_id
        try:
            self.account_store.get_public(target)
        except TelegramAccountError as exc:
            raise TelegramPreviewError("account_not_found", "Telegram account does not exist") from exc
        return target

    def _client(self, account_id: str):
        target = self._active_account(account_id)
        try:
            runtime = self.bot_manager.get_runtime(target)
        except TelegramAccountError as exc:
            raise TelegramPreviewError(exc.code, str(exc)) from exc
        manager = runtime.client_manager
        client = manager.get_client() if manager else None
        if not runtime.is_connected or client is None:
            raise TelegramPreviewError("telegram_not_connected", "The requested Telegram account is not connected")
        return client

    async def _message(self, client: Any, chat_id: int, message_id: int):
        try:
            message = await client.get_messages(chat_id, ids=message_id)
        except Exception as exc:
            raise TelegramPreviewError("message_not_found", "Telegram message was not found") from exc
        if message is None:
            raise TelegramPreviewError("message_not_found", "Telegram message was not found")
        return message

    @staticmethod
    def _video_file(message: Any) -> tuple[types.Document, Any]:
        document = getattr(message, "document", None)
        media_file = getattr(message, "file", None)
        mime_type = str(getattr(media_file, "mime_type", "") or "")
        if not isinstance(document, types.Document) or not mime_type.startswith("video/"):
            raise TelegramPreviewError("video_not_supported", "Message does not contain a playable video")
        if not document.file_reference:
            raise TelegramPreviewError("video_reference_missing", "Telegram video reference is unavailable")
        return document, media_file

    @staticmethod
    async def _permanent_sender(client: Any, dc_id: int) -> tuple[Any, bool]:
        """Return an authorized sender for the target DC and whether it was borrowed."""
        if int(client.session.dc_id) == dc_id:
            sender = client._sender
            if sender is None or not sender.auth_key:
                raise RuntimeError("Telegram client has no active permanent auth key")
            return sender, False
        return await client._borrow_exported_sender(dc_id), True

    @staticmethod
    async def _return_permanent_sender(client: Any, sender: Any, borrowed: bool) -> None:
        if not borrowed:
            return
        return_sender = getattr(client, "_return_exported_sender", None)
        if return_sender is not None:
            await return_sender(sender)

    async def issue_video_ticket(
        self,
        *,
        account_id: str,
        chat_id: int,
        message_id: int,
    ) -> dict[str, Any]:
        client = self._client(account_id)
        message = await self._message(client, chat_id, message_id)
        document, media_file = self._video_file(message)
        dc_id = int(document.dc_id)
        if dc_id not in DC_WEB_HOSTS:
            raise TelegramPreviewError("video_dc_unsupported", "Telegram video DC is not supported")
        api_id = self.config.api_id
        if not api_id or not self.config.api_hash:
            raise TelegramPreviewError("telegram_api_credentials_missing", "Telegram API credentials are not configured")

        # Borrowing an exported sender creates the permanent authorization key
        # on a media DC without copying the account's main session to the page.
        permanent_sender = None
        permanent_sender_borrowed = False
        stage = "select_permanent_sender"
        try:
            permanent_sender, permanent_sender_borrowed = await self._permanent_sender(client, dc_id)
            auth_key = bytes(permanent_sender.auth_key.key)
            auth_key_id = _auth_key_id(permanent_sender.auth_key)
            sender_state = permanent_sender._state
            server_salt = int(sender_state.salt)
            time_offset = int(sender_state.time_offset)
        except TelegramPreviewError:
            raise
        except Exception as exc:
            logger.exception(
                "Telegram video ticket preparation failed "
                "(account_id=%s, chat_id=%s, message_id=%s, dc_id=%s, stage=%s, error_type=%s)",
                account_id,
                chat_id,
                message_id,
                dc_id,
                stage,
                type(exc).__name__,
            )
            raise TelegramPreviewError("video_ticket_failed", "Telegram could not prepare video access") from exc
        finally:
            if permanent_sender is not None:
                await self._return_permanent_sender(client, permanent_sender, permanent_sender_borrowed)

        document_location = {
            "id": str(document.id),
            "access_hash": str(document.access_hash),
            "file_reference": _base64(bytes(document.file_reference)),
            "dc_id": dc_id,
            "size": int(getattr(document, "size", 0) or getattr(media_file, "size", 0) or 0),
        }
        mime_type = str(getattr(media_file, "mime_type", "video/mp4") or "video/mp4")
        file_name = str(
            getattr(media_file, "name", None) or f"telegram-{chat_id}-{message_id}.mp4"
        )
        size = document_location["size"] or None
        return {
            "ticket": secrets.token_urlsafe(32),
            "api_id": api_id,
            "api_layer": alltlobjects.LAYER,
            "dc_id": dc_id,
            "dc_address": DC_WEB_HOSTS[dc_id],
            "dc_port": 443,
            "auth_key": _base64(auth_key),
            "auth_key_id": str(auth_key_id),
            "server_salt": str(server_salt),
            "time_offset": time_offset,
            "file": document_location,
            "mime_type": mime_type,
            "file_name": file_name,
            "size": size,
        }

    async def clear_account(self, account_id: str) -> None:
        return None
