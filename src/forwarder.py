"""
消息转发模块
处理消息转发逻辑
"""
import os
import tempfile
import asyncio
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


        # 只有通过过滤的消息才去获取详细资料
        try:
            sender_task = event.get_sender()
            chat_task = event.get_chat()
            sender, chat = await asyncio.wait_for(asyncio.gather(sender_task, chat_task), timeout=ENTITY_FETCH_TIMEOUT)

            # 获取发送者和聊天的名称
            sender_name = utils.get_display_name(sender) if sender else 'Unknown'
            chat_title = utils.get_display_name(chat) if chat else 'Unknown'
        except asyncio.TimeoutError:
            sender_name, chat_title = "Timeout", "Timeout"
        except Exception as e:
            logger.error(f"获取实体信息失败: {e}")
            sender_name, chat_title = "Error", "Error"
        
        logger.info(f"收到消息 - 来自: {chat_title} ({chat_id}), 发送者: {sender_name} ({sender_id}), 内容: {message_preview}")
        
        # 转发消息
        try:
            await self.forward_message(message, chat_title)
            
            # 延迟，避免触发限制
            if self.rule.delay > 0:
                await asyncio.sleep(self.rule.delay)
                
        except FloodWaitError as e:
            logger.warning(f"触发速率限制，需要等待 {e.seconds} 秒")
            await asyncio.sleep(e.seconds)
            # 重试
            await self.forward_message(message, chat_title)
        except Exception as e:
            logger.error(f"转发消息失败: {e}", exc_info=True)
    
    async def _copy_message(self, message: Message, target, source_chat: str) -> None:
        """
        通过下载+重新上传的方式复制消息（绕过 noforwards 限制）
        媒体文件下载到临时目录，发送后立即删除
        
        参数:
            message: 要复制的消息
            target: 目标聊天
            source_chat: 源聊天名称
        """
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
                
                # download_media 返回文件路径，自动保留原始文件名
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
        
        logger.info(f"[{self.rule.name}] ✓ 强制复制消息到 {target}")

    async def forward_message(self, message: Message, source_chat: str) -> None:
        """
        转发消息到多个目标
        
        策略：
        1. force_forward 开启 → 直接下载+重新上传（始终绕过限制）
        2. noforwards 聊天 → 先尝试复制引用，失败则下载+重新上传
        3. 正常聊天 → 按 preserve_format 设置转发或复制
        
        参数:
            message: 要转发的消息
            source_chat: 源聊天名称
        """
        targets = self.rule.target_chats
        
        if not targets:
            logger.error("未配置目标聊天")
            return
        
        # 获取消息预览
        message_preview = (message.text or get_media_description(message))[:FORWARD_PREVIEW_LENGTH]
        
        # 检查是否受 noforwards 限制
        is_noforwards = getattr(message.chat, 'noforwards', False) if message.chat else False
        
        # 记录成功转发的目标数量
        success_count = 0
        
        # 对每个目标进行转发
        for target in targets:
            try:
                if self.rule.force_forward:
                    # 强制转发模式：直接下载+重新上传
                    await self._copy_message(message, target, source_chat)
                elif is_noforwards:
                    # noforwards 限制：先尝试复制引用
                    try:
                        await self._send_copy(message, target, source_chat)
                    except Exception:
                        # 复制引用失败，降级为下载+重新上传
                        logger.info(f"[{self.rule.name}] 复制引用失败，降级为下载重传")
                        await self._copy_message(message, target, source_chat)
                elif self.rule.preserve_format:
                    # 保留原始格式（直接转发）
                    await self.client.forward_messages(
                        target,
                        message
                    )
                    logger.info(f"[{self.rule.name}] ✓ 转发消息到 {target}")
                else:
                    # 复制消息（不保留转发标记）
                    await self._send_copy(message, target, source_chat)
                
                success_count += 1
                
                # 添加延迟，避免触发限制
                if self.rule.delay > 0 and target != targets[-1]:
                    await asyncio.sleep(self.rule.delay)
                
            except ChatForwardsRestrictedError:
                # 兜底：转发受限，自动降级为下载+重新上传
                logger.warning(f"[{self.rule.name}] 聊天限制转发，自动降级为下载重传")
                try:
                    await self._copy_message(message, target, source_chat)
                    success_count += 1
                except Exception as e2:
                    logger.error(f"下载重传到 {target} 也失败: {e2}")
            except Exception as e:
                logger.error(f"转发消息到 {target} 时出错: {e}")
                # 继续转发到其他目标，不抛出异常
        
        # 只要成功转发到至少一个目标就计数
        if success_count > 0:
            self.forwarded_count += 1
            logger.info(f"[{self.rule.name}] ✅ 转发成功: \"{message_preview}\" → {success_count}/{len(targets)} 目标 | 总计: {self.forwarded_count}")
        else:
            logger.error(f"❌ 转发失败: \"{message_preview}\" → 所有目标均失败")
    
    async def _send_copy(self, message: Message, target, source_chat: str) -> None:
        """
        通过引用媒体 ID 复制消息（不保留转发标记）
        
        参数:
            message: 要复制的消息
            target: 目标聊天
            source_chat: 源聊天名称
        """
        message_text = message.text or ""
        
        # 添加来源信息
        if self.rule.add_source_info:
            message_text = f"📢 来源: {source_chat}\n\n{message_text}"
        
        # 发送消息
        if message.media:
            # 如果有媒体文件，一起发送
            await self.client.send_message(
                target,
                message_text,
                file=message.media
            )
        else:
            # 纯文本消息
            await self.client.send_message(
                target,
                message_text
            )
        
        logger.info(f"[{self.rule.name}] ✓ 复制消息到 {target}")
    
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
