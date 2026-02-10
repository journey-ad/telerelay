"""
Message filtering module
Supports regex, keyword matching, media type and file size filtering
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
from src.i18n import t

logger = get_logger()

# Supported media types
MEDIA_TYPES = ["text", "photo", "video", "document", "audio", "voice", "sticker", "animation", "webpage"]


def get_media_type(message: Message) -> str:
    """Get the media type of a message"""
    if not message.media:
        return "text"
    
    if isinstance(message.media, MessageMediaPhoto):
        return "photo"
    
    if isinstance(message.media, MessageMediaWebPage):
        return "webpage"
    
    if isinstance(message.media, MessageMediaDocument):
        doc = message.media.document
        if doc:
            # Determine type based on document attributes
            for attr in doc.attributes:
                if isinstance(attr, DocumentAttributeSticker):
                    return "sticker"
                if isinstance(attr, DocumentAttributeAnimated):
                    return "animation"
                if isinstance(attr, DocumentAttributeVideo):
                    # Distinguish between video and GIF animation
                    if getattr(attr, 'round_message', False):
                        return "video"  # Video message
                    return "video"
                if isinstance(attr, DocumentAttributeAudio):
                    if getattr(attr, 'voice', False):
                        return "voice"
                    return "audio"
            return "document"
    
    return "text"


def get_file_size(message: Message) -> int:
    """Get the file size in bytes from a message, returns 0 if no file"""
    if not message.media:
        return 0
    
    if isinstance(message.media, MessageMediaDocument):
        doc = message.media.document
        if doc:
            return doc.size or 0
    
    if isinstance(message.media, MessageMediaPhoto):
        # Get the largest size for photos
        photo = message.media.photo
        if photo and photo.sizes:
            for size in reversed(photo.sizes):
                if hasattr(size, 'size'):
                    return size.size
    
    return 0


class MessageFilter:
    """Message filter"""
    
    def __init__(
        self,
        rule_name: str = "",
        regex_patterns: List[str] = None,
        keywords: List[str] = None,
        mode: str = "whitelist",
        ignored_user_ids: List[int] = None,
        ignored_keywords: List[str] = None,
        # New: media filtering
        media_types: List[str] = None,
        max_file_size: int = 0,
        min_file_size: int = 0,
    ):
        """
        Initialize filter

        Args:
            regex_patterns: List of regex patterns
            keywords: List of keywords
            mode: Filter mode (whitelist or blacklist)
            ignored_user_ids: List of ignored user IDs
            ignored_keywords: List of ignored keywords
            media_types: List of allowed media types (empty list = allow all)
            max_file_size: Maximum file size in bytes, 0 = no limit
            min_file_size: Minimum file size in bytes
        """
        self.rule_name = rule_name
        self._log_prefix = f"[{rule_name}] " if rule_name else ""
        self.regex_patterns = regex_patterns or []
        self.keywords = keywords or []
        self.mode = mode.lower()
        self.ignored_user_ids = ignored_user_ids or []
        self.ignored_keywords = ignored_keywords or []
        self.media_types = media_types or []
        self.max_file_size = max_file_size
        self.min_file_size = min_file_size

        # Compile regex patterns
        self.compiled_patterns = []
        for pattern in self.regex_patterns:
            try:
                self.compiled_patterns.append(re.compile(pattern))
            except re.error as e:
                logger.error(t("log.filter.regex_invalid", pattern=pattern, error=str(e)))

        logger.info(
            t("log.filter.initialized",
              mode=self.mode,
              regex_count=len(self.compiled_patterns),
              keyword_count=len(self.keywords),
              media_types=self.media_types or t("misc.all_media_types"),
              min_size=self.min_file_size,
              max_size=self.max_file_size or t("misc.unlimited"))
        )
    
    def check_media_type(self, message: Message) -> bool:
        """Check if media type is allowed. Returns True if allowed"""
        if not self.media_types:
            return True  # Empty list = allow all

        media_type = get_media_type(message)
        allowed = media_type in self.media_types
        if not allowed:
            logger.debug(f"{self._log_prefix}{t('log.filter.media_type_filtered', type=media_type, allowed=self.media_types)}")
        return allowed
    
    def check_file_size(self, message: Message) -> bool:
        """Check if file size is within limits. Returns True if allowed"""
        file_size = get_file_size(message)

        # No file = skip size check
        if file_size == 0:
            return True

        # Check minimum size
        if self.min_file_size > 0 and file_size < self.min_file_size:
            logger.debug(f"{self._log_prefix}{t('log.filter.file_too_small', size=file_size, min_size=self.min_file_size)}")
            return False

        # Check maximum size
        if self.max_file_size > 0 and file_size > self.max_file_size:
            logger.debug(f"{self._log_prefix}{t('log.filter.file_too_large', size=file_size, max_size=self.max_file_size)}")
            return False

        return True
    
    def matches_text(self, text: str) -> bool:
        """Check if text matches regex or keywords"""
        if not text:
            return False

        # Check regex
        for pattern in self.compiled_patterns:
            if pattern.search(text):
                logger.debug(f"{self._log_prefix}{t('log.filter.regex_matched', pattern=pattern.pattern)}")
                return True

        # Check keywords
        text_lower = text.lower()
        for keyword in self.keywords:
            if keyword.lower() in text_lower:
                logger.debug(f"{self._log_prefix}{t('log.filter.keyword_matched', keyword=keyword)}")
                return True

        return False
    
    def is_ignored(self, text: str, sender_id: int = None) -> bool:
        """Check if should be ignored (highest priority)"""
        # Check user blacklist
        if sender_id and sender_id in self.ignored_user_ids:
            logger.debug(f"{self._log_prefix}{t('log.filter.user_ignored', user_id=sender_id)}")
            return True

        # Check ignored keywords
        if text:
            text_lower = text.lower()
            for keyword in self.ignored_keywords:
                if keyword.lower() in text_lower:
                    logger.debug(f"{self._log_prefix}{t('log.filter.keyword_ignored', keyword=keyword)}")
                    return True

        return False
    
    def should_forward(self, message: Union[Message, str], sender_id: int = None) -> bool:
        """
        Determine if message should be forwarded

        Args:
            message: Message object or message text
            sender_id: Sender ID

        Returns:
            Whether to forward
        """
        # Compatibility: support passing string (old calling method)
        if isinstance(message, str):
            text = message
            msg_obj = None
        else:
            text = message.text or ""
            msg_obj = message

        # 1. Check ignore list first
        if self.is_ignored(text, sender_id):
            return False

        # 2. Check media type (only when Message object is passed)
        if msg_obj and not self.check_media_type(msg_obj):
            return False

        # 3. Check file size
        if msg_obj and not self.check_file_size(msg_obj):
            return False

        # 4. Text matching rules
        # If no rules configured, whitelist mode - don't forward, blacklist mode - forward
        if not self.compiled_patterns and not self.keywords:
            return self.mode == "blacklist"

        matches = self.matches_text(text)

        if self.mode == "whitelist":
            return matches  # Whitelist: forward only if matched
        else:
            return not matches  # Blacklist: forward only if not matched
