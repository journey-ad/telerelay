"""
消息转发模块
处理消息转发逻辑
"""
import asyncio
from typing import Optional
from telethon import TelegramClient
from telethon import utils
from telethon.tl.types import Message
from telethon.errors import FloodWaitError
from src.config import Config
from src.filters import MessageFilter
from src.logger import get_logger
from src.utils import get_media_description
from src.constants import (
    ENTITY_FETCH_TIMEOUT,
    MESSAGE_PREVIEW_LENGTH,
    FORWARD_PREVIEW_LENGTH
)

logger = get_logger()


class MessageForwarder:
    """消息转发器类"""
    
    def __init__(
        self,
        client: TelegramClient,
        config: Config,
        message_filter: MessageFilter,
        bot_manager=None  # 可选的 bot_manager 用于触发 UI 更新
    ):
        """
        初始化转发器
        
        参数:
            client: Telegram 客户端
            config: 配置对象
            message_filter: 消息过滤器
            bot_manager: Bot 管理器（可选）
        """
        self.client = client
        self.config = config
        self.filter = message_filter
        self.bot_manager = bot_manager
        
        # 统计信息
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
        raw_text = message.text or get_media_description(message)
        raw_text = raw_text.replace('\n', ' ')
        message_preview = f"{raw_text[:50]}..." if len(raw_text) > 50 else raw_text
        
        # 获取基础 ID
        sender_id = event.sender_id
        chat_id = event.chat_id

        # 先过滤，通过后再去拿详细信息
        if not self.filter.should_forward(raw_text, sender_id=sender_id):
            self.filtered_count += 1
            # 过滤时记录 ID 即可，节省 API 调用
            logger.debug(f"消息被过滤 - ChatID: {chat_id}, SenderID: {sender_id}, 内容: {message_preview}")
            return

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
        
        # 获取消息预览
        message_preview = (message.text or get_media_description(message))[:FORWARD_PREVIEW_LENGTH]
        
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
                    logger.info(f"✓ 转发消息到 {target}")
                else:
                    # 复制消息（不保留转发标记）
                    message_text = message.text or ""
                    
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
                    
                    logger.info(f"✓ 复制消息到 {target}")
                
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
            logger.info(f"✅ 转发成功: \"{message_preview}\" → {success_count}/{len(targets)} 目标 | 总计: {self.forwarded_count}")
            # 触发 UI 更新
            if self.bot_manager:
                self.bot_manager.trigger_ui_update()
        else:
            logger.error(f"❌ 转发失败: \"{message_preview}\" → 所有目标均失败")
    
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
