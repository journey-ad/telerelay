"""
媒体组处理模块
"""
import time
import asyncio
from typing import List
from telethon import TelegramClient
from telethon.tl.types import Message
from src.filters import MessageFilter
from src.logger import get_logger

logger = get_logger()

# 媒体组缓存超时（秒）
MEDIA_GROUP_CACHE_TTL = 3600


class MediaGroupHandler:
    """处理媒体组的获取、去重和过滤"""

    def __init__(self, client: TelegramClient, rule_name: str):
        self.client = client
        self.rule_name = rule_name
        self._processed_groups: dict = {}  # {grouped_id: timestamp}

    async def get_messages(self, message: Message) -> List[Message]:
        """获取媒体组的所有消息，非媒体组返回 [message]"""
        if not message.grouped_id:
            return [message]

        try:
            await asyncio.sleep(0.5)  # 等待媒体组所有消息到达

            messages = []
            async for msg in self.client.iter_messages(message.chat_id, limit=50):
                if msg.grouped_id == message.grouped_id:
                    messages.append(msg)
                if len(messages) >= 10:
                    break

            if not messages:
                return [message]

            messages.sort(key=lambda m: m.id)
            logger.debug(f"[{self.rule_name}] 📎 媒体组 grouped_id={message.grouped_id}: 共 {len(messages)} 条消息")
            return messages

        except Exception as e:
            logger.warning(f"获取媒体组消息失败: {e}，作为单条消息处理")
            return [message]

    def should_skip(self, grouped_id) -> bool:
        """检查媒体组是否已处理过（去重）"""
        now = time.time()

        if grouped_id in self._processed_groups:
            if now - self._processed_groups[grouped_id] < MEDIA_GROUP_CACHE_TTL:
                logger.debug(f"[{self.rule_name}] ↩ 媒体组重复触发，跳过 (grouped_id={grouped_id})")
                return True

        # 记录并清理过期缓存
        self._processed_groups[grouped_id] = now
        self._processed_groups = {
            gid: ts for gid, ts in self._processed_groups.items()
            if now - ts < MEDIA_GROUP_CACHE_TTL
        }
        return False

    def should_forward(self, messages: List[Message], message_filter: MessageFilter, sender_id: int) -> bool:
        """判断媒体组是否应该转发"""
        has_text = any(msg.text for msg in messages)

        if not has_text:
            return True  # 全是纯媒体，默认通过

        # 有文本时，检查是否有任何一条消息匹配过滤条件
        if any(message_filter.should_forward(msg, sender_id=sender_id) for msg in messages):
            return True

        logger.debug(f"[{self.rule_name}] 媒体组被过滤 (无匹配消息) - grouped_id: {messages[0].grouped_id}")
        return False
