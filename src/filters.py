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
        mode: str = "whitelist"
    ):
        """
        初始化过滤器
        
        参数:
            regex_patterns: 正则表达式列表
            keywords: 关键词列表
            mode: 过滤模式 (whitelist 或 blacklist)
        """
        self.regex_patterns = regex_patterns or []
        self.keywords = keywords or []
        self.mode = mode.lower()
        
        # 编译正则表达式
        self.compiled_patterns = []
        for pattern in self.regex_patterns:
            try:
                self.compiled_patterns.append(re.compile(pattern))
            except re.error as e:
                logger.error(f"无效的正则表达式 '{pattern}': {e}")
        
        logger.info(f"过滤器初始化完成 - 模式: {self.mode}, "
                   f"正则规则: {len(self.compiled_patterns)}, "
                   f"关键词: {len(self.keywords)}")
    
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
    
    def should_forward(self, message_text: str) -> bool:
        """
        判断消息是否应该被转发
        
        参数:
            message_text: 消息文本
        
        返回:
            是否应该转发
        """
        if not message_text:
            # 空消息处理：白名单模式不转发，黑名单模式转发
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
