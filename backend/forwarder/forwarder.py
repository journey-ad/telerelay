"""
Message forwarding core module
"""
import asyncio
import copy
import json
from typing import Any, Callable, List, Optional

from telethon import TelegramClient, utils
from telethon.errors import ChatForwardsRestrictedError
from telethon.tl.types import (
    Message,
    MessageEntityBlockquote,
    MessageEntityTextUrl,
    MessageMediaWebPage,
)

from backend.constants import FORWARD_PREVIEW_LENGTH
from backend.dedup import DeduplicateCache
from backend.filters import MessageFilter, get_media_type
from backend.i18n import t
from backend.logger import get_logger
from backend.rule import ForwardingRule
from backend.stats_db import get_stats_db
from backend.telegram_entities import serialize_entities
from backend.utils import get_media_description

from .downloader import MediaDownloader
from .media_group import MediaGroupHandler

logger = get_logger()

# Limit concurrent force-forward tasks (download + upload) to prevent tmp disk exhaustion
_force_forward_semaphore = asyncio.Semaphore(3)


class MessageForwarder:
    """Message forwarder - core forwarding logic"""

    def __init__(
        self,
        client: TelegramClient,
        rule: ForwardingRule,
        message_filter: MessageFilter,
        bot_manager=None,
        target_label_cache: Optional[dict[str, str]] = None,
        stats_db=None,
        suppressed_check: Optional[Callable[[Any], bool]] = None,
        delivered_callback: Optional[Callable[[Any], None]] = None,
    ):
        self.client = client
        self.rule = rule
        self.filter = message_filter
        self.bot_manager = bot_manager
        self.suppressed_check = suppressed_check
        self.delivered_callback = delivered_callback
        self._target_label_cache = (
            target_label_cache if target_label_cache is not None else {}
        )

        # Statistics (persistent via SQLite)
        self._stats_db = stats_db or get_stats_db()
        db_stats = self._stats_db.get_stats(rule.name)
        self.forwarded_count = db_stats["forwarded"]
        self.filtered_count = db_stats["filtered"]

        # Helper components
        self.media_group = MediaGroupHandler(client, rule.name)
        self.downloader = MediaDownloader(client, rule.name)

        # Deduplication cache (per-rule)
        self._dedup = DeduplicateCache(window=rule.deduplicate_window) if rule.deduplicate else None

    async def handle_message(self, event) -> None:
        """Compatibility wrapper; live updates are normally handled by the queue."""
        message: Message = event.message
        await self.forward_message(message, event.sender_id)

    async def forward_message(
        self,
        message: Message,
        sender_id: int,
        skip_dedup: bool = False,
        start_target_index: int = 0,
        messages_override: Optional[List[Message]] = None,
        on_target_success: Optional[Callable[[int], None]] = None,
    ) -> bool:
        """Forward a message, resuming from a durable target checkpoint.

        ``messages_override`` supplies the full album member list already
        fetched by the queue consumer (bot sessions cannot page history, so
        the consumer aggregates member IDs at enqueue time).  When omitted,
        the media group handler falls back to history paging.

        FloodWait and target errors intentionally propagate to the persistent
        queue, which owns retry and global pause policy.
        """
        targets = self.rule.target_chats
        if not targets:
            raise RuntimeError(t("log.forward.no_target"))

        # 1. Preprocess
        messages = (
            messages_override
            if messages_override is not None
            else await self.media_group.get_messages(message)
        )
        is_media_group = len(messages) > 1

        if is_media_group and not self.media_group.should_forward(messages, self.filter, sender_id):
            self.filtered_count += 1
            self._stats_db.increment_filtered(self.rule.name)
            self._stats_db.increment_daily(self.rule.name, is_forwarded=False)
            return False

        # Deduplication check
        if self._dedup and not skip_dedup:
            text_to_check = message.text or ""
            if self._dedup.is_duplicate(text_to_check):
                self.filtered_count += 1
                self._stats_db.increment_filtered(self.rule.name)
                self._stats_db.increment_daily(self.rule.name, is_forwarded=False)
                logger.debug(t("log.forward.deduplicated", preview=(text_to_check[:50] or "[media]")))
                return False

        target_labels = await self._resolve_target_labels(targets)

        # 2. Prepare
        is_noforwards = getattr(message.chat, 'noforwards', False) if message.chat else False
        need_download = is_noforwards and self.rule.force_forward

        if need_download:
            async with _force_forward_semaphore:
                await self._do_forward(
                    messages,
                    message,
                    need_download,
                    is_noforwards,
                    start_target_index,
                    on_target_success,
                    target_labels,
                )
        else:
            await self._do_forward(
                messages,
                message,
                need_download,
                is_noforwards,
                start_target_index,
                on_target_success,
                target_labels,
            )
        return True

    async def _do_forward(
        self,
        messages: List[Message],
        message: Message,
        need_download: bool,
        is_noforwards: bool,
        start_target_index: int = 0,
        on_target_success: Optional[Callable[[int], None]] = None,
        target_labels: Optional[List[str]] = None,
    ) -> None:
        """Execute forwarding with optional download, cleanup guaranteed by try/finally"""
        targets = self.rule.target_chats
        downloaded_files = []
        session_dir = None
        sent_count = 0
        skipped_count = 0
        try:
            if start_target_index >= len(targets):
                self._log_result(
                    message,
                    messages,
                    len(targets),
                    len(targets),
                    target_labels,
                )
                return

            if need_download:
                downloaded_files, session_dir = await self.downloader.download(messages)
                if not downloaded_files:
                    raise RuntimeError(t("log.forward.download_failed"))

            # Execute forwarding
            source_data = self._get_source_data(message) if self.rule.hide_sender else None
            source_text = self._build_source_text(message) if not self.rule.hide_sender else ""
            for i in range(max(0, start_target_index), len(targets)):
                target = targets[i]
                if getattr(self, "suppressed_check", None) and self.suppressed_check(target):
                    # Opted-out subscribers are skipped silently; the durable
                    # checkpoint still advances so retries never resend them.
                    skipped_count += 1
                    if on_target_success:
                        on_target_success(i + 1)
                    continue
                try:
                    if downloaded_files:
                        await self._send_files(downloaded_files, messages, target, source_data, source_text)
                    else:
                        await self._forward_normal(messages, target, source_data, source_text, is_noforwards)

                except ChatForwardsRestrictedError:
                    # Only an explicitly enabled force-forward rule may turn a
                    # restricted forward into a download + upload operation.
                    # With force-forward disabled, preserve the restriction and
                    # let the durable queue handle the failed delivery instead
                    # of silently uploading protected media.
                    if not self.rule.force_forward:
                        raise

                    # Forwarding restricted, fallback to download and resend
                    logger.debug(t("log.forward.restricted_fallback"))
                    if not downloaded_files:
                        downloaded_files, session_dir = await self.downloader.download(messages)
                    if not downloaded_files:
                        raise RuntimeError(t("log.forward.download_failed"))
                    await self._send_files(downloaded_files, messages, target, source_data, source_text)

                sent_count += 1
                if self.delivered_callback:
                    self.delivered_callback(target)
                if on_target_success:
                    on_target_success(i + 1)

                # Delay between targets; per-rule delay is applied after commit.
                if self.rule.delay > 0 and i < len(targets) - 1:
                    await asyncio.sleep(self.rule.delay)
        finally:
            if session_dir:
                MediaDownloader.cleanup(session_dir)

        if skipped_count:
            logger.info(
                t(
                    "log.forward.suppressed_skipped",
                    count=skipped_count,
                    total=len(targets),
                )
            )
        if sent_count or not skipped_count:
            # Report success/failure only when delivery was actually attempted.
            self._log_result(
                message,
                messages,
                sent_count,
                len(targets),
                target_labels,
            )

    # -- Forwarding --

    @staticmethod
    def _has_media_files(messages: List[Message]) -> bool:
        return any(
            getattr(message, "media", None) is not None
            and not isinstance(message.media, MessageMediaWebPage)
            for message in messages
        )

    async def _forward_normal(
        self, messages: List[Message], target, source_data: dict, source_text: str, is_noforwards: bool
    ) -> None:
        """Normal forwarding flow (no download needed)"""
        if self.rule.hide_sender:
            await self._forward_copy(messages, target, source_data, "")
        elif self.rule.hide_media_caption and self._has_media_files(messages):
            await self._forward_copy(messages, target, source_data, source_text)
        elif is_noforwards:
            # noforwards restriction → copy with reference
            await self._forward_copy(messages, target, None, source_text)
        elif self.rule.preserve_format:
            # Preserve format → direct forward
            await self.client.forward_messages(target, messages)
            logger.debug(t("log.forward.direct_success", target=target))
        else:
            # Don't preserve format → copy with reference
            await self._forward_copy(messages, target, None, source_text)

    async def _forward_copy(self, messages: List[Message], target, source_data: dict, source_text: str) -> None:
        """Copy message by referencing media ID (without preserving 'forwarded from' label)"""
        if len(messages) == 1:
            msg = messages[0]
            text = msg.raw_text or ""
            entities = list(msg.entities) if msg.entities else []
            if self.rule.hide_media_caption and self._has_media_files(messages):
                text = ""
                entities = []
            
            if source_data:
                text, added_entities = self._format_source_append(text, source_data)
                entities.extend(added_entities)
            elif source_text:
                text, entities = self._prepend_source(text, source_text, entities)
                
            # WebPage preview cannot be sent as file
            media = msg.media if not isinstance(msg.media, MessageMediaWebPage) else None
            
            await self.client.send_message(
                target, text,
                file=media,
                formatting_entities=entities,
                link_preview=False if source_data else None
            )
        else:
            # Media group: collect all media, text attached to first message
            first = messages[0]
            text = first.raw_text or ""
            entities = list(first.entities) if first.entities else []
            if self.rule.hide_media_caption and self._has_media_files(messages):
                text = ""
                entities = []
            
            if source_data:
                text, added_entities = self._format_source_append(text, source_data)
                entities.extend(added_entities)
            elif source_text:
                text, entities = self._prepend_source(text, source_text, entities)
                
            media_list = [msg.media for msg in messages if msg.media and not isinstance(msg.media, MessageMediaWebPage)]
            
            await self.client.send_file(
                target,
                file=media_list,
                caption=text,
                formatting_entities=entities,
            )
            
        logger.debug(t("log.forward.copy_success", target=target))

    async def _send_files(
        self, file_paths: List[str], messages: List[Message], target, source_data: dict, source_text: str
    ) -> None:
        """Send to target using downloaded files"""
        if not file_paths:
            # No media files, send text only (this should be rare here)
            text = messages[0].raw_text or ""
            entities = list(messages[0].entities) if messages[0].entities else []
            
            if source_data:
                text, added_entities = self._format_source_append(text, source_data)
                entities.extend(added_entities)
            elif source_text:
                text, entities = self._prepend_source(text, source_text, entities)
                
            await self.client.send_message(
                target, text,
                formatting_entities=entities,
                link_preview=False if source_data else None
            )
            logger.debug(t("log.forward.text_sent", target=target))
            return

        first = messages[0]
        text = first.raw_text or ""
        entities = list(first.entities) if first.entities else []
        if self.rule.hide_media_caption:
            text = ""
            entities = []

        file_passed = file_paths[0] if len(file_paths) == 1 else file_paths
        
        if source_data:
            text, added_entities = self._format_source_append(text, source_data)
            entities.extend(added_entities)
        elif source_text:
            text, entities = self._prepend_source(text, source_text, entities)

        logger.debug(t("log.forward.uploading", target=target))
        await self.client.send_file(
            target,
            file=file_passed,
            caption=text,
            formatting_entities=entities,
        )
            
        logger.debug(t("log.forward.force_success", target=target))

    async def _resolve_target_labels(self, targets: List[object]) -> List[str]:
        """Resolve readable target names once and share them across forwarders."""
        labels = []
        for target in targets:
            cache_key = f"{type(target).__name__}:{target}"
            cached = self._target_label_cache.get(cache_key)
            if cached is not None:
                labels.append(cached)
                continue

            fallback = str(target)
            try:
                entity = await self.client.get_entity(target)
                name = utils.get_display_name(entity).strip()
                peer_id = int(utils.get_peer_id(entity))
                label = f"{name} ({peer_id})" if name and name != str(peer_id) else str(peer_id)
            except Exception as exc:
                label = fallback
                logger.debug(
                    t(
                        "log.forward.target_resolve_failed",
                        target=fallback,
                        error=exc,
                    )
                )

            self._target_label_cache[cache_key] = label
            labels.append(label)
        return labels

    # -- Source info --

    def _get_source_data(self, message: Message) -> dict:
        """
        Build source information data (name, link)
        """
        if not self.rule.add_source_info:
            return None

        name = "Unknown"
        link = ""
        
        import datetime
        # telethon message.date is usually a timezone-aware datetime in UTC
        if getattr(message, 'date', None):
            date_str = message.date.astimezone().strftime("%Y-%m-%d %H-%M-%S")
        else:
            date_str = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H-%M-%S")
        
        # 1. Determine subject (prefer forward source)
        target = None
        is_forward = False
        if message.forward:
            target = message.forward.chat or message.forward.sender
            is_forward = True
        else:
            target = message.chat or message.sender

        if not target:
            return {"name": name, "link": link, "date": date_str}

        # 2. Extract name
        username = getattr(target, 'username', None)
        if username:
            name = f"@{username}"
        else:
            first_name = getattr(target, 'first_name', '')
            last_name = getattr(target, 'last_name', '')
            if first_name or last_name:
                name = f"{first_name} {last_name}".strip()
            else:
                name = getattr(target, 'title', "Unknown")

        # 3. Build link
        msg_id = None
        if is_forward:
            msg_id = getattr(message.forward, 'channel_post', getattr(message.forward, 'msg_id', None))
        else:
            msg_id = message.id

        is_chat = hasattr(target, 'title') or (message.chat and hasattr(message.chat, 'title'))
        
        if username:
            # Public
            if is_chat and msg_id:
                link = f"https://t.me/{username}/{msg_id}"
            else:
                link = f"https://t.me/{username}"
        elif is_chat and msg_id:
            # Private
            chat_id = getattr(target, 'id', None)
            if chat_id:
                clean_id = str(chat_id).replace("-100", "", 1) if str(chat_id).startswith("-100") else str(chat_id)
                link = f"https://t.me/c/{clean_id}/{msg_id}"

        return {"name": name, "link": link, "date": date_str}

    def _format_source_append(self, text: str, source_data: dict) -> tuple[str, list]:
        """Append source information to message text, returning (text, entities)"""
        if not source_data:
            return text, []

        name = source_data.get("name", "Unknown")
        link = source_data.get("link", "")
        date_str = source_data.get("date", "")
        
        spacer = "\n" if text else ""
        
        # Use Blockquote for visual separation
        source_label = f"{date_str}" if date_str else "Ref:"
        append_str = f"{source_label} {name}"
        
        base_offset = len((text + spacer).encode('utf-16-le')) // 2
        append_length = len(append_str.encode('utf-16-le')) // 2
        
        entities = [
            MessageEntityBlockquote(
                offset=base_offset,
                length=append_length
            )
        ]
        
        if link:
            prefix_length = len(f"{source_label} ".encode('utf-16-le')) // 2
            entities.append(
                MessageEntityTextUrl(
                    offset=base_offset + prefix_length,
                    length=len(name.encode('utf-16-le')) // 2,
                    url=link
                )
            )
            
        full_append = spacer + append_str
        return text + full_append, entities



    def _build_source_text(self, message: Message) -> str:
        """
        Build source information text (including t.me link) - old format
        """
        if not self.rule.add_source_info:
            return ""

        chat = message.chat
        msg_id = message.id

        # Try to build clickable link
        if chat:
            username = getattr(chat, 'username', None)
            if username:
                # Public channel/group
                return t("log.forward.source_label", username=username, msg_id=msg_id)
            else:
                # Private group: remove -100 prefix from chat_id
                chat_id = message.chat_id
                if chat_id and chat_id < 0:
                    channel_id = str(chat_id).replace("-100", "")
                    return t("log.forward.source_private", channel_id=channel_id, msg_id=msg_id)

        # Fallback: unable to build link
        chat_title = getattr(chat, 'title', None) or t("misc.unknown")
        return t("log.forward.source_unknown", chat_title=chat_title)

    def _prepend_source(self, text: str, source_text: str, entities: list = None) -> tuple[str, list]:
        """Prepend source information to message text, shifting entities offset"""
        if not source_text:
            return text, entities or []

        if text:
            prefix = f"{source_text}\n\n"
            new_text = prefix + text
        else:
            return source_text, entities or []

        # Shift all existing entities by the prefix length (UTF-16 code units)
        shifted_entities = []
        if entities:
            prefix_len = len(prefix.encode('utf-16-le')) // 2
            for ent in entities:
                ent_copy = copy.copy(ent)
                ent_copy.offset = ent.offset + prefix_len
                shifted_entities.append(ent_copy)

        return new_text, shifted_entities

    def _log_result(
        self,
        message: Message,
        messages: List[Message],
        success: int,
        total: int,
        target_labels: Optional[List[str]] = None,
    ) -> None:
        """Log forwarding result"""
        preview = (message.text or get_media_description(message))[:FORWARD_PREVIEW_LENGTH]
        is_media_group = len(messages) > 1

        if success > 0:
            self.forwarded_count += 1
            self._stats_db.increment_forwarded(self.rule.name)
            self._stats_db.increment_daily(self.rule.name, is_forwarded=True)

            # Write history record
            try:
                chat = message.chat
                sender = message.sender
                self._stats_db.insert_history(
                    rule_name=self.rule.name,
                    message_id=message.id,
                    source_chat_id=message.chat_id,
                    source_chat_name=getattr(chat, 'title', None) or getattr(chat, 'username', None) or str(message.chat_id),
                    sender_id=message.sender_id,
                    sender_name=(
                        ' '.join(filter(None, [getattr(sender, 'first_name', None), getattr(sender, 'last_name', None)]))
                        if sender else str(message.sender_id)
                    ),
                    sender_first_name=getattr(sender, 'first_name', None) if sender else None,
                    sender_last_name=getattr(sender, 'last_name', None) if sender else None,
                    sender_username=getattr(sender, 'username', None) if sender else None,
                    content=message.text or get_media_description(message),
                    media_type=get_media_type(message) if message.media else "text",
                    entities=(
                        json.dumps(serialize_entities(message.entities))
                        if getattr(message, "entities", None)
                        else None
                    ),
                )
            except Exception as e:
                logger.debug(t("log.forward.history_failed", error=e))

            chat = getattr(message, "chat", None)
            source_name = (
                getattr(chat, "title", None)
                or getattr(chat, "username", None)
                or str(message.chat_id)
            )
            source = (
                f"{source_name} ({message.chat_id})/{message.id}"
                if str(source_name) != str(message.chat_id)
                else f"{message.chat_id}/{message.id}"
            )
            group_info = (
                t(
                    "misc.media_group_info",
                    count=len(messages),
                )
                if is_media_group
                else ""
            )
            targets = target_labels or [str(target) for target in self.rule.target_chats]
            logger.info(
                t("log.forward.success",
                  rule=self.rule.name,
                  source=source,
                  group_info=group_info,
                  targets=", ".join(targets) or "-",
                  preview=preview,
                  success=success,
                  total=total)
            )
        else:
            logger.error(t("log.forward.all_failed", preview=preview))

    def get_stats(self) -> dict:
        """Get forwarding statistics"""
        return {
            "forwarded": self.forwarded_count,
            "filtered": self.filtered_count,
            "total": self.forwarded_count + self.filtered_count,
        }
