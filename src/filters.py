"""
消息过滤模块
支持正则表达式、关键词匹配、媒体类型和文件大小过滤
"""
import re
from typing import List, Optional, Union
from telethon.tl.types import (
    Message,
    MessageMediaPhoto, MessageMediaDocument, MessageMediaWebPage,
    DocumentAttributeVideo, DocumentAttributeAudio, DocumentAttributeSticker,
    DocumentAttributeAnimated
)
from src.logger import get_logger

logger = get_logger()

# 支持的媒体类型
MEDIA_TYPES = ["text", "photo", "video", "document", "audio", "voice", "sticker", "animation", "webpage"]


def get_media_type(message: Message) -> str:
    """获取消息的媒体类型"""
    if not message.media:
        return "text"
    
    if isinstance(message.media, MessageMediaPhoto):
        return "photo"
    
    if isinstance(message.media, MessageMediaWebPage):
        return "webpage"
    
    if isinstance(message.media, MessageMediaDocument):
        doc = message.media.document
        if doc:
            # 根据文档属性判断类型
            for attr in doc.attributes:
                if isinstance(attr, DocumentAttributeSticker):
                    return "sticker"
                if isinstance(attr, DocumentAttributeAnimated):
                    return "animation"
                if isinstance(attr, DocumentAttributeVideo):
                    # 区分视频和 GIF 动画
                    if getattr(attr, 'round_message', False):
                        return "video"  # 视频消息
                    return "video"
                if isinstance(attr, DocumentAttributeAudio):
                    if getattr(attr, 'voice', False):
                        return "voice"
                    return "audio"
            return "document"
    
    return "text"


def get_file_size(message: Message) -> int:
    """获取消息中文件的大小（字节），无文件返回 0"""
    if not message.media:
        return 0
    
    if isinstance(message.media, MessageMediaDocument):
        doc = message.media.document
        if doc:
            return doc.size or 0
    
    if isinstance(message.media, MessageMediaPhoto):
        # 图片取最大尺寸
        photo = message.media.photo
        if photo and photo.sizes:
            for size in reversed(photo.sizes):
                if hasattr(size, 'size'):
                    return size.size
    
    return 0


class MessageFilter:
    """消息过滤器"""
    
    def __init__(
        self,
        regex_patterns: List[str] = None,
        keywords: List[str] = None,
        mode: str = "whitelist",
        ignored_user_ids: List[int] = None,
        ignored_keywords: List[str] = None,
        # 新增：媒体过滤
        media_types: List[str] = None,
        max_file_size: int = 0,
        min_file_size: int = 0,
    ):
        """
        初始化过滤器
        
        参数:
            regex_patterns: 正则表达式列表
            keywords: 关键词列表
            mode: 过滤模式 (whitelist 或 blacklist)
            ignored_user_ids: 忽略的用户 ID 列表
            ignored_keywords: 忽略的关键词列表
            media_types: 允许的媒体类型列表（空列表=全部允许）
            max_file_size: 最大文件大小（字节），0=不限制
            min_file_size: 最小文件大小（字节）
        """
        self.regex_patterns = regex_patterns or []
        self.keywords = keywords or []
        self.mode = mode.lower()
        self.ignored_user_ids = ignored_user_ids or []
        self.ignored_keywords = ignored_keywords or []
        self.media_types = media_types or []
        self.max_file_size = max_file_size
        self.min_file_size = min_file_size
        
        # 编译正则表达式
        self.compiled_patterns = []
        for pattern in self.regex_patterns:
            try:
                self.compiled_patterns.append(re.compile(pattern))
            except re.error as e:
                logger.error(f"无效的正则表达式 '{pattern}': {e}")
        
        logger.info(
            f"过滤器初始化 - 模式: {self.mode}, "
            f"正则: {len(self.compiled_patterns)}, 关键词: {len(self.keywords)}, "
            f"媒体类型: {self.media_types or '全部'}, "
            f"文件大小: {self.min_file_size}-{self.max_file_size or '不限'}"
        )
    
    def check_media_type(self, message: Message) -> bool:
        """检查媒体类型是否允许。返回 True 表示允许"""
        if not self.media_types:
            return True  # 空列表 = 全部允许
        
        media_type = get_media_type(message)
        allowed = media_type in self.media_types
        if not allowed:
            logger.debug(f"媒体类型被过滤: {media_type} 不在允许列表 {self.media_types}")
        return allowed
    
    def check_file_size(self, message: Message) -> bool:
        """检查文件大小是否在限制范围内。返回 True 表示允许"""
        file_size = get_file_size(message)
        
        # 无文件 = 不检查大小
        if file_size == 0:
            return True
        
        # 检查最小大小
        if self.min_file_size > 0 and file_size < self.min_file_size:
            logger.debug(f"文件太小被过滤: {file_size} < {self.min_file_size}")
            return False
        
        # 检查最大大小
        if self.max_file_size > 0 and file_size > self.max_file_size:
            logger.debug(f"文件太大被过滤: {file_size} > {self.max_file_size}")
            return False
        
        return True
    
    def matches_text(self, text: str) -> bool:
        """检查文本是否匹配正则或关键词"""
        if not text:
            return False
        
        # 检查正则
        for pattern in self.compiled_patterns:
            if pattern.search(text):
                logger.debug(f"匹配正则: {pattern.pattern}")
                return True
        
        # 检查关键词
        text_lower = text.lower()
        for keyword in self.keywords:
            if keyword.lower() in text_lower:
                logger.debug(f"匹配关键词: {keyword}")
                return True
        
        return False
    
    def is_ignored(self, text: str, sender_id: int = None) -> bool:
        """检查是否应该被忽略（优先级最高）"""
        # 检查用户黑名单
        if sender_id and sender_id in self.ignored_user_ids:
            logger.debug(f"忽略用户: {sender_id}")
            return True
        
        # 检查忽略关键词
        if text:
            text_lower = text.lower()
            for keyword in self.ignored_keywords:
                if keyword.lower() in text_lower:
                    logger.debug(f"忽略关键词: {keyword}")
                    return True
        
        return False
    
    def should_forward(self, message: Union[Message, str], sender_id: int = None) -> bool:
        """
        判断消息是否应该被转发
        
        参数:
            message: Message 对象或消息文本
            sender_id: 发送者 ID
        
        返回:
            是否应该转发
        """
        # 兼容：支持传入字符串（旧调用方式）
        if isinstance(message, str):
            text = message
            msg_obj = None
        else:
            text = message.text or ""
            msg_obj = message
        
        # 1. 优先检查忽略列表
        if self.is_ignored(text, sender_id):
            return False
        
        # 2. 检查媒体类型（仅当传入 Message 对象时）
        if msg_obj and not self.check_media_type(msg_obj):
            return False
        
        # 3. 检查文件大小
        if msg_obj and not self.check_file_size(msg_obj):
            return False
        
        # 4. 文本匹配规则
        # 如果没有配置任何规则，白名单模式-不转发，黑名单模式-转发
        if not self.compiled_patterns and not self.keywords:
            return self.mode == "blacklist"
        
        matches = self.matches_text(text)
        
        if self.mode == "whitelist":
            return matches  # 白名单：匹配才转发
        else:
            return not matches  # 黑名单：不匹配才转发
