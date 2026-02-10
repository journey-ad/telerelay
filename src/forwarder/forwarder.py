"""
消息转发核心模块
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
from .media_group import MediaGroupHandler
from .downloader import MediaDownloader

logger = get_logger()


class MessageForwarder:
    """消息转发器 - 核心转发逻辑"""

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

        # 辅助组件
        self.media_group = MediaGroupHandler(client, rule.name)
        self.downloader = MediaDownloader(client, rule.name)

    async def handle_message(self, event) -> None:
        """处理新消息事件（由 bot_manager 中央处理器调用）"""
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

        # 1. 预处理：获取消息、去重、过滤
        messages = await self.media_group.get_messages(message)
        is_media_group = len(messages) > 1

        if is_media_group and self.media_group.should_skip(message.grouped_id):
            return

        if is_media_group and not self.media_group.should_forward(messages, self.filter, sender_id):
            self.filtered_count += 1
            return

        # 2. 准备资源：检查是否需要下载
        is_noforwards = getattr(message.chat, 'noforwards', False) if message.chat else False
        need_download = is_noforwards and self.rule.force_forward

        downloaded_files = []
        if need_download:
            downloaded_files = await self.downloader.download(messages)
            if not downloaded_files:
                logger.error(f"[{self.rule.name}] 强制下载失败，无法转发")
                return

        # 3. 执行转发：循环所有目标
        source_text = self._build_source_text(message)
        success_count = 0

        for i, target in enumerate(targets):
            try:
                if downloaded_files:
                    await self._send_files(downloaded_files, messages, target, source_text)
                else:
                    await self._forward_normal(messages, target, source_text, is_noforwards)

                success_count += 1

                # 多目标间延迟
                if self.rule.delay > 0 and i < len(targets) - 1:
                    await asyncio.sleep(self.rule.delay)

            except ChatForwardsRestrictedError:
                # 转发受限，降级为下载重传
                logger.warning(f"[{self.rule.name}] 转发受限，降级为下载重传")
                try:
                    if not downloaded_files:
                        downloaded_files = await self.downloader.download(messages)
                    if downloaded_files:
                        await self._send_files(downloaded_files, messages, target, source_text)
                        success_count += 1
                except Exception as e2:
                    logger.error(f"降级转发到 {target} 失败: {e2}")
            except Exception as e:
                logger.error(f"转发消息到 {target} 失败: {e}")

        # 4. 清理资源
        if downloaded_files:
            MediaDownloader.cleanup(downloaded_files)

        # 5. 统计和日志
        self._log_result(message, messages, success_count, len(targets))

    # ===== 转发策略 =====

    async def _forward_normal(
        self, messages: List[Message], target, source_text: str, is_noforwards: bool
    ) -> None:
        """正常转发流程（不需要下载）"""
        if is_noforwards:
            # noforwards 限制 → 引用复制
            await self._forward_copy(messages, target, source_text)
        elif self.rule.preserve_format:
            # 保留格式 → 直接转发
            await self.client.forward_messages(target, messages)
            logger.info(f"[{self.rule.name}] ✓ 已直接转发到 {target}")
        else:
            # 不保留格式 → 引用复制
            await self._forward_copy(messages, target, source_text)

    async def _forward_copy(self, messages: List[Message], target, source_text: str) -> None:
        """通过引用媒体 ID 复制消息（不保留"转发自"标记）"""
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
        logger.info(f"[{self.rule.name}] ✓ 已引用复制到 {target}")

    async def _send_files(
        self, file_paths: List[str], messages: List[Message], target, source_text: str
    ) -> None:
        """使用已下载的文件发送到目标"""
        if not file_paths:
            # 无媒体文件，只发送文本
            text = self._prepend_source(messages[0].text or "", source_text)
            await self.client.send_message(target, text, formatting_entities=messages[0].entities)
            logger.info(f"[{self.rule.name}] ✓ 已发送文本到 {target}")
            return

        first = messages[0]
        text = self._prepend_source(first.text or "", source_text)

        logger.info(f"[{self.rule.name}] ⬆️ 开始上传到 {target}...")
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
        logger.info(f"[{self.rule.name}] ✓ 已强制转发到 {target}")

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

    def _log_result(self, message: Message, messages: List[Message], success: int, total: int) -> None:
        """记录转发结果"""
        preview = (message.text or get_media_description(message))[:FORWARD_PREVIEW_LENGTH]
        is_media_group = len(messages) > 1

        if success > 0:
            self.forwarded_count += 1
            group_info = f" (媒体组 {len(messages)} 项)" if is_media_group else ""
            group_id_info = f" gid={message.grouped_id}" if is_media_group else ""
            logger.info(
                f"[{self.rule.name}] ✅ 转发成功{group_info}: \"{preview}\"{group_id_info} "
                f"→ {success}/{total} 目标"
            )
        else:
            logger.error(f"❌ 转发失败: \"{preview}\" → 所有目标均失败")

    def get_stats(self) -> dict:
        """获取转发统计"""
        return {
            "forwarded": self.forwarded_count,
            "filtered": self.filtered_count,
            "total": self.forwarded_count + self.filtered_count,
        }
