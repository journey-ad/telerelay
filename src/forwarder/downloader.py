"""
Media download module
"""
import os
import tempfile
from typing import List, Optional
from telethon import TelegramClient
from telethon.tl.types import Message
from src.logger import get_logger
from src.i18n import t

logger = get_logger()

# Temporary file directory
TEMP_DIR = os.path.join(tempfile.gettempdir(), "telerelay-cache")


class MediaDownloader:
    """Handle media file download and cleanup"""

    def __init__(self, client: TelegramClient, rule_name: str):
        self.client = client
        self.rule_name = rule_name

    async def download(self, messages: List[Message]) -> List[str]:
        """Download media files from messages, return list of file paths"""
        os.makedirs(TEMP_DIR, exist_ok=True)
        file_paths = []

        if len(messages) == 1:
            path = await self._download_single(messages[0])
            if path:
                file_paths.append(path)
        else:
            file_paths = await self._download_group(messages)

        return file_paths

    async def _download_single(self, message: Message) -> Optional[str]:
        """Download media from a single message"""
        if not message.media:
            return None

        logger.info(t("log.forward.downloader.downloading"))
        path = await self.client.download_media(message, file=TEMP_DIR)

        if path:
            file_size_mb = os.path.getsize(path) / 1048576
            logger.info(t("log.forward.downloader.complete", filename=os.path.basename(path), size=f"{file_size_mb:.1f}"))

        return path

    async def _download_group(self, messages: List[Message]) -> List[str]:
        """Download all media from a media group"""
        logger.info(t("log.forward.downloader.group_downloading", count=len(messages)))
        file_paths = []

        for i, msg in enumerate(messages):
            if msg.media:
                path = await self.client.download_media(msg, file=TEMP_DIR)
                if path:
                    file_paths.append(path)
                    logger.debug(t("log.forward.downloader.group_progress", current=i+1, total=len(messages), filename=os.path.basename(path)))

        if file_paths:
            logger.info(t("log.forward.downloader.group_complete", count=len(file_paths)))

        return file_paths

    @staticmethod
    def cleanup(file_paths: List[str]) -> None:
        """Cleanup temporary files"""
        for path in file_paths:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                    logger.debug(t("log.forward.downloader.cleanup", path=path))
                except OSError as e:
                    logger.warning(t("log.forward.downloader.cleanup_failed", path=path, error=e))
