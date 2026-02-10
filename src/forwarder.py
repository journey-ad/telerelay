"""
消息转发模块
处理消息转发逻辑
"""
import os
import tempfile
import asyncio
from typing import List, Optional
from telethon import TelegramClient
from telethon import utils
from telethon.tl.types import Message
from telethon.errors import FloodWaitError, ChatForwardsRestrictedError
from src.rule import ForwardingRule
from src.filters import MessageFilter
from src.logger import get_logger
from src.utils import get_media_description
from src.constants import (
    ENTITY_FETCH_TIMEOUT,
    FORWARD_PREVIEW_LENGTH
)

logger = get_logger()


class MessageForwarder:
    """消息转发器"""

    def __init__(
        self,
        client: TelegramClient,
        rule: ForwardingRule,
        message_filter: MessageFilter,
        bot_manager=None,
    ):
        """
        初始化转发器

        参数:
            client: Telegram 客户端
            rule: 转发规则
            message_filter: 消息过滤器
            bot_manager: Bot 管理器（可选，用于触发 UI 更新）
        """
        self.client = client
        self.rule = rule
        self.filter = message_filter
        self.bot_manager = bot_manager

        # 统计信息
        self.forwarded_count = 0
        self.filtered_count = 0

        # 媒体组去重缓存
        self._processed_media_groups: dict = {}  # {grouped_id: timestamp}

    async def handle_message(self, event) -> None:
        """
        处理新消息事件（由 bot_manager 中央处理器调用，已通过过滤）

        参数:
            event: Telethon 消息事件
        """
        message: Message = event.message

        # 获取消息文本
        raw_text = message.text or get_media_description(message)
        raw_text = raw_text.replace('\n', ' ')
        message_preview = f"{raw_text[:50]}..." if len(raw_text) > 50 else raw_text

        # 获取基础 ID
        sender_id = event.sender_id
        chat_id = event.chat_id

        # 获取详细资料
        try:
            sender_task = event.get_sender()
            chat_task = event.get_chat()
            sender, chat = await asyncio.wait_for(
                asyncio.gather(sender_task, chat_task),
                timeout=ENTITY_FETCH_TIMEOUT
            )

            sender_name = utils.get_display_name(sender) if sender else 'Unknown'
            chat_title = utils.get_display_name(chat) if chat else 'Unknown'
        except asyncio.TimeoutError:
            sender_name, chat_title = "Timeout", "Timeout"
        except Exception as e:
            logger.error(f"获取实体信息失败: {e}")
            sender_name, chat_title = "Error", "Error"

        logger.info(
            f"收到消息 - 来自: {chat_title} ({chat_id}), "
            f"发送者: {sender_name} ({sender_id}), 内容: {message_preview}"
        )

        # 转发消息
        try:
            await self.forward_message(message, chat_title, sender_id)

            # 延迟，避免触发限制
            if self.rule.delay > 0:
                await asyncio.sleep(self.rule.delay)

        except FloodWaitError as e:
            logger.warning(f"触发速率限制，需要等待 {e.seconds} 秒")
            await asyncio.sleep(e.seconds)
            # 重试
            await self.forward_message(message, chat_title, sender_id)
        except Exception as e:
            logger.error(f"转发消息失败: {e}", exc_info=True)

    async def forward_message(self, message: Message, source_chat: str, sender_id: int) -> None:
        """
        转发消息到多个目标

        转发策略:
        1. 检测是否是 noforwards 消息和媒体组
        2. 根据配置选择转发方法:
           - noforwards + force_forward → 下载+重新上传
           - noforwards + !force_forward → 引用复制（失败则降级）
           - !noforwards + preserve_format → 直接转发
           - !noforwards + !preserve_format → 引用复制
        3. 异常处理: ChatForwardsRestrictedError 自动降级

        参数:
            message: 要转发的消息
            source_chat: 源聊天名称
            sender_id: 发送者 ID
        """
        targets = self.rule.target_chats

        if not targets:
            logger.error("未配置目标聊天")
            return

        # 检查是否受 noforwards 限制
        is_noforwards = getattr(message.chat, 'noforwards', False) if message.chat else False

        # 检查是否是媒体组
        messages = await self._get_media_group_messages(message)
        is_media_group = len(messages) > 1

        # 媒体组去重：只处理一次
        if is_media_group:
            import time
            current_time = time.time()

            # 检查是否已处理
            if message.grouped_id in self._processed_media_groups:
                if current_time - self._processed_media_groups[message.grouped_id] < 60:
                    logger.debug(f"[{self.rule.name}] 媒体组已处理，跳过: grouped_id={message.grouped_id}")
                    return
                else:
                    # 过期，删除旧记录
                    del self._processed_media_groups[message.grouped_id]

            # 记录处理时间
            self._processed_media_groups[message.grouped_id] = current_time

            # 定期清理过期缓存
            if len(self._processed_media_groups) > 100:
                expired = [gid for gid, ts in self._processed_media_groups.items()
                          if current_time - ts > 60]
                for gid in expired:
                    del self._processed_media_groups[gid]

        # 对媒体组进行过滤判断
        if is_media_group:
            # 检查是否有任何一条消息包含文本
            has_text = any(msg.text for msg in messages)

            if has_text:
                # 有文本时，检查是否有任何一条消息匹配过滤条件
                has_match = False
                for msg in messages:
                    if self.filter.should_forward(msg, sender_id=sender_id):
                        has_match = True
                        break

                if not has_match:
                    logger.debug(f"[{self.rule.name}] 媒体组被过滤 (无匹配消息) - grouped_id: {message.grouped_id}")
                    self.filtered_count += 1
                    return
            # 如果所有消息都无文本，默认通过（不过滤）

        # 获取消息预览
        message_preview = (message.text or get_media_description(message))[:FORWARD_PREVIEW_LENGTH]

        # 记录成功转发的目标数量
        success_count = 0

        # 对每个目标进行转发
        for target in targets:
            try:
                # 选择转发方法
                if is_noforwards and self.rule.force_forward:
                    # noforwards + 强制转发 → 下载+重新上传
                    await self._forward_download(messages, target, source_chat)
                elif is_noforwards:
                    # noforwards + 非强制 → 尝试引用复制，失败则降级
                    try:
                        await self._forward_copy(messages, target, source_chat)
                    except Exception as e:
                        logger.info(f"[{self.rule.name}] 引用复制失败，降级为下载重传: {e}")
                        await self._forward_download(messages, target, source_chat)
                elif self.rule.preserve_format:
                    # 正常消息 + 保留格式 → 直接转发
                    await self._forward_direct(messages, target)
                else:
                    # 正常消息 + 不保留格式 → 引用复制
                    await self._forward_copy(messages, target, source_chat)

                success_count += 1

                # 添加延迟，避免触发限制
                if self.rule.delay > 0 and target != targets[-1]:
                    await asyncio.sleep(self.rule.delay)

            except ChatForwardsRestrictedError:
                # 兜底：转发受限，自动降级为下载+重新上传
                logger.warning(f"[{self.rule.name}] 转发受限，降级为下载重传")
                try:
                    await self._forward_download(messages, target, source_chat)
                    success_count += 1
                except Exception as e2:
                    logger.error(f"降级转发到 {target} 失败: {e2}")
            except Exception as e:
                logger.error(f"转发消息到 {target} 失败: {e}")

        # 统计
        if success_count > 0:
            self.forwarded_count += 1
            group_info = f" (媒体组 {len(messages)} 项)" if is_media_group else ""
            logger.info(
                f"[{self.rule.name}] ✅ 转发成功{group_info}: \"{message_preview}\" "
                f"→ {success_count}/{len(targets)} 目标 | 总计: {self.forwarded_count}"
            )
        else:
            logger.error(f"❌ 转发失败: \"{message_preview}\" → 所有目标均失败")

    async def _forward_direct(self, messages: List[Message], target) -> None:
        """
        直接转发消息（保留"转发自"标记）

        参数:
            messages: 要转发的消息列表（媒体组或单条消息）
            target: 目标聊天
        """
        await self.client.forward_messages(target, messages)
        logger.info(f"[{self.rule.name}] ✓ 直接转发到 {target}")

    async def _forward_copy(self, messages: List[Message], target, source_chat: str) -> None:
        """
        通过引用媒体 ID 复制消息（不保留"转发自"标记）

        参数:
            messages: 要复制的消息列表（媒体组或单条消息）
            target: 目标聊天
            source_chat: 源聊天名称
        """
        # 处理单条消息
        if len(messages) == 1:
            message = messages[0]
            message_text = message.text or ""

            # 添加来源信息
            if self.rule.add_source_info:
                message_text = f"📢 来源: {source_chat}\n\n{message_text}"

            # 发送消息
            if message.media:
                await self.client.send_message(
                    target,
                    message_text,
                    file=message.media,
                    formatting_entities=message.entities
                )
            else:
                await self.client.send_message(
                    target,
                    message_text,
                    formatting_entities=message.entities
                )
        else:
            # 处理媒体组
            # 第一条消息包含文本和来源信息
            first_message = messages[0]
            message_text = first_message.text or ""

            if self.rule.add_source_info:
                message_text = f"📢 来源: {source_chat}\n\n{message_text}"

            # 收集所有媒体
            media_list = [msg.media for msg in messages if msg.media]

            # 发送媒体组
            await self.client.send_file(
                target,
                file=media_list,
                caption=message_text,
                formatting_entities=first_message.entities
            )

        logger.info(f"[{self.rule.name}] ✓ 引用复制到 {target}")

    async def _forward_download(self, messages: List[Message], target, source_chat: str) -> None:
        """
        通过下载+重新上传的方式复制消息（绕过 noforwards 限制）
        媒体文件下载到临时目录，发送后立即删除

        参数:
            messages: 要复制的消息列表（媒体组或单条消息）
            target: 目标聊天
            source_chat: 源聊天名称
        """
        # 处理单条消息
        if len(messages) == 1:
            await self._download_and_send_single(messages[0], target, source_chat)
        else:
            # 处理媒体组
            await self._download_and_send_group(messages, target, source_chat)

        logger.info(f"[{self.rule.name}] ✓ 下载重传到 {target}")

    async def _download_and_send_single(self, message: Message, target, source_chat: str) -> None:
        """下载并发送单条消息"""
        message_text = message.text or ""

        # 添加来源信息
        if self.rule.add_source_info:
            message_text = f"📢 来源: {source_chat}\n\n{message_text}"

        if message.media:
            # 下载媒体到临时目录
            temp_dir = os.path.join(tempfile.gettempdir(), "tg-box-cache")
            os.makedirs(temp_dir, exist_ok=True)

            file_path = None
            try:
                logger.info(f"[{self.rule.name}] ⬇️ 开始下载媒体文件...")

                file_path = await self.client.download_media(message, file=temp_dir)

                if not file_path:
                    logger.error(f"[{self.rule.name}] 媒体下载失败，返回空路径")
                    return

                file_size_mb = os.path.getsize(file_path) / 1048576
                file_name = os.path.basename(file_path)
                logger.info(f"[{self.rule.name}] ⬇️ 下载完成: {file_name} ({file_size_mb:.1f} MB)")

                # 重新上传发送
                logger.info(f"[{self.rule.name}] ⬆️ 开始上传到 {target}...")
                await self.client.send_file(
                    target,
                    file=file_path,
                    caption=message_text,
                    formatting_entities=message.entities,
                )
            finally:
                # 确保临时文件被删除
                if file_path and os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                        logger.debug(f"已清理临时文件: {file_path}")
                    except OSError as e:
                        logger.warning(f"清理临时文件失败: {file_path}, {e}")
        else:
            # 纯文本消息直接发送
            await self.client.send_message(
                target,
                message_text,
                formatting_entities=message.entities,
            )

    async def _download_and_send_group(self, messages: List[Message], target, source_chat: str) -> None:
        """下载并发送媒体组"""
        first_message = messages[0]
        message_text = first_message.text or ""

        # 添加来源信息
        if self.rule.add_source_info:
            message_text = f"📢 来源: {source_chat}\n\n{message_text}"

        # 下载所有媒体
        temp_dir = os.path.join(tempfile.gettempdir(), "tg-box-cache")
        os.makedirs(temp_dir, exist_ok=True)

        file_paths = []
        try:
            logger.info(f"[{self.rule.name}] ⬇️ 开始下载媒体组 ({len(messages)} 项)...")

            for i, message in enumerate(messages):
                if message.media:
                    file_path = await self.client.download_media(message, file=temp_dir)
                    if file_path:
                        file_paths.append(file_path)
                        file_name = os.path.basename(file_path)
                        logger.debug(f"[{self.rule.name}] ⬇️ 下载 {i+1}/{len(messages)}: {file_name}")

            if not file_paths:
                logger.error(f"[{self.rule.name}] 媒体组下载失败，无有效文件")
                return

            logger.info(f"[{self.rule.name}] ⬇️ 媒体组下载完成: {len(file_paths)} 个文件")

            # 重新上传发送
            logger.info(f"[{self.rule.name}] ⬆️ 开始上传媒体组到 {target}...")
            await self.client.send_file(
                target,
                file=file_paths,
                caption=message_text,
                formatting_entities=first_message.entities,
            )
        finally:
            # 确保所有临时文件被删除
            for file_path in file_paths:
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                        logger.debug(f"已清理临时文件: {file_path}")
                    except OSError as e:
                        logger.warning(f"清理临时文件失败: {file_path}, {e}")

    async def _get_media_group_messages(self, message: Message) -> List[Message]:
        """
        获取媒体组的所有消息

        参数:
            message: 消息对象

        返回:
            消息列表（如果不是媒体组，返回单条消息的列表）
        """
        # 检查是否是媒体组
        if not message.grouped_id:
            return [message]

        try:
            # 等待一小段时间，确保媒体组的所有消息都已到达
            await asyncio.sleep(0.5)

            # 搜索最近的消息，找出同一媒体组的所有消息
            messages = []
            async for msg in self.client.iter_messages(
                message.chat_id,
                limit=50  # 搜索最近 50 条消息
            ):
                if msg.grouped_id == message.grouped_id:
                    messages.append(msg)
                # 媒体组通常不会超过 10 条，找到足够多可以提前退出
                if len(messages) >= 10:
                    break

            if messages:
                # 按 ID 排序
                messages.sort(key=lambda m: m.id)
                logger.debug(f"[{self.rule.name}] 检测到媒体组: {len(messages)} 条消息")
                return messages
            else:
                logger.debug(f"[{self.rule.name}] 未找到媒体组其他消息，作为单条处理")
                return [message]

        except Exception as e:
            logger.warning(f"获取媒体组消息失败: {e}，将作为单条消息处理")
            return [message]

    def get_stats(self) -> dict:
        """
        获取转发统计

        返回:
            统计信息字典
        """
        return {
            "forwarded": self.forwarded_count,
            "filtered": self.filtered_count,
            "total": self.forwarded_count + self.filtered_count
        }

