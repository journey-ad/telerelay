"""Browser-direct Telegram media authorization.

This module delivers the target DC authorization state to an in-memory browser
worker; Telegram file bytes never enter this process. Tickets cover any
message media (documents, photos, thumbnails) and peer avatars.
"""

from __future__ import annotations

import base64
import secrets
from typing import Any

from telethon.crypto import AuthKey
from telethon.tl import alltlobjects, types

from backend.logger import get_logger
from backend.telegram_accounts import TelegramAccountError
from backend.telegram_preview import TelegramPreviewError, resolve_active_account


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


def _photo_size_type(photo: types.Photo, *, thumb: bool) -> str:
    """Pick the PhotoSize type to fetch: a thumbnail or the largest size.

    Photo sizes are separate files selected by their `type` string; the largest
    size is the original image.
    """
    sizes = [
        size
        for size in getattr(photo, "sizes", None) or []
        if isinstance(size, (types.PhotoSize, types.PhotoSizeProgressive))
        and getattr(size, "type", None)
        and int(getattr(size, "w", 0) or 0) > 0
        and int(getattr(size, "h", 0) or 0) > 0
    ]
    if not sizes:
        raise TelegramPreviewError("media_not_supported", "Photo sizes are unavailable")
    if thumb:
        candidates = [size for size in sizes if max(size.w, size.h) <= 640] or sizes
        return max(candidates, key=lambda size: size.w * size.h).type
    return max(sizes, key=lambda size: size.w * size.h).type


def _document_thumb_type(document: types.Document) -> str:
    """Pick the type string of the largest downloadable document thumbnail."""
    sizes = [
        size
        for size in getattr(document, "thumbs", None) or []
        if isinstance(size, (types.PhotoSize, types.PhotoSizeProgressive))
        and getattr(size, "type", None)
    ]
    if not sizes:
        raise TelegramPreviewError("thumbnail_not_found", "Message thumbnail is unavailable")
    return max(
        sizes,
        key=lambda size: int(getattr(size, "w", 0) or 0) * int(getattr(size, "h", 0) or 0),
    ).type


class TelegramResourceService:
    """Issue browser-direct media credentials using Web K's no-PFS path."""

    def __init__(self, bot_manager: Any, account_store: Any, config: Any):
        self.bot_manager = bot_manager
        self.account_store = account_store
        self.config = config

    def _active_account(self, account_id: str | None) -> str:
        return resolve_active_account(self.account_store, account_id)

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
    def _media_location(message: Any, *, thumb: bool) -> tuple[dict[str, Any], str, str]:
        """Resolve the file location of a message's media for browser-direct access.

        Returns (location, mime_type, file_name). The location describes how the
        browser worker should construct the Telegram InputFileLocation: documents
        use InputDocumentFileLocation (empty thumb_size = original file), photos
        use InputPhotoFileLocation with the requested PhotoSize type.
        """
        document = getattr(message, "document", None)
        photo = getattr(message, "photo", None)
        if isinstance(document, types.Document):
            if not document.file_reference:
                raise TelegramPreviewError(
                    "resource_reference_missing", "Telegram file reference is unavailable"
                )
            media_file = getattr(message, "file", None)
            thumb_size = ""
            if thumb:
                thumb_size = _document_thumb_type(document)
            # Thumbnails are JPEG files even when the full document is a video
            # or audio: the worker validates the mime prefix, so reporting the
            # full-file mime would reject the thumbnail bytes as invalid.
            mime_type = (
                "image/jpeg"
                if thumb
                else str(getattr(media_file, "mime_type", "") or "")
                or "application/octet-stream"
            )
            file_name = (
                f"telegram-{message.id}.jpg"
                if thumb
                else str(getattr(media_file, "name", None) or f"telegram-{message.id}")
            )
            return (
                {
                    "location_type": "document",
                    "id": str(document.id),
                    "access_hash": str(document.access_hash),
                    "file_reference": _base64(bytes(document.file_reference)),
                    "dc_id": int(document.dc_id),
                    "size": int(
                        getattr(document, "size", 0)
                        or getattr(media_file, "size", 0)
                        or 0
                    ),
                    "thumb_size": thumb_size,
                },
                mime_type,
                file_name,
            )
        if isinstance(photo, types.Photo):
            if not photo.file_reference:
                raise TelegramPreviewError(
                    "resource_reference_missing", "Telegram file reference is unavailable"
                )
            return (
                {
                    "location_type": "photo",
                    "id": str(photo.id),
                    "access_hash": str(photo.access_hash),
                    "file_reference": _base64(bytes(photo.file_reference)),
                    "dc_id": int(photo.dc_id),
                    "size": 0,
                    "thumb_size": _photo_size_type(photo, thumb=thumb),
                },
                "image/jpeg",
                f"telegram-{message.id}",
            )
        raise TelegramPreviewError(
            "media_not_supported", "Message does not contain a downloadable file"
        )

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

    async def _prepare_credentials(
        self,
        client: Any,
        *,
        account_id: str,
        dc_id: int,
        scope: str,
    ) -> dict[str, Any]:
        """Borrow the target-DC sender and prepare the account-level DC credentials.

        The returned payload (API id/layer, DC endpoint, permanent auth key,
        server salt) is account-wide: the same values are signed for every
        file on that DC, so the browser may cache them per account + DC.
        """
        if dc_id not in DC_WEB_HOSTS:
            raise TelegramPreviewError("resource_dc_unsupported", "Telegram media DC is not supported")
        api_id = self.config.api_id
        if not api_id or not self.config.api_hash:
            raise TelegramPreviewError(
                "telegram_api_credentials_missing", "Telegram API credentials are not configured"
            )

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
                "Telegram media credentials preparation failed "
                "(account_id=%s, dc_id=%s, scope=%s, stage=%s, error_type=%s)",
                account_id,
                dc_id,
                scope,
                stage,
                type(exc).__name__,
            )
            raise TelegramPreviewError("resource_ticket_failed", "Telegram could not prepare media access") from exc
        finally:
            if permanent_sender is not None:
                await self._return_permanent_sender(client, permanent_sender, permanent_sender_borrowed)

        return {
            "api_id": api_id,
            "api_layer": alltlobjects.LAYER,
            "dc_id": dc_id,
            "dc_address": DC_WEB_HOSTS[dc_id],
            "dc_port": 443,
            "auth_key": _base64(auth_key),
            "auth_key_id": str(auth_key_id),
            "server_salt": str(server_salt),
            "time_offset": time_offset,
        }

    async def issue_dc_credentials(
        self,
        *,
        account_id: str,
        dc_id: int,
    ) -> dict[str, Any]:
        """Issue account-level browser-direct credentials for a Telegram DC."""
        client = self._client(account_id)
        return await self._prepare_credentials(
            client,
            account_id=account_id,
            dc_id=dc_id,
            scope=f"dc-{dc_id}",
        )

    async def issue_resource_info(
        self,
        *,
        account_id: str,
        chat_id: int,
        message_id: int,
        thumb: bool = False,
    ) -> dict[str, Any]:
        client = self._client(account_id)
        message = await self._message(client, chat_id, message_id)
        location, mime_type, file_name = self._media_location(message, thumb=thumb)
        return {
            "ticket": secrets.token_urlsafe(32),
            "location_type": location["location_type"],
            "file": location,
            "mime_type": mime_type,
            "file_name": file_name,
            "size": location["size"] or None,
        }

    async def issue_avatar_info(
        self,
        *,
        account_id: str,
        peer_id: int,
    ) -> dict[str, Any]:
        client = self._client(account_id)
        try:
            entity = await client.get_entity(peer_id)
        except Exception as exc:
            raise TelegramPreviewError("peer_not_found", "Telegram peer was not found") from exc
        photo = getattr(entity, "photo", None)
        photo_id = getattr(photo, "photo_id", None)
        if photo_id is None:
            raise TelegramPreviewError("avatar_not_found", "Peer has no avatar")
        dc_id = int(getattr(photo, "dc_id", 0) or 0)
        if not dc_id:
            # Some entities do not carry the photo DC; fall back to the
            # account's home DC (profile photos live on the account DC).
            dc_id = int(getattr(getattr(client, "session", None), "dc_id", 0) or 0)
        if isinstance(entity, types.User):
            peer = {
                "type": "user",
                "id": str(entity.id),
                "access_hash": str(getattr(entity, "access_hash", None) or 0),
            }
        elif isinstance(entity, types.Channel):
            peer = {
                "type": "channel",
                "id": str(entity.id),
                "access_hash": str(getattr(entity, "access_hash", None) or 0),
            }
        else:
            # Plain groups (types.Chat) and unknown entities have no access
            # hash: InputPeerChat only needs the id.
            peer = {"type": "chat", "id": str(entity.id), "access_hash": None}
        location = {
            "location_type": "peer_photo",
            "peer": peer,
            "photo_id": str(photo_id),
            "dc_id": dc_id,
            "size": 0,
        }
        return {
            "ticket": secrets.token_urlsafe(32),
            "location_type": "peer_photo",
            "file": location,
            "mime_type": "image/jpeg",
            "file_name": f"avatar-{peer_id}.jpg",
            "size": None,
            "cache_key": f"avatar-{peer_id}-{photo_id}",
        }
