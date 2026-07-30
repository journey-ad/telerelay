"""Read-only Telegram dialog and message preview services."""

from __future__ import annotations

import base64
import asyncio
import hashlib
import json
import mimetypes
import os
import shutil
import tempfile
import time
import weakref
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from telethon import utils
from telethon.tl import types

from backend.events import EventBus


class TelegramPreviewError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _date_text(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat(timespec="seconds")


def _display_name(entity: Any) -> str:
    if entity is None:
        return ""
    title = getattr(entity, "title", None)
    if title:
        return str(title)
    name = " ".join(
        str(part)
        for part in (
            getattr(entity, "first_name", None),
            getattr(entity, "last_name", None),
        )
        if part
    )
    username = getattr(entity, "username", None)
    return name or (f"@{username}" if username else "") or str(getattr(entity, "id", ""))


def _peer_id(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(utils.get_peer_id(value))
    except (AttributeError, TypeError, ValueError):
        pass
    for field in ("user_id", "chat_id", "channel_id", "id"):
        peer_id = getattr(value, field, None)
        if peer_id is not None:
            return int(peer_id)
    return None


def _chat_kind(entity: Any) -> str:
    if isinstance(entity, types.User):
        return "bot" if getattr(entity, "bot", False) else "private"
    if isinstance(entity, types.Chat):
        return "group"
    if isinstance(entity, types.Channel) and getattr(entity, "megagroup", False):
        return "supergroup"
    if isinstance(entity, types.Channel):
        return "channel"
    if getattr(entity, "first_name", None) is not None:
        return "bot" if getattr(entity, "bot", False) else "private"
    if getattr(entity, "megagroup", False):
        return "supergroup"
    return "channel" if getattr(entity, "broadcast", False) else "group"


def _media_type(message: Any) -> str:
    if getattr(message, "action", None) is not None:
        return "service"
    if not getattr(message, "media", None):
        return "text"
    if getattr(message, "photo", None):
        return "photo"
    if getattr(message, "gif", None):
        return "animation"
    if getattr(message, "video_note", None):
        return "video_note"
    if getattr(message, "video", None):
        return "video"
    if getattr(message, "voice", None):
        return "voice"
    if getattr(message, "audio", None):
        return "audio"
    if getattr(message, "sticker", None):
        return "sticker"
    if getattr(message, "document", None):
        return "document"
    media = getattr(message, "media", None)
    if isinstance(media, types.MessageMediaContact):
        return "contact"
    if isinstance(media, types.MessageMediaPoll):
        return "poll"
    if isinstance(media, (types.MessageMediaGeo, types.MessageMediaGeoLive)):
        return "location"
    return "media"


def _media_label(kind: str) -> str:
    return {
        "photo": "图片",
        "animation": "动图",
        "video_note": "视频消息",
        "video": "视频",
        "voice": "语音",
        "audio": "音频",
        "sticker": "贴纸",
        "document": "文件",
        "contact": "联系人",
        "poll": "投票",
        "location": "位置",
        "service": "服务消息",
        "media": "媒体",
    }.get(kind, "消息")


def _stripped_thumbnail(content: bytes | None) -> str | None:
    if not content or len(content) > 8 * 1024:
        return None
    try:
        image = utils.stripped_photo_to_jpg(content)
    except (TypeError, ValueError):
        return None
    encoded = base64.b64encode(image).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


class TelegramPreviewService:
    """Expose Telegram data without changing read state or sending messages."""

    CACHE_MAX_BYTES = 128 * 1024 * 1024
    AVATAR_MAX_AGE = 6 * 60 * 60
    THUMBNAIL_MAX_AGE = 7 * 24 * 60 * 60

    def __init__(self, bot_manager: Any, account_store: Any, events: EventBus):
        self.bot_manager = bot_manager
        self.account_store = account_store
        self.events = events
        self.cache_root = Path(account_store.data_dir) / "telegram_preview_cache"
        self._cache_locks: weakref.WeakValueDictionary[Path, asyncio.Lock] = (
            weakref.WeakValueDictionary()
        )
        self._last_cache_prune = 0.0

    def _active_account(self, account_id: str | None = None) -> str:
        active_id = self.account_store.active_account_id
        if account_id is not None and account_id != active_id:
            raise TelegramPreviewError(
                "inactive_account",
                "The requested Telegram account is no longer active",
            )
        return active_id

    def _client(self, account_id: str | None = None):
        self._active_account(account_id)
        manager = self.bot_manager.client_manager
        client = manager.get_client() if manager else None
        if not self.bot_manager.is_connected or client is None:
            raise TelegramPreviewError(
                "telegram_not_connected",
                "The active Telegram account is not connected",
            )
        return client

    async def list_dialogs(
        self,
        *,
        account_id: str | None,
        folder: str,
        limit: int,
        cursor: str | None,
    ) -> dict[str, Any]:
        active_id = self._active_account(account_id)
        client = self._client(active_id)
        options: dict[str, Any] = {
            "limit": limit + 1,
            "archived": folder == "archived",
        }
        if cursor:
            cursor_data = self._decode_cursor(cursor, active_id, folder)
            options.update(
                offset_date=cursor_data["date"],
                offset_id=cursor_data["message_id"],
                offset_peer=await client.get_input_entity(cursor_data["peer_id"]),
                ignore_pinned=True,
            )

        dialogs = [dialog async for dialog in client.iter_dialogs(**options)]
        has_more = len(dialogs) > limit
        visible = dialogs[:limit]
        return {
            "account_id": active_id,
            "folder": folder,
            "items": [self._dialog_data(dialog) for dialog in visible],
            "next_cursor": (
                self._encode_cursor(active_id, folder, visible[-1])
                if has_more and visible
                else None
            ),
        }

    async def list_messages(
        self,
        *,
        account_id: str,
        chat_id: int,
        limit: int,
        before_id: int | None,
        query: str | None,
    ) -> dict[str, Any]:
        client = self._client(account_id)
        try:
            entity = await client.get_entity(chat_id)
        except Exception as exc:
            raise TelegramPreviewError("chat_not_found", "Telegram chat was not found") from exc

        options: dict[str, Any] = {"limit": limit + 1}
        if before_id:
            options["max_id"] = before_id
        if query:
            options["search"] = query
        messages = [message async for message in client.iter_messages(entity, **options)]
        has_more = len(messages) > limit
        visible = messages[:limit]

        reply_ids = {
            int(reply_id)
            for message in visible
            if (reply_id := getattr(message, "reply_to_msg_id", None)) is not None
        }
        replies: dict[int, Any] = {}
        if reply_ids:
            reply_messages = await client.get_messages(entity, ids=sorted(reply_ids))
            if not isinstance(reply_messages, (list, tuple)):
                reply_messages = [reply_messages]
            replies = {
                int(message.id): message
                for message in reply_messages
                if message is not None
            }

        serialized = [
            await self._message_data(message, chat_id, replies=replies)
            for message in visible
        ]
        serialized.reverse()
        return {
            "account_id": account_id,
            "chat": self._chat_data(entity),
            "query": query or None,
            "items": serialized,
            "next_before_id": int(visible[-1].id) if has_more and visible else None,
        }

    async def get_message(
        self,
        *,
        account_id: str,
        chat_id: int,
        message_id: int,
    ) -> dict[str, Any]:
        client, message = await self._message(
            client_account=account_id,
            chat_id=chat_id,
            message_id=message_id,
        )
        reply_id = getattr(message, "reply_to_msg_id", None)
        replies: dict[int, Any] = {}
        if reply_id:
            reply = await client.get_messages(chat_id, ids=int(reply_id))
            if reply is not None:
                replies[int(reply.id)] = reply
        return await self._message_data(message, chat_id, replies=replies)

    async def avatar(self, *, account_id: str, peer_id: int) -> bytes:
        async def load() -> bytes:
            client = self._client(account_id)
            try:
                entity = await client.get_entity(peer_id)
                content = await client.download_profile_photo(
                    entity,
                    file=bytes,
                    download_big=False,
                )
            except Exception as exc:
                raise TelegramPreviewError(
                    "avatar_not_found", "Telegram avatar was not found"
                ) from exc
            if not content:
                raise TelegramPreviewError(
                    "avatar_not_found", "Telegram avatar was not found"
                )
            return bytes(content)

        return await self._cached_bytes(
            self._cache_path(account_id, "avatars", f"{peer_id}.jpg"),
            self.AVATAR_MAX_AGE,
            load,
        )

    async def media_thumbnail(
        self,
        *,
        account_id: str,
        chat_id: int,
        message_id: int,
    ) -> tuple[bytes, str]:
        async def load() -> bytes:
            client, message = await self._message(
                client_account=account_id,
                chat_id=chat_id,
                message_id=message_id,
            )
            if not self._has_thumbnail(message):
                raise TelegramPreviewError(
                    "thumbnail_not_found", "Message has no image thumbnail"
                )
            try:
                content = await client.download_media(
                    message,
                    file=bytes,
                    thumb=self._thumbnail(message),
                )
            except Exception as exc:
                raise TelegramPreviewError(
                    "thumbnail_not_found", "Message thumbnail is unavailable"
                ) from exc
            if not content:
                raise TelegramPreviewError(
                    "thumbnail_not_found", "Message thumbnail is unavailable"
                )
            return bytes(content)

        content = await self._cached_bytes(
            self._cache_path(
                account_id,
                "thumbnails",
                f"{chat_id}-{message_id}.jpg",
            ),
            self.THUMBNAIL_MAX_AGE,
            load,
        )
        return content, "image/jpeg"

    async def clear_account_cache(self, account_id: str) -> None:
        path = self._account_cache_path(account_id)
        await asyncio.to_thread(shutil.rmtree, path, True)

    async def download_media(
        self,
        *,
        account_id: str,
        chat_id: int,
        message_id: int,
    ) -> tuple[Path, str, str]:
        client, message = await self._message(client_account=account_id, chat_id=chat_id, message_id=message_id)
        if not getattr(message, "media", None) or _media_type(message) == "service":
            raise TelegramPreviewError("media_not_found", "Message has no downloadable media")

        media = self._media_data(message)
        filename = media["file_name"] or f"telegram-{chat_id}-{message_id}"
        suffix = Path(filename).suffix
        file_descriptor, temporary_name = tempfile.mkstemp(prefix="telerelay-media-", suffix=suffix)
        os.close(file_descriptor)
        try:
            downloaded = await client.download_media(message, file=temporary_name)
        except Exception as exc:
            Path(temporary_name).unlink(missing_ok=True)
            raise TelegramPreviewError("media_download_failed", "Telegram media download failed") from exc
        path = Path(downloaded or temporary_name)
        if not path.is_file() or not path.stat().st_size:
            path.unlink(missing_ok=True)
            raise TelegramPreviewError("media_not_found", "Telegram media is unavailable")
        mime_type = media["mime_type"] or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        return path, mime_type, Path(filename).name

    async def handle_new_message(self, event: Any) -> None:
        """Publish a compact live event without acknowledging the message as read."""
        try:
            account_id = self._active_account()
            message = event.message
            chat_id = int(event.chat_id)
            data = await self._message_data(
                message,
                chat_id,
                sender=getattr(event, "sender", None),
                resolve_sender=False,
            )
            self.events.publish(
                "telegram-preview-message",
                {
                    "account_id": account_id,
                    "chat_id": chat_id,
                    "message": data,
                },
            )
        except Exception:
            # Preview events must never interfere with forwarding handlers.
            return

    async def _message(self, *, client_account: str, chat_id: int, message_id: int):
        client = self._client(client_account)
        try:
            message = await client.get_messages(chat_id, ids=message_id)
        except Exception as exc:
            raise TelegramPreviewError("message_not_found", "Telegram message was not found") from exc
        if message is None:
            raise TelegramPreviewError("message_not_found", "Telegram message was not found")
        return client, message

    def _account_cache_path(self, account_id: str) -> Path:
        digest = hashlib.sha256(account_id.encode("utf-8")).hexdigest()[:20]
        return self.cache_root / digest

    def _cache_path(self, account_id: str, category: str, filename: str) -> Path:
        return self._account_cache_path(account_id) / category / filename

    async def _cached_bytes(self, path: Path, max_age: int, loader) -> bytes:
        cached = await asyncio.to_thread(self._read_cache, path, max_age)
        if cached is not None:
            return cached

        lock = self._cache_locks.setdefault(path, asyncio.Lock())
        async with lock:
            cached = await asyncio.to_thread(self._read_cache, path, max_age)
            if cached is not None:
                return cached
            content = await loader()
            await asyncio.to_thread(self._write_cache, path, content)
            return content

    @staticmethod
    def _read_cache(path: Path, max_age: int) -> bytes | None:
        try:
            stat = path.stat()
            if time.time() - stat.st_mtime > max_age:
                path.unlink(missing_ok=True)
                return None
            content = path.read_bytes()
            os.utime(path, (time.time(), stat.st_mtime))
            return content or None
        except OSError:
            return None

    def _write_cache(self, path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}-",
            suffix=".tmp",
            dir=path.parent,
        )
        try:
            with os.fdopen(file_descriptor, "wb") as handle:
                handle.write(content)
            os.replace(temporary_name, path)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)
        self._prune_cache()

    def _prune_cache(self) -> None:
        now = time.monotonic()
        if now - self._last_cache_prune < 60:
            return
        self._last_cache_prune = now
        try:
            files = [path for path in self.cache_root.rglob("*") if path.is_file()]
            entries = [(path, path.stat()) for path in files]
        except OSError:
            return
        total = sum(stat.st_size for _, stat in entries)
        if total <= self.CACHE_MAX_BYTES:
            return
        for path, stat in sorted(entries, key=lambda item: item[1].st_atime):
            path.unlink(missing_ok=True)
            total -= stat.st_size
            if total <= self.CACHE_MAX_BYTES:
                break

    def _dialog_data(self, dialog: Any) -> dict[str, Any]:
        entity = dialog.entity
        chat_id = _peer_id(entity)
        if chat_id is None:
            raise TelegramPreviewError("invalid_dialog", "Telegram dialog has no peer ID")
        message = getattr(dialog, "message", None)
        return {
            **self._chat_data(entity),
            "id": chat_id,
            "archived": getattr(dialog, "folder_id", None) == 1,
            "pinned": bool(getattr(dialog, "pinned", False)),
            "unread_count": int(getattr(dialog, "unread_count", 0) or 0),
            "unread_mentions_count": int(
                getattr(dialog, "unread_mentions_count", 0) or 0
            ),
            "last_message": self._message_summary(message, chat_id) if message else None,
        }

    def _chat_data(self, entity: Any) -> dict[str, Any]:
        chat_id = _peer_id(entity)
        if chat_id is None:
            raise TelegramPreviewError("invalid_dialog", "Telegram chat has no peer ID")
        return {
            "id": chat_id,
            "title": _display_name(entity) or str(chat_id),
            "kind": _chat_kind(entity),
            "username": getattr(entity, "username", None),
            "is_self": bool(getattr(entity, "is_self", False)),
            "verified": bool(getattr(entity, "verified", False)),
            "inline_avatar": _stripped_thumbnail(
                getattr(getattr(entity, "photo", None), "stripped_thumb", None)
            ),
        }

    def _message_summary(self, message: Any, chat_id: int) -> dict[str, Any]:
        kind = _media_type(message)
        text = getattr(message, "raw_text", None) or getattr(message, "text", None) or ""
        return {
            "id": int(message.id),
            "chat_id": chat_id,
            "date": _date_text(getattr(message, "date", None)),
            "text": text,
            "media_type": kind,
            "preview": text or f"[{_media_label(kind)}]",
            "outgoing": bool(getattr(message, "out", False)),
        }

    async def _message_data(
        self,
        message: Any,
        chat_id: int,
        *,
        replies: dict[int, Any] | None = None,
        sender: Any = None,
        resolve_sender: bool = True,
    ) -> dict[str, Any]:
        sender = sender or getattr(message, "sender", None)
        if resolve_sender and sender is None and getattr(message, "sender_id", None):
            try:
                sender = await message.get_sender()
            except Exception:
                sender = None
        sender_id = _peer_id(sender) or getattr(message, "sender_id", None)
        reply_id = getattr(message, "reply_to_msg_id", None)
        reply = (replies or {}).get(int(reply_id)) if reply_id else None
        forward = getattr(message, "forward", None)
        forward_entity = (
            getattr(forward, "sender", None) or getattr(forward, "chat", None)
            if forward is not None
            else None
        )
        forward_header = getattr(message, "fwd_from", None)
        forward_name = (
            _display_name(forward_entity)
            or getattr(forward, "sender_name", None)
            or getattr(forward_header, "from_name", None)
        )
        text = getattr(message, "raw_text", None) or getattr(message, "text", None) or ""
        media = self._media_data(message)
        return {
            "id": int(message.id),
            "chat_id": int(chat_id),
            "date": _date_text(getattr(message, "date", None)),
            "sender": {
                "id": int(sender_id) if sender_id is not None else None,
                "name": _display_name(sender) or (str(sender_id) if sender_id else "Telegram"),
                "username": getattr(sender, "username", None) if sender else None,
            },
            "text": text,
            "media": media,
            "reply_to": (
                self._reply_data(reply, int(reply_id)) if reply_id else None
            ),
            "forward": (
                {
                    "from_id": _peer_id(forward_entity)
                    or _peer_id(getattr(forward_header, "from_id", None)),
                    "from_name": forward_name or "Telegram",
                    "date": _date_text(
                        getattr(forward, "date", None)
                        or getattr(forward_header, "date", None)
                    ),
                }
                if forward is not None or forward_header is not None
                else None
            ),
            "grouped_id": (
                int(message.grouped_id) if getattr(message, "grouped_id", None) else None
            ),
            "edited_at": _date_text(getattr(message, "edit_date", None)),
            "outgoing": bool(getattr(message, "out", False)),
            "post_author": getattr(message, "post_author", None),
            "views": getattr(message, "views", None),
            "reactions": self._reactions(message),
            "service_action": (
                type(message.action).__name__ if getattr(message, "action", None) else None
            ),
        }

    def _reply_data(self, reply: Any, message_id: int) -> dict[str, Any]:
        if reply is None:
            return {
                "message_id": message_id,
                "sender_name": None,
                "text": "原消息不可用",
                "media_type": None,
            }
        sender = getattr(reply, "sender", None)
        kind = _media_type(reply)
        text = getattr(reply, "raw_text", None) or getattr(reply, "text", None) or ""
        return {
            "message_id": int(reply.id),
            "sender_name": _display_name(sender) or None,
            "text": text or f"[{_media_label(kind)}]",
            "media_type": kind,
        }

    def _media_data(self, message: Any) -> dict[str, Any] | None:
        kind = _media_type(message)
        if kind in {"text", "service"}:
            return None
        message_file = getattr(message, "file", None)
        file_name = getattr(message_file, "name", None)
        mime_type = getattr(message_file, "mime_type", None)
        width, height = self._media_dimensions(message)
        return {
            "type": kind,
            "file_name": Path(file_name).name if file_name else None,
            "mime_type": mime_type,
            "size": getattr(message_file, "size", None),
            "duration": getattr(message_file, "duration", None),
            "width": width,
            "height": height,
            "has_thumbnail": self._has_thumbnail(message),
            "inline_thumbnail": self._inline_thumbnail(message),
            "downloadable": bool(getattr(message, "media", None)),
        }

    @staticmethod
    def _media_dimensions(message: Any) -> tuple[int | None, int | None]:
        photo = getattr(message, "photo", None)
        photo_sizes = getattr(photo, "sizes", None) or []
        dimensions = [
            (int(size.w), int(size.h))
            for size in photo_sizes
            if int(getattr(size, "w", 0) or 0) > 0
            and int(getattr(size, "h", 0) or 0) > 0
        ]
        if dimensions:
            return max(dimensions, key=lambda value: value[0] * value[1])

        document = getattr(message, "document", None)
        attributes = getattr(document, "attributes", None) or []
        dimensions = [
            (int(attribute.w), int(attribute.h))
            for attribute in attributes
            if isinstance(
                attribute,
                (types.DocumentAttributeImageSize, types.DocumentAttributeVideo),
            )
            and int(getattr(attribute, "w", 0) or 0) > 0
            and int(getattr(attribute, "h", 0) or 0) > 0
        ]
        if dimensions:
            return max(dimensions, key=lambda value: value[0] * value[1])
        return None, None

    @staticmethod
    def _inline_thumbnail(message: Any) -> str | None:
        photo = getattr(message, "photo", None)
        document = getattr(message, "document", None)
        sizes = list(
            getattr(photo, "sizes", None)
            or getattr(document, "thumbs", None)
            or []
        )
        for size in sizes:
            if not isinstance(size, (types.PhotoStrippedSize, types.PhotoCachedSize)):
                continue
            content = getattr(size, "bytes", None)
            if not content or len(content) > 8 * 1024:
                continue
            if isinstance(size, types.PhotoStrippedSize):
                return _stripped_thumbnail(content)
            encoded = base64.b64encode(bytes(content)).decode("ascii")
            return f"data:image/jpeg;base64,{encoded}"
        return None

    @staticmethod
    def _has_thumbnail(message: Any) -> bool:
        if getattr(message, "photo", None):
            return True
        mime_type = getattr(getattr(message, "file", None), "mime_type", "") or ""
        return bool(getattr(message, "document", None) and mime_type.startswith("image/"))

    @staticmethod
    def _thumbnail(message: Any):
        photo = getattr(message, "photo", None)
        document = getattr(message, "document", None)
        sizes = list(
            getattr(photo, "sizes", None)
            or getattr(document, "thumbs", None)
            or []
        )
        usable = [
            size
            for size in sizes
            if not isinstance(size, (types.PhotoStrippedSize, types.PhotoPathSize))
        ]
        if not usable:
            return -1
        within_preview = [
            size
            for size in usable
            if max(getattr(size, "w", 0), getattr(size, "h", 0)) <= 640
        ]
        return max(
            within_preview or usable,
            key=lambda size: getattr(size, "w", 0) * getattr(size, "h", 0),
        )

    @staticmethod
    def _reactions(message: Any) -> list[dict[str, Any]]:
        reactions = getattr(getattr(message, "reactions", None), "results", None) or []
        result = []
        for item in reactions:
            reaction = getattr(item, "reaction", None)
            if isinstance(reaction, types.ReactionEmoji):
                label = reaction.emoticon
            elif isinstance(reaction, types.ReactionPaid):
                label = "⭐"
            elif isinstance(reaction, types.ReactionCustomEmoji):
                label = "自定义"
            else:
                label = "回应"
            result.append(
                {
                    "label": label,
                    "count": int(getattr(item, "count", 0) or 0),
                    "chosen": getattr(item, "chosen_order", None) is not None,
                }
            )
        return result

    @staticmethod
    def _encode_cursor(account_id: str, folder: str, dialog: Any) -> str:
        message = getattr(dialog, "message", None)
        payload = {
            "account_id": account_id,
            "folder": folder,
            "peer_id": _peer_id(dialog.entity),
            "message_id": int(getattr(message, "id", 0) or 0),
            "date": _date_text(getattr(message, "date", None)),
        }
        encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(encoded).decode("ascii").rstrip("=")

    @staticmethod
    def _decode_cursor(cursor: str, account_id: str, folder: str) -> dict[str, Any]:
        try:
            padding = "=" * (-len(cursor) % 4)
            payload = json.loads(base64.urlsafe_b64decode(cursor + padding))
            if payload["account_id"] != account_id or payload["folder"] != folder:
                raise ValueError
            date = datetime.fromisoformat(payload["date"]) if payload.get("date") else None
            return {
                "peer_id": int(payload["peer_id"]),
                "message_id": int(payload["message_id"]),
                "date": date,
            }
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise TelegramPreviewError("invalid_cursor", "Dialog cursor is invalid") from exc
