"""
消息转发模块
处理消息转发逻辑
"""
import os
import time
import tempfile
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

logger = get_logger()

# 媒体组缓存超时（秒），需要覆盖大文件下载耗时
MEDIA_GROUP_CACHE_TTL = 300
# 临时文件目录
TEMP_DIR = os.path.join(tempfile.gettempdir(), "tg-box-cache")


class MessageForwarder:
    """消息转发器"""

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

        # 统计信息
        self.forwarded_count = 0
        self.filtered_count = 0

        # 媒体组去重缓存 {grouped_id: timestamp}
        self._processed_media_groups: dict = {}

    async def handle_message(self, event) -> None:
        """
        处理新消息事件（由 bot_manager 中央处理器调用，已完成日志输出）
        """
        message: Message = event.message

        try:
            await self.forward_message(message, event.sender_id)

            if self.rule.delay > 0:
                await asyncio.sleep(self.rule.delay)

        except FloodWaitError as e:
            logger.warning(f"触发速率限制，等待 {e.seconds} 秒后重试")
            await asyncio.sleep(e.seconds)
            await self.forward_message(message, event.sender_id)
        except Exception as e:
            logger.error(f"转发消息失败: {e}", exc_info=True)

    async def forward_message(self, message: Message, sender_id: int) -> None:
        """转发消息到所有目标"""
        targets = self.rule.target_chats
        if not targets:
            logger.error("未配置目标聊天")
            return

        # 获取媒体组消息（单条消息返回 [message]）
        messages = await self._get_media_group_messages(message)
        is_media_group = len(messages) > 1

        # 媒体组去重
        if is_media_group and self._should_skip_media_group(message.grouped_id):
            return

        # 媒体组过滤
        if is_media_group and not self._should_forward_media_group(messages, sender_id):
            return

        # noforwards 检查
        is_noforwards = getattr(message.chat, 'noforwards', False) if message.chat else False

        # 构建来源信息文本
        source_text = self._build_source_text(message)

        # 转发到所有目标
        success_count = 0
        for i, target in enumerate(targets):
            try:
                await self._forward_to_target(messages, target, source_text, is_noforwards)
                success_count += 1

                # 多目标间延迟
                if self.rule.delay > 0 and i < len(targets) - 1:
                    await asyncio.sleep(self.rule.delay)

            except ChatForwardsRestrictedError:
                # 转发受限，降级为下载重传
                logger.warning(f"[{self.rule.name}] 转发受限，降级为下载重传")
                try:
                    await self._forward_download(messages, target, source_text)
                    success_count += 1
                except Exception as e2:
                    logger.error(f"降级转发到 {target} 失败: {e2}")
            except Exception as e:
                logger.error(f"转发消息到 {target} 失败: {e}")

        # 统计和日志
        preview = (message.text or get_media_description(message))[:FORWARD_PREVIEW_LENGTH]
        if success_count > 0:
            self.forwarded_count += 1
            group_info = f" (媒体组 {len(messages)} 项)" if is_media_group else ""
            group_id_info = f" gid={message.grouped_id}" if is_media_group else ""
            logger.info(
                f"[{self.rule.name}] ✅ 转发成功{group_info}: \"{preview}\"{group_id_info} "
                f"→ {success_count}/{len(targets)} 目标"
            )
        else:
            logger.error(f"❌ 转发失败: \"{preview}\" → 所有目标均失败")

    # ===== 转发策略 =====

    async def _forward_to_target(
        self, messages: List[Message], target, source_text: str, is_noforwards: bool
    ) -> None:
        """根据配置选择合适的转发方法"""
        if is_noforwards and self.rule.force_forward:
            # noforwards + 强制转发 → 下载重传
            await self._forward_download(messages, target, source_text)
        elif is_noforwards:
            # noforwards + 非强制 → 引用复制，失败则降级
            try:
                await self._forward_copy(messages, target, source_text)
            except Exception as e:
                logger.info(f"[{self.rule.name}] 引用复制失败，降级为下载重传: {e}")
                await self._forward_download(messages, target, source_text)
        elif self.rule.preserve_format:
            # 正常 + 保留格式 → 直接转发
            await self.client.forward_messages(target, messages)
            logger.info(f"[{self.rule.name}] ✓ 直接转发到 {target}")
        else:
            # 正常 + 不保留格式 → 引用复制
            await self._forward_copy(messages, target, source_text)

    async def _forward_copy(self, messages: List[Message], target, source_text: str) -> None:
        """通过引用媒体 ID 复制消息（不保留\"转发自\"标记）"""
        if len(messages) == 1:
            msg = messages[0]
            text = self._prepend_source(msg.text or "", source_text)
            await self.client.send_message(
                target, text,
                file=msg.media,
                formatting_entities=msg.entities,
            )
        else:
            # 媒体组：收集所有媒体，文本附在第一条
            first = messages[0]
            text = self._prepend_source(first.text or "", source_text)
            media_list = [msg.media for msg in messages if msg.media]
            await self.client.send_file(
                target,
                file=media_list,
                caption=text,
                formatting_entities=first.entities,
            )
        logger.info(f"[{self.rule.name}] ✓ 引用复制到 {target}")

    async def _forward_download(self, messages: List[Message], target, source_text: str) -> None:
        """通过下载+重新上传的方式复制消息（绕过 noforwards 限制）"""
        os.makedirs(TEMP_DIR, exist_ok=True)
        file_paths = []

        try:
            if len(messages) == 1:
                await self._download_and_send_single(messages[0], target, source_text)
            else:
                await self._download_and_send_group(messages, target, source_text, file_paths)
        finally:
            self._cleanup_files(file_paths)

        logger.info(f"[{self.rule.name}] ✓ 下载重传到 {target}")

    async def _download_and_send_single(self, message: Message, target, source_text: str) -> None:
        """下载并发送单条消息"""
        text = self._prepend_source(message.text or "", source_text)

        if not message.media:
            await self.client.send_message(target, text, formatting_entities=message.entities)
            return

        file_path = None
        try:
            logger.info(f"[{self.rule.name}] ⬇️ 开始下载媒体文件...")
            file_path = await self.client.download_media(message, file=TEMP_DIR)

            if not file_path:
                logger.error(f"[{self.rule.name}] 媒体下载失败，返回空路径")
                return

            file_size_mb = os.path.getsize(file_path) / 1048576
            logger.info(f"[{self.rule.name}] ⬇️ 下载完成: {os.path.basename(file_path)} ({file_size_mb:.1f} MB)")

            logger.info(f"[{self.rule.name}] ⬆️ 开始上传到 {target}...")
            await self.client.send_file(
                target,
                file=file_path,
                caption=text,
                formatting_entities=message.entities,
            )
        finally:
            if file_path:
                self._cleanup_files([file_path])

    async def _download_and_send_group(
        self, messages: List[Message], target, source_text: str, file_paths: list
    ) -> None:
        """下载并发送媒体组"""
        first = messages[0]
        text = self._prepend_source(first.text or "", source_text)

        logger.info(f"[{self.rule.name}] ⬇️ 开始下载媒体组 ({len(messages)} 项)...")

        for i, msg in enumerate(messages):
            if msg.media:
                path = await self.client.download_media(msg, file=TEMP_DIR)
                if path:
                    file_paths.append(path)
                    logger.debug(f"[{self.rule.name}] ⬇️ 下载 {i+1}/{len(messages)}: {os.path.basename(path)}")

        if not file_paths:
            logger.error(f"[{self.rule.name}] 媒体组下载失败，无有效文件")
            return

        logger.info(f"[{self.rule.name}] ⬇️ 媒体组下载完成: {len(file_paths)} 个文件")
        logger.info(f"[{self.rule.name}] ⬆️ 开始上传媒体组到 {target}...")
        await self.client.send_file(
            target,
            file=file_paths,
            caption=text,
            formatting_entities=first.entities,
        )

    # ===== 辅助方法 =====

    def _build_source_text(self, message: Message) -> str:
        """
        构建来源信息文本（包含 t.me 链接）

        对于公开频道/群组：https://t.me/{username}/{message_id}
        对于私有群组：https://t.me/c/{channel_id}/{message_id}
        """
        if not self.rule.add_source_info:
            return ""

        chat = message.chat
        msg_id = message.id

        # 尝试构建可点击链接
        if chat:
            username = getattr(chat, 'username', None)
            if username:
                # 公开频道/群组
                return f"📢 来源: https://t.me/{username}/{msg_id}"
            else:
                # 私有群组：chat_id 去掉 -100 前缀
                chat_id = message.chat_id
                if chat_id and chat_id < 0:
                    channel_id = str(chat_id).replace("-100", "")
                    return f"📢 来源: https://t.me/c/{channel_id}/{msg_id}"

        # 兜底：无法构建链接
        chat_title = getattr(chat, 'title', None) or "未知"
        return f"📢 来源: {chat_title}"

    def _prepend_source(self, text: str, source_text: str) -> str:
        """在消息文本前添加来源信息"""
        if not source_text:
            return text
        return f"{source_text}\n\n{text}" if text else source_text

    def _should_skip_media_group(self, grouped_id) -> bool:
        """检查媒体组是否已处理过（去重）"""
        now = time.time()

        if grouped_id in self._processed_media_groups:
            if now - self._processed_media_groups[grouped_id] < MEDIA_GROUP_CACHE_TTL:
                logger.debug(f"[{self.rule.name}] ↩ 媒体组重复触发，跳过 (grouped_id={grouped_id})")
                return True

        # 记录并清理过期缓存
        self._processed_media_groups[grouped_id] = now
        self._processed_media_groups = {
            gid: ts for gid, ts in self._processed_media_groups.items()
            if now - ts < MEDIA_GROUP_CACHE_TTL
        }
        return False

    def _should_forward_media_group(self, messages: List[Message], sender_id: int) -> bool:
        """判断媒体组是否应该转发"""
        has_text = any(msg.text for msg in messages)

        if not has_text:
            return True  # 全是纯媒体，默认通过

        # 有文本时，检查是否有任何一条消息匹配过滤条件
        if any(self.filter.should_forward(msg, sender_id=sender_id) for msg in messages):
            return True

        logger.debug(f"[{self.rule.name}] 媒体组被过滤 (无匹配消息) - grouped_id: {messages[0].grouped_id}")
        self.filtered_count += 1
        return False

    async def _get_media_group_messages(self, message: Message) -> List[Message]:
        """获取媒体组的所有消息，非媒体组返回 [message]"""
        if not message.grouped_id:
            return [message]

        try:
            # 等待媒体组所有消息到达
            await asyncio.sleep(0.5)

            messages = []
            async for msg in self.client.iter_messages(message.chat_id, limit=50):
                if msg.grouped_id == message.grouped_id:
                    messages.append(msg)
                if len(messages) >= 10:
                    break

            if not messages:
                return [message]

            messages.sort(key=lambda m: m.id)
            logger.debug(f"[{self.rule.name}] 📎 媒体组 grouped_id={message.grouped_id}: 共 {len(messages)} 条消息")
            return messages

        except Exception as e:
            logger.warning(f"获取媒体组消息失败: {e}，作为单条消息处理")
            return [message]

    @staticmethod
    def _cleanup_files(file_paths: list) -> None:
        """清理临时文件"""
        for path in file_paths:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                    logger.debug(f"已清理临时文件: {path}")
                except OSError as e:
                    logger.warning(f"清理临时文件失败: {path}, {e}")

    def get_stats(self) -> dict:
        """获取转发统计"""
        return {
            "forwarded": self.forwarded_count,
            "filtered": self.filtered_count,
            "total": self.forwarded_count + self.filtered_count,
        }
