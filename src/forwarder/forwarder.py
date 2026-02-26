"""
Message forwarding core module
"""
import asyncio
import copy
from typing import List
from telethon import TelegramClient
from telethon.tl.types import Message, MessageEntityTextUrl, MessageEntityBlockquote, MessageMediaWebPage
from telethon.errors import FloodWaitError, ChatForwardsRestrictedError
from src.rule import ForwardingRule
from src.filters import MessageFilter, get_media_type
from src.logger import get_logger
from src.utils import get_media_description
from src.constants import FORWARD_PREVIEW_LENGTH
from src.stats_db import get_stats_db
from src.dedup import DeduplicateCache
from src.i18n import t
from .media_group import MediaGroupHandler
from .downloader import MediaDownloader

logger = get_logger()


class MessageForwarder:
    """Message forwarder - core forwarding logic"""

    def __init__(
        self,
        client: TelegramClient,
        rule: ForwardingRule,
        message_filter: MessageFilter,
        bot_manager=None,
    ):
        self.client = client
        self.rule = rule
        self.filter = message_filter
        self.bot_manager = bot_manager

        # Statistics (persistent via SQLite)
        self._stats_db = get_stats_db()
        db_stats = self._stats_db.get_stats(rule.name)
        self.forwarded_count = db_stats["forwarded"]
        self.filtered_count = db_stats["filtered"]

        # Helper components
        self.media_group = MediaGroupHandler(client, rule.name)
        self.downloader = MediaDownloader(client, rule.name)

        # Deduplication cache (per-rule)
        self._dedup = DeduplicateCache(window=rule.deduplicate_window) if rule.deduplicate else None

    async def handle_message(self, event) -> None:
        """Handle new message event (called by bot_manager central handler)"""
        message: Message = event.message

        # Debug serialized message
        try:
            if hasattr(message, 'to_dict'):
                # Avoid overly large outputs via pretty print if possible, but keep it simple
                logger.debug(f"[DEBUG] Intercepted message: {message.to_dict()}")
        except Exception:
            pass

        try:
            await self.forward_message(message, event.sender_id)

            if self.rule.delay > 0:
                await asyncio.sleep(self.rule.delay)

        except FloodWaitError as e:
            logger.warning(t("log.forward.flood_wait", seconds=e.seconds))
            await asyncio.sleep(e.seconds)
            await self.forward_message(message, event.sender_id)
        except Exception as e:
            logger.error(t("log.forward.error", error=e), exc_info=True)

    async def forward_message(self, message: Message, sender_id: int) -> None:
        """Forward message to all targets"""
        targets = self.rule.target_chats
        if not targets:
            logger.error(t("log.forward.no_target"))
            return

        # 1. Preprocessing: get messages, deduplicate, filter
        messages = await self.media_group.get_messages(message)
        is_media_group = len(messages) > 1

        if is_media_group and self.media_group.should_skip(message.grouped_id):
            return

        if is_media_group and not self.media_group.should_forward(messages, self.filter, sender_id):
            self.filtered_count += 1
            self._stats_db.increment_filtered(self.rule.name)
            self._stats_db.increment_daily(self.rule.name, is_forwarded=False)
            return

        # Deduplication check
        if self._dedup:
            text_to_check = message.text or ""
            if self._dedup.is_duplicate(text_to_check):
                self.filtered_count += 1
                self._stats_db.increment_filtered(self.rule.name)
                self._stats_db.increment_daily(self.rule.name, is_forwarded=False)
                logger.info(t("log.forward.deduplicated", preview=(text_to_check[:50] or "[media]")))
                return

        # 2. Prepare resources: check if download is needed
        is_noforwards = getattr(message.chat, 'noforwards', False) if message.chat else False
        need_download = is_noforwards and self.rule.force_forward

        downloaded_files = []
        if need_download:
            downloaded_files = await self.downloader.download(messages)
            if not downloaded_files:
                logger.error(t("log.forward.download_failed"))
                return

        # 3. Execute forwarding: loop through all targets
        source_data = self._get_source_data(message) if self.rule.hide_sender else None
        source_text = self._build_source_text(message) if not self.rule.hide_sender else ""
        success_count = 0

        for i, target in enumerate(targets):
            try:
                if downloaded_files:
                    await self._send_files(downloaded_files, messages, target, source_data, source_text)
                else:
                    await self._forward_normal(messages, target, source_data, source_text, is_noforwards)

                success_count += 1

                # Delay between multiple targets
                if self.rule.delay > 0 and i < len(targets) - 1:
                    await asyncio.sleep(self.rule.delay)

            except ChatForwardsRestrictedError:
                # Forwarding restricted, fallback to download and resend
                logger.warning(t("log.forward.restricted_fallback"))
                try:
                    if not downloaded_files:
                        downloaded_files = await self.downloader.download(messages)
                    if downloaded_files:
                        await self._send_files(downloaded_files, messages, target, source_data, source_text)
                        success_count += 1
                except Exception as e2:
                    logger.error(t("log.forward.fallback_failed", target=target, error=e2))
            except Exception as e:
                logger.error(t("log.forward.target_failed", target=target, error=e))

        # 4. Cleanup resources
        if downloaded_files:
            MediaDownloader.cleanup(downloaded_files)

        # 5. Statistics and logging
        self._log_result(message, messages, success_count, len(targets))

    # ===== Forwarding strategies =====

    async def _forward_normal(
        self, messages: List[Message], target, source_data: dict, source_text: str, is_noforwards: bool
    ) -> None:
        """Normal forwarding flow (no download needed)"""
        if self.rule.hide_sender:
            await self._forward_copy(messages, target, source_data, "")
        elif is_noforwards:
            # noforwards restriction → copy with reference
            await self._forward_copy(messages, target, None, source_text)
        elif self.rule.preserve_format:
            # Preserve format → direct forward
            await self.client.forward_messages(target, messages)
            logger.info(t("log.forward.direct_success", target=target))
        else:
            # Don't preserve format → copy with reference
            await self._forward_copy(messages, target, None, source_text)

    async def _forward_copy(self, messages: List[Message], target, source_data: dict, source_text: str) -> None:
        """Copy message by referencing media ID (without preserving 'forwarded from' label)"""
        has_media = any(msg.media for msg in messages)
        
        if len(messages) == 1:
            msg = messages[0]
            text = msg.raw_text or ""
            entities = list(msg.entities) if msg.entities else []
            
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
            
        logger.info(t("log.forward.copy_success", target=target))

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
            logger.info(t("log.forward.text_sent", target=target))
            return

        first = messages[0]
        text = first.raw_text or ""
        entities = list(first.entities) if first.entities else []

        file_passed = file_paths[0] if len(file_paths) == 1 else file_paths
        
        if source_data:
            text, added_entities = self._format_source_append(text, source_data)
            entities.extend(added_entities)
        elif source_text:
            text, entities = self._prepend_source(text, source_text, entities)

        logger.info(t("log.forward.uploading", target=target))
        await self.client.send_file(
            target,
            file=file_passed,
            caption=text,
            formatting_entities=entities,
        )
            
        logger.info(t("log.forward.force_success", target=target))

    # ===== Helper methods =====

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
        
        # 1. Determine the main subject (priority given to forward source)
        target = None
        is_forward = False
        if message.forward:
            target = message.forward.chat or message.forward.sender
            is_forward = True
        else:
            target = message.chat or message.sender

        if not target:
            return {"name": name, "link": link, "date": date_str}

        # 2. Extract the name
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

        # 3. Construct the link
        msg_id = None
        if is_forward:
            msg_id = getattr(message.forward, 'channel_post', getattr(message.forward, 'msg_id', None))
        else:
            msg_id = message.id

        is_chat = hasattr(target, 'title') or (message.chat and hasattr(message.chat, 'title'))
        
        if username:
            # Public channel/group, deep link to message
            if is_chat and msg_id:
                link = f"https://t.me/{username}/{msg_id}"
            else:
                link = f"https://t.me/{username}"
        elif is_chat and msg_id:
            # Private group/channel
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

    def _log_result(self, message: Message, messages: List[Message], success: int, total: int) -> None:
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
                )
            except Exception as e:
                logger.debug(f"Failed to insert history: {e}")

            group_info = t("misc.media_group_info", count=len(messages)) if is_media_group else ""
            group_id_info = f" gid={message.grouped_id}" if is_media_group else ""
            logger.info(
                t("log.forward.success",
                  group_info=group_info,
                  preview=preview,
                  group_id_info=group_id_info,
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
