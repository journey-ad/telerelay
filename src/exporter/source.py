"""Telethon-backed source for group metadata and message history."""

import asyncio
import queue
import threading
from concurrent.futures import Future
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterator, List, Optional

from telethon import utils
from telethon.tl import types
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.functions.messages import GetFullChatRequest

from src.i18n import t

from .models import AdministratorRecord, ChatRecord, ChatSummary, MessageRecord

_STREAM_END = object()


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
    if isinstance(entity, types.Chat):
        return "group"
    if isinstance(entity, types.Channel) and getattr(entity, "megagroup", False):
        return "supergroup"
    if isinstance(entity, types.Channel) and getattr(entity, "broadcast", False):
        return "channel"
    return "channel"


def _admin_role(participant) -> str:
    if isinstance(
        participant,
        (types.ChannelParticipantCreator, types.ChatParticipantCreator),
    ):
        return "creator"
    return "administrator"


def _admin_record(user, participant=None) -> AdministratorRecord:
    return AdministratorRecord(
        user_id=int(user.id),
        name=_display_name(user),
        username=getattr(user, "username", None),
        role=_admin_role(participant),
        is_bot=bool(getattr(user, "bot", False)),
    )


def _warning(label: str, error: Exception) -> str:
    detail = str(error).replace("\n", " ").strip()
    if len(detail) > 240:
        detail = detail[:237] + "..."
    return f"{label}: {type(error).__name__}" + (f" ({detail})" if detail else "")


class TelegramExportSource:
    """Run all Telegram API work on BotManager's owning event loop."""

    def __init__(self, bot_manager):
        self.bot_manager = bot_manager

    def list_chat_summaries(self, timeout: float = 90) -> List[ChatSummary]:
        future = self.bot_manager.submit_telegram(self._list_chat_summaries)
        return future.result(timeout=timeout)

    async def _list_chat_summaries(self, client) -> List[ChatSummary]:
        chats: List[ChatSummary] = []
        async for dialog in client.iter_dialogs():
            entity = dialog.entity
            if not isinstance(entity, (types.Chat, types.Channel)):
                continue
            chats.append(
                ChatSummary(
                    chat_id=int(utils.get_peer_id(entity)),
                    title=_display_name(entity),
                    kind=_chat_kind(entity),
                    username=getattr(entity, "username", None),
                )
            )
        return sorted(chats, key=lambda item: (item.title.casefold(), item.chat_id))

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
            records.append(await self._build_chat_record(client, dialog.entity))
            if progress:
                progress(index, total)

        return sorted(records, key=lambda item: (item.title.casefold(), item.chat_id))

    async def _build_chat_record(self, client, entity) -> ChatRecord:
        warnings: List[str] = []
        description = None
        member_count = getattr(entity, "participants_count", None)
        administrators: List[AdministratorRecord] = []

        if isinstance(entity, types.Channel):
            try:
                response = await client(GetFullChannelRequest(entity))
                full_chat = response.full_chat
                description = getattr(full_chat, "about", None)
                member_count = getattr(full_chat, "participants_count", member_count)
            except Exception as exc:
                warnings.append(_warning(t("export.warning.details"), exc))

            try:
                async for user in client.iter_participants(
                    entity,
                    filter=types.ChannelParticipantsAdmins(),
                ):
                    administrators.append(
                        _admin_record(user, getattr(user, "participant", None))
                    )
            except Exception as exc:
                warnings.append(_warning(t("export.warning.administrators"), exc))
        else:
            try:
                response = await client(GetFullChatRequest(entity.id))
                full_chat = response.full_chat
                description = getattr(full_chat, "about", None)
                participants = getattr(getattr(full_chat, "participants", None), "participants", [])
                member_count = len(participants) if participants is not None else member_count
                users = {user.id: user for user in getattr(response, "users", [])}
                for participant in participants or []:
                    if not isinstance(
                        participant,
                        (types.ChatParticipantAdmin, types.ChatParticipantCreator),
                    ):
                        continue
                    user = users.get(participant.user_id)
                    if user:
                        administrators.append(_admin_record(user, participant))
            except Exception as exc:
                warnings.append(_warning(t("export.warning.details_and_administrators"), exc))

        username = getattr(entity, "username", None)
        administrators.sort(key=lambda item: (item.role != "creator", item.name.casefold()))
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
            administrators=administrators,
            export_warning="; ".join(warnings) if warnings else None,
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
        media = message.media
        if isinstance(media, types.MessageMediaContact):
            return "contact"
        if isinstance(media, types.MessageMediaPoll):
            return "poll"
        if isinstance(media, (types.MessageMediaGeo, types.MessageMediaGeoLive)):
            return "location"
        return "media"
