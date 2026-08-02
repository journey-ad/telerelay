"""Read-only Telegram dialog and message preview services."""

from __future__ import annotations

import asyncio
import base64
import hmac
import json
import mimetypes
import os
import secrets
import shutil
import tempfile
import threading
import time
import weakref
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from telethon import utils
from telethon.tl import types

from backend.telegram_accounts import TelegramAccountError


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


def _text_with_entities(value: Any) -> str:
    if value is None:
        return ""
    return str(getattr(value, "text", value) or "")


def _poll_question(message: Any) -> str:
    media = getattr(message, "media", None)
    if not isinstance(media, types.MessageMediaPoll):
        return ""
    return _text_with_entities(getattr(media.poll, "question", None))


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
    CACHE_MAGIC = b"TPXC1"
    CACHE_KEY_BYTES = 32
    CACHE_TAG_BYTES = 16

    def __init__(self, bot_manager: Any, account_store: Any):
        self.bot_manager = bot_manager
        self.account_store = account_store
        self._cache_keys: dict[Path, bytes] = {}
        self._cache_key_lock = threading.Lock()
        self._cache_locks: weakref.WeakValueDictionary[Path, asyncio.Lock] = (
            weakref.WeakValueDictionary()
        )
        self._last_cache_prune: dict[Path, float] = {}

    def _active_account(self, account_id: str | None = None) -> str:
        target = account_id or self.account_store.active_account_id
        try:
            self.account_store.get_public(target)
        except TelegramAccountError as exc:
            raise TelegramPreviewError(
                "account_not_found",
                "Telegram account does not exist",
            ) from exc
        return target

    def _client(self, account_id: str | None = None):
        target = self._active_account(account_id)
        try:
            runtime = self.bot_manager.get_runtime(target)
        except TelegramAccountError as exc:
            raise TelegramPreviewError(exc.code, str(exc)) from exc
        manager = runtime.client_manager
        client = manager.get_client() if manager else None
        if not runtime.is_connected or client is None:
            raise TelegramPreviewError(
                "telegram_not_connected",
                "The requested Telegram account is not connected",
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
            "ignore_pinned": folder == "archived",
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
            thumbnail = self._thumbnail(message)
            if thumbnail is None:
                raise TelegramPreviewError(
                    "thumbnail_not_found", "Message has no image thumbnail"
                )
            try:
                content = await client.download_media(
                    message,
                    file=bytes,
                    thumb=thumbnail,
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
        try:
            path = self._account_cache_path_unchecked(account_id)
        except ValueError:
            return
        await asyncio.to_thread(shutil.rmtree, path, True)
        with self._cache_key_lock:
            self._cache_keys.pop(path, None)
        self._last_cache_prune.pop(path, None)

    async def download_visual_media(
        self,
        *,
        account_id: str,
        chat_id: int,
        message_id: int,
    ) -> tuple[Path, str, str]:
        client, message = await self._message(
            client_account=account_id,
            chat_id=chat_id,
            message_id=message_id,
        )
        if not self._is_visual_media(message):
            raise TelegramPreviewError(
                "visual_media_not_found",
                "Message does not contain a downloadable image, GIF, or sticker",
            )

        media = self._media_data(message)
        mime_type = media["mime_type"] or (
            "image/gif"
            if media["type"] == "animation"
            else "application/x-tgsticker"
            if media["type"] == "sticker"
            else "image/jpeg"
        )
        filename = media["file_name"] or f"telegram-{chat_id}-{message_id}"
        default_suffix = {
            "animation": ".gif",
            "sticker": ".tgs",
        }.get(media["type"], ".jpg")
        suffix = (
            Path(filename).suffix
            or mimetypes.guess_extension(mime_type)
            or default_suffix
        )
        if not Path(filename).suffix:
            filename += suffix
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix="telerelay-visual-",
            suffix=suffix,
        )
        os.close(file_descriptor)
        try:
            downloaded = await client.download_media(message, file=temporary_name)
        except Exception as exc:
            Path(temporary_name).unlink(missing_ok=True)
            raise TelegramPreviewError(
                "visual_media_download_failed",
                "Telegram visual media download failed",
            ) from exc
        path = Path(downloaded or temporary_name)
        temporary_path = Path(temporary_name)
        if path != temporary_path:
            temporary_path.unlink(missing_ok=True)
        if not path.is_file() or not path.stat().st_size:
            path.unlink(missing_ok=True)
            raise TelegramPreviewError(
                "visual_media_not_found",
                "Telegram visual media is unavailable",
            )
        return path, mime_type, Path(filename).name

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
        target = self._active_account(account_id)
        try:
            return self._account_cache_path_unchecked(target)
        except ValueError as exc:
            raise TelegramPreviewError(
                "account_not_authenticated",
                "Telegram account must be authenticated first",
            ) from exc

    def _account_cache_path_unchecked(self, account_id: str) -> Path:
        paths = getattr(self.account_store, "paths", None)
        if paths is not None:
            account_data_dir = paths.for_account(account_id).data_dir
        else:
            account_data_dir = Path(self.account_store.data_dir) / account_id
        return account_data_dir / "telegram_preview_cache"

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

    def _read_cache(self, path: Path, max_age: int) -> bytes | None:
        try:
            stat = path.stat()
            if time.time() - stat.st_mtime > max_age:
                path.unlink(missing_ok=True)
                return None
            stored = path.read_bytes()
            if not stored.startswith(self.CACHE_MAGIC):
                path.unlink(missing_ok=True)
                return None
            cache_root = path.parents[1]
            key = self._cache_keys.get(cache_root)
            if key is None:
                key_path = cache_root.parent / ".telegram_preview_cache.key"
                if not key_path.is_file():
                    return None
                key = self._cache_key(cache_root)
            content = self._decrypt_cache(stored, key)
            if content is None:
                path.unlink(missing_ok=True)
                return None
            os.utime(path, (time.time(), stat.st_mtime))
            return content or None
        except OSError:
            return None

    def _write_cache(self, path: Path, content: bytes) -> None:
        key = self._cache_key(path.parents[1])
        path.parent.mkdir(parents=True, exist_ok=True)
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}-",
            suffix=".tmp",
            dir=path.parent,
        )
        try:
            with os.fdopen(file_descriptor, "wb") as handle:
                handle.write(self._encrypt_cache(content, key))
            os.replace(temporary_name, path)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)
        self._prune_cache(path.parents[1])

    def _cache_key(self, cache_root: Path) -> bytes:
        with self._cache_key_lock:
            key = self._cache_keys.get(cache_root)
            if key is not None:
                return key
            key, created = self._load_or_create_cache_key(cache_root)
            if created:
                shutil.rmtree(cache_root, ignore_errors=True)
            self._cache_keys[cache_root] = key
            return key

    def _load_or_create_cache_key(self, cache_root: Path) -> tuple[bytes, bool]:
        cache_key_path = cache_root.parent / ".telegram_preview_cache.key"
        try:
            key = cache_key_path.read_bytes()
            created = False
        except FileNotFoundError:
            key = secrets.token_bytes(self.CACHE_KEY_BYTES)
            created = True
            cache_key_path.parent.mkdir(parents=True, exist_ok=True)
            file_descriptor = os.open(
                cache_key_path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
            try:
                with os.fdopen(file_descriptor, "wb") as handle:
                    handle.write(key)
                    handle.flush()
                    os.fsync(handle.fileno())
            except Exception:
                cache_key_path.unlink(missing_ok=True)
                raise
        if len(key) != self.CACHE_KEY_BYTES:
            raise RuntimeError("Telegram preview cache key is invalid")
        try:
            cache_key_path.chmod(0o600)
        except OSError:
            pass
        return key, created

    def _encrypt_cache(self, content: bytes, key: bytes) -> bytes:
        encrypted = self._xor_cache(content, key)
        tag = hmac.digest(
            key,
            self.CACHE_MAGIC + encrypted,
            "sha256",
        )[: self.CACHE_TAG_BYTES]
        return self.CACHE_MAGIC + tag + encrypted

    def _decrypt_cache(self, stored: bytes, key: bytes) -> bytes | None:
        header_size = len(self.CACHE_MAGIC) + self.CACHE_TAG_BYTES
        if len(stored) <= header_size:
            return None
        tag_start = len(self.CACHE_MAGIC)
        content_start = tag_start + self.CACHE_TAG_BYTES
        tag = stored[tag_start:content_start]
        encrypted = stored[content_start:]
        expected = hmac.digest(
            key,
            self.CACHE_MAGIC + encrypted,
            "sha256",
        )[: self.CACHE_TAG_BYTES]
        if not hmac.compare_digest(tag, expected):
            return None
        return self._xor_cache(encrypted, key)

    @staticmethod
    def _xor_cache(content: bytes, key: bytes) -> bytes:
        key_size = len(key)
        return bytes(
            value ^ key[index % key_size]
            for index, value in enumerate(content)
        )

    def _prune_cache(self, cache_root: Path) -> None:
        now = time.monotonic()
        if now - self._last_cache_prune.get(cache_root, 0.0) < 60:
            return
        self._last_cache_prune[cache_root] = now
        try:
            files = [path for path in cache_root.rglob("*") if path.is_file()]
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
        preview = _poll_question(message) or text or f"[{_media_label(kind)}]"
        return {
            "id": int(message.id),
            "chat_id": chat_id,
            "date": _date_text(getattr(message, "date", None)),
            "text": text,
            "media_type": kind,
            "preview": preview,
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
            "text": _poll_question(reply) or text or f"[{_media_label(kind)}]",
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
            "is_visual_media": self._is_visual_media(message),
            "has_thumbnail": self._has_thumbnail(message),
            "inline_thumbnail": self._inline_thumbnail(message),
            "poll": self._poll_data(message),
        }

    @staticmethod
    def _poll_data(message: Any) -> dict[str, Any] | None:
        media = getattr(message, "media", None)
        if not isinstance(media, types.MessageMediaPoll):
            return None
        poll = media.poll
        results = media.results
        result_items = list(getattr(results, "results", None) or [])
        result_by_option = {
            bytes(item.option): item
            for item in result_items
            if getattr(item, "option", None) is not None
        }
        options = []
        for answer in poll.answers:
            result = result_by_option.get(bytes(answer.option))
            options.append(
                {
                    "text": _text_with_entities(answer.text),
                    "voters": int(getattr(result, "voters", 0) or 0),
                    "chosen": bool(getattr(result, "chosen", False)),
                    "correct": bool(getattr(result, "correct", False)),
                }
            )
        return {
            "question": _text_with_entities(poll.question),
            "options": options,
            "results_visible": bool(result_items),
            "total_voters": int(getattr(results, "total_voters", 0) or 0),
            "multiple_choice": bool(getattr(poll, "multiple_choice", False)),
            "quiz": bool(getattr(poll, "quiz", False)),
            "closed": bool(getattr(poll, "closed", False)),
            "solution": getattr(results, "solution", None) or None,
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
        return bool(
            TelegramPreviewService._is_visual_media(message)
            and (
                TelegramPreviewService._inline_thumbnail(message)
                or TelegramPreviewService._thumbnail(message) is not None
            )
        )

    @staticmethod
    def _is_visual_media(message: Any) -> bool:
        if (
            getattr(message, "photo", None)
            or getattr(message, "gif", None)
            or getattr(message, "sticker", None)
        ):
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
            return None
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
