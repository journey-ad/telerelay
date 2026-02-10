"""
Message forwarding core module
"""
import asyncio
from typing import List
from telethon import TelegramClient
from telethon.tl.types import Message
from telethon.errors import FloodWaitError, ChatForwardsRestrictedError
from src.rule import ForwardingRule
from src.filters import MessageFilter
from src.logger import get_logger
from src.utils import get_media_description
from src.constants import FORWARD_PREVIEW_LENGTH
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

        # Statistics
        self.forwarded_count = 0
        self.filtered_count = 0

        # Helper components
        self.media_group = MediaGroupHandler(client, rule.name)
        self.downloader = MediaDownloader(client, rule.name)

    async def handle_message(self, event) -> None:
        """Handle new message event (called by bot_manager central handler)"""
        message: Message = event.message

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
        source_text = self._build_source_text(message)
        success_count = 0

        for i, target in enumerate(targets):
            try:
                if downloaded_files:
                    await self._send_files(downloaded_files, messages, target, source_text)
                else:
                    await self._forward_normal(messages, target, source_text, is_noforwards)

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
                        await self._send_files(downloaded_files, messages, target, source_text)
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
        self, messages: List[Message], target, source_text: str, is_noforwards: bool
    ) -> None:
        """Normal forwarding flow (no download needed)"""
        if is_noforwards:
            # noforwards restriction → copy with reference
            await self._forward_copy(messages, target, source_text)
        elif self.rule.preserve_format:
            # Preserve format → direct forward
            await self.client.forward_messages(target, messages)
            logger.info(t("log.forward.direct_success", target=target))
        else:
            # Don't preserve format → copy with reference
            await self._forward_copy(messages, target, source_text)

    async def _forward_copy(self, messages: List[Message], target, source_text: str) -> None:
        """Copy message by referencing media ID (without preserving 'forwarded from' label)"""
        if len(messages) == 1:
            msg = messages[0]
            text = self._prepend_source(msg.text or "", source_text)
            await self.client.send_message(
                target, text,
                file=msg.media,
                formatting_entities=msg.entities,
            )
        else:
            # Media group: collect all media, text attached to first message
            first = messages[0]
            text = self._prepend_source(first.text or "", source_text)
            media_list = [msg.media for msg in messages if msg.media]
            await self.client.send_file(
                target,
                file=media_list,
                caption=text,
                formatting_entities=first.entities,
            )
        logger.info(t("log.forward.copy_success", target=target))

    async def _send_files(
        self, file_paths: List[str], messages: List[Message], target, source_text: str
    ) -> None:
        """Send to target using downloaded files"""
        if not file_paths:
            # No media files, send text only
            text = self._prepend_source(messages[0].text or "", source_text)
            await self.client.send_message(target, text, formatting_entities=messages[0].entities)
            logger.info(t("log.forward.text_sent", target=target))
            return

        first = messages[0]
        text = self._prepend_source(first.text or "", source_text)

        logger.info(t("log.forward.uploading", target=target))
        if len(file_paths) == 1:
            await self.client.send_file(
                target,
                file=file_paths[0],
                caption=text,
                formatting_entities=first.entities,
            )
        else:
            await self.client.send_file(
                target,
                file=file_paths,
                caption=text,
                formatting_entities=first.entities,
            )
        logger.info(t("log.forward.force_success", target=target))

    # ===== Helper methods =====

    def _build_source_text(self, message: Message) -> str:
        """
        Build source information text (including t.me link)

        For public channels/groups: https://t.me/{username}/{message_id}
        For private groups: https://t.me/c/{channel_id}/{message_id}
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

    def _prepend_source(self, text: str, source_text: str) -> str:
        """Prepend source information to message text"""
        if not source_text:
            return text
        return f"{source_text}\n\n{text}" if text else source_text

    def _log_result(self, message: Message, messages: List[Message], success: int, total: int) -> None:
        """Log forwarding result"""
        preview = (message.text or get_media_description(message))[:FORWARD_PREVIEW_LENGTH]
        is_media_group = len(messages) > 1

        if success > 0:
            self.forwarded_count += 1
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
