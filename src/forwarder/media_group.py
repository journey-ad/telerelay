"""
Media group handling module
"""
import time
import asyncio
from typing import List
from telethon import TelegramClient
from telethon.tl.types import Message
from src.filters import MessageFilter
from src.logger import get_logger
from src.i18n import t

logger = get_logger()

# Media group cache timeout (seconds)
MEDIA_GROUP_CACHE_TTL = 3600


class MediaGroupHandler:
    """Handle media group retrieval, deduplication and filtering"""

    def __init__(self, client: TelegramClient, rule_name: str):
        self.client = client
        self.rule_name = rule_name
        self._processed_groups: dict = {}  # {grouped_id: timestamp}

    async def get_messages(self, message: Message) -> List[Message]:
        """Get all messages in a media group, return [message] for non-media-group"""
        if not message.grouped_id:
            return [message]

        try:
            await asyncio.sleep(0.5)  # Wait for all messages in media group to arrive

            messages = []
            async for msg in self.client.iter_messages(message.chat_id, limit=50):
                if msg.grouped_id == message.grouped_id:
                    messages.append(msg)
                if len(messages) >= 10:
                    break

            if not messages:
                return [message]

            messages.sort(key=lambda m: m.id)
            logger.debug(t("log.forward.media_group.collected", group_id=message.grouped_id, count=len(messages)))
            return messages

        except Exception as e:
            logger.warning(t("log.forward.media_group.fetch_failed", error=e))
            return [message]

    def should_skip(self, grouped_id) -> bool:
        """Check if media group has been processed (deduplication)"""
        now = time.time()

        if grouped_id in self._processed_groups:
            if now - self._processed_groups[grouped_id] < MEDIA_GROUP_CACHE_TTL:
                logger.debug(t("log.forward.media_group.duplicate", group_id=grouped_id))
                return True

        # Record and cleanup expired cache
        self._processed_groups[grouped_id] = now
        self._processed_groups = {
            gid: ts for gid, ts in self._processed_groups.items()
            if now - ts < MEDIA_GROUP_CACHE_TTL
        }
        return False

    def should_forward(self, messages: List[Message], message_filter: MessageFilter, sender_id: int) -> bool:
        """Determine if media group should be forwarded"""
        has_text = any(msg.text for msg in messages)

        if not has_text:
            return True  # All pure media, pass by default

        # When there's text, check if any message matches filter conditions
        if any(message_filter.should_forward(msg, sender_id=sender_id) for msg in messages):
            return True

        logger.debug(t("log.forward.media_group.filtered", group_id=messages[0].grouped_id))
        return False
