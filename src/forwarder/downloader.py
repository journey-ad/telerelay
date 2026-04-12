"""
Media download module
"""
import os
import shutil
import tempfile
import uuid
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

    @staticmethod
    def purge_temp_dir() -> None:
        """Remove the temp directory to clear all residual files"""
        if os.path.exists(TEMP_DIR):
            try:
                shutil.rmtree(TEMP_DIR)
                logger.info(f"Purged temp directory: {TEMP_DIR}")
            except OSError as e:
                logger.warning(f"Failed to purge temp directory: {e}")

    async def download(self, messages: List[Message]) -> tuple[List[str], str]:
        """Download media files into a unique subdirectory.

        Returns:
            (file_paths, session_dir) — session_dir should be passed to cleanup()
        """
        session_dir = os.path.join(TEMP_DIR, uuid.uuid4().hex[:12])
        os.makedirs(session_dir, exist_ok=True)
        file_paths = []

        if len(messages) == 1:
            path = await self._download_single(messages[0], session_dir)
            if path:
                file_paths.append(path)
        else:
            file_paths = await self._download_group(messages, session_dir)

        return file_paths, session_dir

    async def _download_single(self, message: Message, dest: str) -> Optional[str]:
        """Download media from a single message"""
        if not message.media:
            return None

        logger.info(t("log.forward.downloader.downloading"))
        path = await self.client.download_media(message, file=dest)

        if path:
            file_size_mb = os.path.getsize(path) / 1048576
            logger.info(t("log.forward.downloader.complete", filename=os.path.basename(path), size=f"{file_size_mb:.1f}"))

        return path

    async def _download_group(self, messages: List[Message], dest: str) -> List[str]:
        """Download all media from a media group"""
        logger.info(t("log.forward.downloader.group_downloading", count=len(messages)))
        file_paths = []

        for i, msg in enumerate(messages):
            if msg.media:
                path = await self.client.download_media(msg, file=dest)
                if path:
                    file_paths.append(path)
                    logger.debug(t("log.forward.downloader.group_progress", current=i+1, total=len(messages), filename=os.path.basename(path)))

        if file_paths:
            logger.info(t("log.forward.downloader.group_complete", count=len(file_paths)))

        return file_paths

    @staticmethod
    def cleanup(session_dir: str) -> None:
        """Remove the entire session subdirectory (including any partial downloads)"""
        if session_dir and os.path.isdir(session_dir):
            try:
                shutil.rmtree(session_dir)
                logger.debug(t("log.forward.downloader.cleanup", path=session_dir))
            except OSError as e:
                logger.warning(t("log.forward.downloader.cleanup_failed", path=session_dir, error=e))
