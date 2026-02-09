"""
消息过滤模块
支持正则表达式和关键词匹配
"""
import re
from typing import List
from src.logger import get_logger

logger = get_logger()


class MessageFilter:
    """消息过滤器类"""
    
    def __init__(
        self,
        regex_patterns: List[str] = None,
        keywords: List[str] = None,
        mode: str = "whitelist",
        ignored_user_ids: List[int] = None,
        ignored_keywords: List[str] = None
    ):
        """
        初始化过滤器
        
        参数:
            regex_patterns: 正则表达式列表
            keywords: 关键词列表
            mode: 过滤模式 (whitelist 或 blacklist)
            ignored_user_ids: 忽略的用户 ID 列表
            ignored_keywords: 忽略的关键词列表
        """
        self.regex_patterns = regex_patterns or []
        self.keywords = keywords or []
        self.mode = mode.lower()
        self.ignored_user_ids = ignored_user_ids or []
        self.ignored_keywords = ignored_keywords or []
        
        # 编译正则表达式
        self.compiled_patterns = []
        for pattern in self.regex_patterns:
            try:
                self.compiled_patterns.append(re.compile(pattern))
            except re.error as e:
                logger.error(f"无效的正则表达式 '{pattern}': {e}")
        
        logger.info(f"过滤器初始化完成 - 模式: {self.mode}, "
                   f"正则规则: {len(self.compiled_patterns)}, "
                   f"关键词: {len(self.keywords)}, "
                   f"忽略用户: {len(self.ignored_user_ids)}, "
                   f"忽略关键词: {len(self.ignored_keywords)}")
    
    def matches_regex(self, text: str) -> bool:
        """
        检查文本是否匹配任一正则表达式
        
        参数:
            text: 要检查的文本
        
        返回:
            是否匹配
        """
        if not self.compiled_patterns:
            return False
        
        for pattern in self.compiled_patterns:
            if pattern.search(text):
                logger.debug(f"文本匹配正则规则: {pattern.pattern}")
                return True
        
        return False
    
    def matches_keyword(self, text: str) -> bool:
        """
        检查文本是否包含任一关键词
        
        参数:
            text: 要检查的文本
        
        返回:
            是否匹配
        """
        if not self.keywords:
            return False
        
        text_lower = text.lower()
        for keyword in self.keywords:
            if keyword.lower() in text_lower:
                logger.debug(f"文本包含关键词: {keyword}")
                return True
        
        return False
    
    def is_ignored_user(self, user_id: int) -> bool:
        """
        检查用户是否在忽略列表中
        
        参数:
            user_id: 用户 ID
        
        返回:
            是否在忽略列表中
        """
        if not self.ignored_user_ids:
            return False
        return user_id in self.ignored_user_ids
    
    def is_ignored_content(self, text: str) -> bool:
        """
        检查消息内容是否包含忽略关键词
        
        参数:
            text: 消息文本
        
        返回:
            是否包含忽略关键词
        """
        if not self.ignored_keywords or not text:
            return False
        
        text_lower = text.lower()
        for keyword in self.ignored_keywords:
            if keyword.lower() in text_lower:
                logger.debug(f"消息包含忽略关键词: {keyword}")
                return True
        return False
    
    def should_forward(self, message_text: str, sender_id: int = None) -> bool:
        """
        判断消息是否应该被转发
        
        参数:
            message_text: 消息文本
            sender_id: 发送者 ID（可选）
        
        返回:
            是否应该转发
        """
        # 优先检查忽略列表（黑名单模式）
        if sender_id and self.is_ignored_user(sender_id):
            logger.debug(f"消息来自忽略用户: {sender_id}")
            return False
        
        if self.is_ignored_content(message_text):
            return False
        
        # 空消息处理：白名单模式不转发，黑名单模式转发
        if not message_text:
            return self.mode == "blacklist"
        
        # 检查是否匹配过滤规则
        matches = self.matches_regex(message_text) or self.matches_keyword(message_text)
        
        # 根据模式决定是否转发
        if self.mode == "whitelist":
            # 白名单模式：匹配则转发
            should_forward = matches
        else:
            # 黑名单模式：不匹配则转发
            should_forward = not matches
        
        logger.debug(f"过滤判断 - 模式: {self.mode}, 匹配: {matches}, 转发: {should_forward}")
        return should_forward
    
    def update_rules(
        self,
        regex_patterns: List[str] = None,
        keywords: List[str] = None,
        mode: str = None
    ) -> None:
        """
        更新过滤规则
        
        参数:
            regex_patterns: 新的正则表达式列表
            keywords: 新的关键词列表
            mode: 新的过滤模式
        """
        if regex_patterns is not None:
            self.regex_patterns = regex_patterns
            self.compiled_patterns = []
            for pattern in regex_patterns:
                try:
                    self.compiled_patterns.append(re.compile(pattern))
                except re.error as e:
                    logger.error(f"无效的正则表达式 '{pattern}': {e}")
        
        if keywords is not None:
            self.keywords = keywords
        
        if mode is not None:
            self.mode = mode.lower()
        
        logger.info(f"过滤规则已更新 - 模式: {self.mode}, "
                   f"正则规则: {len(self.compiled_patterns)}, "
                   f"关键词: {len(self.keywords)}")
