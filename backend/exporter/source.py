"""Telethon-backed source for group metadata and message history."""

import asyncio
import base64
import queue
import threading
from concurrent.futures import Future
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterator, List, Optional

from telethon import utils
from telethon.tl import types
from telethon.tl.functions.channels import GetFullChannelRequest, GetParticipantRequest
from telethon.tl.functions.messages import GetFullChatRequest, GetHistoryRequest

from backend.i18n import t
from backend.telegram_chats import _chat_validity

from .models import ChatRecord, MessageRecord

_STREAM_END = object()

# Telegram stops reporting the group itself once the account is out; the
# dialog then carries a "forbidden" entity instead of a regular one.
_FORBIDDEN_ENTITIES = (types.ChannelForbidden, types.ChatForbidden)

# Preview length stored for the last message of each chat.
_LAST_MESSAGE_PREVIEW = 200


def _chat_status(entity, validity: Optional[str]) -> str:
    """Usability of a dialog, reusing the chat directory's own vocabulary."""
    if isinstance(entity, _FORBIDDEN_ENTITIES):
        return "blocked"
    if validity:
        return validity
    # Announcement channels only know "no longer active" through deactivated.
    if getattr(entity, "deactivated", False):
        return "deactivated"
    if getattr(entity, "left", False):
        return "left"
    rights = getattr(entity, "banned_rights", None)
    if rights is not None:
        if getattr(rights, "view_messages", False):
            return "blocked"
        if getattr(rights, "send_messages", False):
            return "readonly"
    return "ok"


def _message_preview(message) -> Optional[str]:
    if message is None:
        return None
    text = getattr(message, "message", None) or getattr(message, "text", None)
    if not text:
        return None
    return str(text)[:_LAST_MESSAGE_PREVIEW]


def _date_text(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat(timespec="seconds")


def _display_name(entity) -> str:
    if entity is None:
        return ""
    title = getattr(entity, "title", None)
    if title:
        return title
    name = " ".join(
        part
        for part in (
            getattr(entity, "first_name", None),
            getattr(entity, "last_name", None),
        )
        if part
    )
    return name or str(getattr(entity, "id", ""))


def _chat_kind(entity) -> str:
    if isinstance(entity, types.User) and getattr(entity, "bot", False):
        return "bot"
    if isinstance(entity, types.Chat):
        return "group"
    if isinstance(entity, types.Channel) and getattr(entity, "megagroup", False):
        return "supergroup"
    if isinstance(entity, types.Channel) and getattr(entity, "broadcast", False):
        return "channel"
    return "channel"


def _warning(label: str, error: Exception) -> str:
    detail = str(error).replace("\n", " ").strip()
    if len(detail) > 240:
        detail = detail[:237] + "..."
    return f"{label}: {type(error).__name__}" + (f" ({detail})" if detail else "")


def _tl_data(value):
    """Convert Telethon values into portable JSON-compatible data."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return _date_text(value)
    if isinstance(value, bytes):
        return {"_bytes_base64": base64.b64encode(value).decode("ascii")}
    if isinstance(value, (list, tuple)):
        return [_tl_data(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _tl_data(item) for key, item in value.items()}
    if hasattr(value, "to_dict"):
        return _tl_data(value.to_dict())
    return str(value)


def _peer_id(value) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(utils.get_peer_id(value))
    except (AttributeError, TypeError, ValueError):
        pass
    for name in ("user_id", "chat_id", "channel_id"):
        peer_id = getattr(value, name, None)
        if peer_id is not None:
            return int(peer_id)
    return None


def _sender_type(sender) -> Optional[str]:
    if sender is None:
        return None
    if isinstance(sender, types.User) or hasattr(sender, "first_name"):
        return "user"
    if isinstance(sender, types.Chat):
        return "group"
    if isinstance(sender, types.Channel):
        return "channel"
    return type(sender).__name__.lower()


class TelegramExportSource:
    """Run all Telegram API work on BotManager's owning event loop."""

    def __init__(self, bot_manager):
        self.bot_manager = bot_manager

    def list_chat_records(
        self,
        progress: Optional[Callable[[int, Optional[int]], None]] = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> List[ChatRecord]:
        future = self.bot_manager.submit_telegram(
            self._list_chat_records,
            progress,
            cancel_event,
        )
        return future.result()

    async def _list_chat_records(self, client, progress, cancel_event) -> List[ChatRecord]:
        dialogs = []
        async for dialog in client.iter_dialogs():
            if isinstance(dialog.entity, (types.Chat, types.Channel)):
                dialogs.append(dialog)

        total = len(dialogs)
        records: List[ChatRecord] = []
        for index, dialog in enumerate(dialogs, start=1):
            if cancel_event and cancel_event.is_set():
                break
            try:
                records.append(await self._build_chat_record(client, dialog))
            except Exception as exc:
                # Enrichment is a run of extra per-chat requests, so one chat
                # hitting a rate limit must degrade that row, not the export.
                records.append(self._fallback_chat_record(dialog, exc))
            if progress:
                progress(index, total)

        return sorted(records, key=lambda item: (item.title.casefold(), item.chat_id))

    @staticmethod
    def _fallback_chat_record(dialog, exc: Exception) -> ChatRecord:
        entity = dialog.entity
        username = getattr(entity, "username", None)
        return ChatRecord(
            chat_id=_peer_id(entity),
            title=_display_name(entity) or str(_peer_id(entity)),
            kind=_chat_kind(entity),
            created_at=_date_text(getattr(entity, "date", None)),
            username=username,
            public_link=f"https://t.me/{username}" if username else None,
            is_public=bool(username),
            member_count=None,
            description=None,
            export_warning=_warning(t("export.warning.details"), exc),
            status=_chat_status(entity, _chat_validity(entity)),
            is_archived=bool(getattr(dialog, "archived", False)),
            unread_count=getattr(dialog, "unread_count", None),
            joined_at=None,
            last_message_id=getattr(getattr(dialog, "message", None), "id", None),
            last_message_at=_date_text(getattr(dialog, "date", None)),
            last_message_text=_message_preview(getattr(dialog, "message", None)),
            message_count=None,
        )

    async def _joined_at(self, client, entity, full_chat) -> Optional[str]:
        """When this account joined, which Telegram only reports per participant."""
        if isinstance(entity, types.Channel):
            participant = getattr(full_chat, "participant", None)
            if participant is not None:
                return _date_text(getattr(participant, "date", None))
            try:
                response = await client(
                    GetParticipantRequest(entity, types.InputPeerSelf())
                )
                return _date_text(getattr(response.participant, "date", None))
            except Exception:
                return None
        try:
            me = await client.get_me()
        except Exception:
            return None
        me_id = getattr(me, "id", None)
        participants = getattr(getattr(full_chat, "participants", None), "participants", None)
        for participant in participants or []:
            if getattr(participant, "user_id", None) == me_id:
                return _date_text(getattr(participant, "date", None))
        return None

    @staticmethod
    async def _message_count(client, entity) -> Optional[int]:
        try:
            history = await client(
                GetHistoryRequest(peer=entity, offset_id=0, offset_date=None, add_offset=0,
                                  limit=0, max_id=0, min_id=0, hash=0)
            )
        except Exception:
            return None
        count = getattr(history, "count", None)
        return int(count) if count is not None else None

    async def _build_chat_record(self, client, dialog) -> ChatRecord:
        entity = dialog.entity
        warnings: List[str] = []
        description = None
        member_count = getattr(entity, "participants_count", None)
        joined_at = None

        if isinstance(entity, types.Channel):
            try:
                response = await client(GetFullChannelRequest(entity))
                full_chat = response.full_chat
                description = getattr(full_chat, "about", None)
                member_count = getattr(full_chat, "participants_count", member_count)
                joined_at = await self._joined_at(client, entity, full_chat)
            except Exception as exc:
                warnings.append(_warning(t("export.warning.details"), exc))
        else:
            try:
                response = await client(GetFullChatRequest(entity.id))
                full_chat = response.full_chat
                description = getattr(full_chat, "about", None)
                participants = getattr(getattr(full_chat, "participants", None), "participants", [])
                member_count = len(participants) if participants is not None else member_count
                joined_at = await self._joined_at(client, entity, full_chat)
            except Exception as exc:
                warnings.append(_warning(t("export.warning.details"), exc))

        message_count = await self._message_count(client, entity)
        username = getattr(entity, "username", None)
        return ChatRecord(
            chat_id=int(utils.get_peer_id(entity)),
            title=_display_name(entity),
            kind=_chat_kind(entity),
            created_at=_date_text(getattr(entity, "date", None)),
            username=username,
            public_link=f"https://t.me/{username}" if username else None,
            is_public=bool(username),
            member_count=int(member_count) if member_count is not None else None,
            description=description,
            export_warning="; ".join(warnings) if warnings else None,
            status=_chat_status(entity, _chat_validity(entity)),
            is_archived=bool(getattr(dialog, "archived", False)),
            unread_count=getattr(dialog, "unread_count", None),
            joined_at=joined_at,
            last_message_id=getattr(getattr(dialog, "message", None), "id", None),
            last_message_at=_date_text(getattr(dialog, "date", None)),
            last_message_text=_message_preview(getattr(dialog, "message", None)),
            message_count=message_count,
        )

    def iter_message_records(
        self,
        *,
        chat_id: int,
        chat_title: str,
        start_at: datetime,
        end_at: datetime,
        output_timezone,
        min_message_id: Optional[int],
        cancel_event: threading.Event,
        queue_size: int = 256,
    ) -> Iterator[MessageRecord]:
        record_queue: queue.Queue = queue.Queue(maxsize=queue_size)
        future: Future = self.bot_manager.submit_telegram(
            self._produce_messages,
            record_queue,
            cancel_event,
            chat_id,
            chat_title,
            start_at,
            end_at,
            output_timezone,
            min_message_id,
        )
        try:
            while True:
                item = record_queue.get()
                if item is _STREAM_END:
                    break
                yield item
            future.result()
        finally:
            if not future.done():
                cancel_event.set()
                future.cancel()

    async def _queue_put(self, target: queue.Queue, value, cancel_event, force=False) -> bool:
        while True:
            try:
                target.put_nowait(value)
                return True
            except queue.Full:
                if not force and cancel_event.is_set():
                    return False
                await asyncio.sleep(0.05)

    async def _produce_messages(
        self,
        client,
        target_queue,
        cancel_event,
        chat_id,
        chat_title,
        start_at,
        end_at,
        output_timezone,
        min_message_id,
    ) -> None:
        try:
            entity = await client.get_entity(chat_id)
            history_options = {
                "reverse": True,
                "min_id": int(min_message_id or 0),
                "wait_time": 1,
            }
            unix_epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
            if start_at > unix_epoch:
                history_options["offset_date"] = start_at - timedelta(
                    microseconds=1
                )
            async for message in client.iter_messages(
                entity,
                **history_options,
            ):
                if cancel_event.is_set():
                    return
                message_date = message.date
                if message_date.tzinfo is None:
                    message_date = message_date.replace(tzinfo=timezone.utc)
                if message_date < start_at:
                    continue
                if message_date > end_at:
                    break
                record = await self._message_record(
                    message,
                    chat_id,
                    chat_title,
                    output_timezone,
                )
                if not await self._queue_put(target_queue, record, cancel_event):
                    return
        finally:
            await self._queue_put(target_queue, _STREAM_END, cancel_event, force=True)

    async def _message_record(
        self,
        message,
        chat_id: int,
        chat_title: str,
        output_timezone,
    ) -> MessageRecord:
        sender = getattr(message, "sender", None)
        if sender is None and getattr(message, "sender_id", None):
            try:
                sender = await message.get_sender()
            except Exception:
                sender = None

        media_type = self._media_type(message)
        raw_text = getattr(message, "raw_text", None) or getattr(message, "text", None) or ""
        content = raw_text
        if media_type != "text":
            placeholder = t(f"export.placeholder.{media_type}")
            content = f"{placeholder} {raw_text}".rstrip()

        message_date = message.date
        if message_date.tzinfo is None:
            message_date = message_date.replace(tzinfo=timezone.utc)
        edit_date = getattr(message, "edit_date", None)
        if edit_date and edit_date.tzinfo is None:
            edit_date = edit_date.replace(tzinfo=timezone.utc)

        forward = getattr(message, "fwd_from", None)
        forward_date = getattr(forward, "date", None)
        if forward_date and forward_date.tzinfo is None:
            forward_date = forward_date.replace(tzinfo=timezone.utc)
        message_file = getattr(message, "file", None)
        media_object = getattr(message, "document", None) or getattr(
            message, "photo", None
        )
        replies = getattr(message, "replies", None)
        reply_header = getattr(message, "reply_to", None)
        action = getattr(message, "action", None)

        return MessageRecord(
            message_id=int(message.id),
            chat_id=int(chat_id),
            chat_title=chat_title,
            date=message_date.astimezone(output_timezone).isoformat(timespec="seconds"),
            sender_id=getattr(message, "sender_id", None),
            sender_name=_display_name(sender) or None,
            sender_username=getattr(sender, "username", None) if sender else None,
            text=raw_text,
            media_type=media_type,
            content=content,
            reply_to_message_id=getattr(message, "reply_to_msg_id", None),
            edited_at=(
                edit_date.astimezone(output_timezone).isoformat(timespec="seconds")
                if edit_date
                else None
            ),
            grouped_id=getattr(message, "grouped_id", None),
            date_utc=message_date.astimezone(timezone.utc).isoformat(timespec="seconds"),
            sender_type=_sender_type(sender),
            sender_first_name=getattr(sender, "first_name", None) if sender else None,
            sender_last_name=getattr(sender, "last_name", None) if sender else None,
            sender_is_bot=(
                bool(getattr(sender, "bot", False)) if sender is not None else None
            ),
            sender_phone=getattr(sender, "phone", None) if sender else None,
            sender_is_verified=(
                bool(getattr(sender, "verified", False))
                if sender is not None
                else None
            ),
            sender_is_premium=(
                bool(getattr(sender, "premium", False))
                if sender is not None
                else None
            ),
            sender_is_scam=(
                bool(getattr(sender, "scam", False)) if sender is not None else None
            ),
            sender_is_fake=(
                bool(getattr(sender, "fake", False)) if sender is not None else None
            ),
            sender_is_contact=(
                bool(getattr(sender, "contact", False))
                if sender is not None
                else None
            ),
            sender_is_mutual_contact=(
                bool(getattr(sender, "mutual_contact", False))
                if sender is not None
                else None
            ),
            reply_to_top_id=getattr(reply_header, "reply_to_top_id", None),
            edited_at_utc=(
                edit_date.astimezone(timezone.utc).isoformat(timespec="seconds")
                if edit_date
                else None
            ),
            forward_from_id=_peer_id(getattr(forward, "from_id", None)),
            forward_from_name=getattr(forward, "from_name", None),
            forward_date=(
                forward_date.astimezone(output_timezone).isoformat(timespec="seconds")
                if forward_date
                else None
            ),
            forward_date_utc=(
                forward_date.astimezone(timezone.utc).isoformat(timespec="seconds")
                if forward_date
                else None
            ),
            via_bot_id=getattr(message, "via_bot_id", None),
            post_author=getattr(message, "post_author", None),
            views=getattr(message, "views", None),
            forwards=getattr(message, "forwards", None),
            replies_count=getattr(replies, "replies", None),
            media_id=getattr(media_object, "id", None),
            media_mime_type=getattr(message_file, "mime_type", None),
            media_file_name=getattr(message_file, "name", None),
            media_size=getattr(message_file, "size", None),
            media_duration=getattr(message_file, "duration", None),
            service_action=type(action).__name__ if action is not None else None,
            is_outgoing=getattr(message, "out", None),
            is_mentioned=getattr(message, "mentioned", None),
            is_media_unread=getattr(message, "media_unread", None),
            is_silent=getattr(message, "silent", None),
            is_post=getattr(message, "post", None),
            is_from_scheduled=getattr(message, "from_scheduled", None),
            is_pinned=getattr(message, "pinned", None),
            is_forwarding_restricted=getattr(message, "noforwards", None),
            entities=_tl_data(getattr(message, "entities", None)) or [],
            reactions=_tl_data(getattr(message, "reactions", None)),
            reply_markup=_tl_data(getattr(message, "reply_markup", None)),
            restriction_reason=(
                _tl_data(getattr(message, "restriction_reason", None)) or []
            ),
            sender_raw=_tl_data(sender) or {},
            raw=_tl_data(message) or {},
        )

    @staticmethod
    def _media_type(message) -> str:
        if getattr(message, "action", None) is not None:
            return "service"
        if not getattr(message, "media", None):
            return "text"
        if getattr(message, "photo", None):
            return "photo"
        if getattr(message, "gif", None):
            return "animation"
        if getattr(message, "sticker", None):
            return "sticker"
        if getattr(message, "video_note", None):
            return "video_note"
        if getattr(message, "video", None):
            return "video"
        if getattr(message, "voice", None):
            return "voice"
        if getattr(message, "audio", None):
            return "audio"
        if getattr(message, "document", None):
            return "document"
        media = message.media
        if isinstance(media, types.MessageMediaContact):
            return "contact"
        if isinstance(media, types.MessageMediaPoll):
            return "poll"
        if isinstance(media, (types.MessageMediaGeo, types.MessageMediaGeoLive)):
            return "location"
        return "media"
