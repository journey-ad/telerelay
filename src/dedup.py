"""
Message deduplication module
Uses content hash with sliding window to avoid forwarding duplicate messages
"""
import hashlib
import time
from src.logger import get_logger

logger = get_logger()


class DeduplicateCache:
    """Content-hash based sliding window deduplication cache"""

    def __init__(self, window: int = 3600):
        """
        Initialize deduplication cache

        Args:
            window: Deduplication window in seconds (default 1 hour)
        """
        self.window = window
        self._cache: dict[str, float] = {}

    def is_duplicate(self, text: str) -> bool:
        """
        Check if text content is a duplicate within the sliding window.

        Args:
            text: Message text to check

        Returns:
            True if duplicate (should skip), False if new
        """
        if not text or not text.strip():
            return False

        h = hashlib.md5(text.encode()).hexdigest()[:16]
        now = time.time()

        # Cleanup expired entries
        self._cache = {k: v for k, v in self._cache.items() if now - v < self.window}

        if h in self._cache:
            logger.debug(f"Duplicate message detected (hash={h}), skipping")
            return True

        self._cache[h] = now
        return False
