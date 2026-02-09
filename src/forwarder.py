"""
消息转发模块
处理消息转发逻辑
"""
import asyncio
from typing import Optional
from telethon import TelegramClient
from telethon.tl.types import Message
from telethon.errors import FloodWaitError
from src.config import Config
from src.filters import MessageFilter
from src.logger import get_logger

logger = get_logger(__name__)


class MessageForwarder:
    """消息转发器类"""
    
    def __init__(
        self,
        client: TelegramClient,
        config: Config,
        message_filter: MessageFilter
    ):
        """
        初始化转发器
        
        参数:
            client: Telegram 客户端
            config: 配置对象
            message_filter: 消息过滤器
        """
        self.client = client
        self.config = config
        self.filter = message_filter
        self.forwarded_count = 0
        self.filtered_count = 0
    
    async def handle_message(self, event) -> None:
        """
        处理新消息事件
        
        参数:
            event: Telethon 消息事件
        """
        message: Message = event.message
        
        # 获取消息文本
        message_text = message.text or ""
        
        # 如果没有文本，尝试获取 caption（图片、视频等）
        if not message_text and hasattr(message, 'caption') and message.caption:
            message_text = message.caption
        
        # 获取发送者信息
        sender = await event.get_sender()
        chat = await event.get_chat()
        
        sender_name = getattr(sender, 'first_name', 'Unknown') if sender else 'Unknown'
        chat_title = getattr(chat, 'title', str(chat.id)) if chat else 'Unknown'
        
        logger.debug(f"收到消息 - 来自: {chat_title} ({chat.id}), 发送者: {sender_name}")
        
        # 过滤消息
        if not self.filter.should_forward(message_text):
            self.filtered_count += 1
            logger.debug(f"消息被过滤 - 内容: {message_text[:50]}...")
            return
        
        # 转发消息
        try:
            await self.forward_message(message, chat_title)
            
            # 延迟，避免触发限制
            if self.config.forward_delay > 0:
                await asyncio.sleep(self.config.forward_delay)
                
        except FloodWaitError as e:
            logger.warning(f"触发速率限制，需要等待 {e.seconds} 秒")
            await asyncio.sleep(e.seconds)
            # 重试
            await self.forward_message(message, chat_title)
        except Exception as e:
            logger.error(f"转发消息失败: {e}", exc_info=True)
    
    async def forward_message(self, message: Message, source_chat: str) -> None:
        """
        转发消息到多个目标
        
        参数:
            message: 要转发的消息
            source_chat: 源聊天名称
        """
        targets = self.config.target_chats
        
        if not targets:
            logger.error("未配置目标聊天")
            return
        
        # 记录成功转发的目标数量
        success_count = 0
        
        # 对每个目标进行转发
        for target in targets:
            try:
                if self.config.preserve_format:
                    # 保留原始格式（直接转发）
                    await self.client.forward_messages(
                        target,
                        message
                    )
                    logger.info(f"✓ 已转发消息到 {target}")
                else:
                    # 复制消息（不保留转发标记）
                    message_text = message.text or message.caption or ""
                    
                    # 添加来源信息
                    if self.config.add_source_info:
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
                    
                    logger.info(f"✓ 已复制消息到 {target}")
                
                success_count += 1
                
                # 添加延迟，避免触发限制
                if self.config.forward_delay > 0 and target != targets[-1]:  # 最后一个目标不需要延迟
                    await asyncio.sleep(self.config.forward_delay)
                
            except Exception as e:
                logger.error(f"转发消息到 {target} 时出错: {e}")
                # 继续转发到其他目标，不抛出异常
        
        # 只要成功转发到至少一个目标就计数
        if success_count > 0:
            self.forwarded_count += 1
            logger.info(f"消息已成功转发到 {success_count}/{len(targets)} 个目标")
    
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
