"""
Media download module
"""
import os
import shutil
import tempfile
from typing import List, Optional
from telethon import TelegramClient
from telethon.tl.types import Message
from backend.logger import get_logger
from backend.i18n import t

logger = get_logger()

# Temporary file directory
TEMP_DIR = os.path.join(tempfile.gettempdir(), "telerelay-cache")
# Queue download directories are named after the owning job so a retry can reuse
# the bytes already on disk and a restart can recognise its own leftovers.
JOB_DIR_PREFIX = "job-"
# Leftovers older than this are assumed abandoned (crash before cleanup).
JOB_DIR_TTL_SECONDS = 6 * 3600


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
                logger.debug(t("log.forward.downloader.cleanup", path=TEMP_DIR))
            except OSError as e:
                logger.warning(t("log.forward.downloader.purge_failed", error=str(e)))

    @staticmethod
    def purge_stale_job_dirs(now: Optional[float] = None) -> int:
        """Drop job download directories left behind by a crash or hard stop."""
        import time

        if not os.path.isdir(TEMP_DIR):
            return 0
        reference = time.time() if now is None else now
        removed = 0
        for name in os.listdir(TEMP_DIR):
            if not name.startswith(JOB_DIR_PREFIX):
                continue
            path = os.path.join(TEMP_DIR, name)
            try:
                if reference - os.path.getmtime(path) < JOB_DIR_TTL_SECONDS:
                    continue
                if os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
                removed += 1
            except OSError as e:
                logger.warning(t("log.forward.downloader.cleanup_failed", path=path, error=e))
        return removed

    @staticmethod
    def download_dir(item_id: int) -> str:
        """Return the stable download directory for a queue job."""
        return os.path.join(TEMP_DIR, f"{JOB_DIR_PREFIX}{int(item_id)}")

    async def download(self, messages: List[Message], session_dir: Optional[str] = None) -> tuple[List[str], str]:
        """Download media files into a job directory.

        ``session_dir`` makes the directory stable across retries: when every
        expected file is already there the download is skipped entirely.  Bytes
        are staged in a temporary sibling directory and moved into place with a
        single rename, so an interrupted attempt never looks complete.

        Returns:
            (file_paths, session_dir) — session_dir should be passed to cleanup()
        """
        expected = sum(1 for message in messages if message.media)
        reusable = self._reusable_files(session_dir, expected)
        if reusable:
            logger.debug(t("log.forward.downloader.reused", count=len(reusable)))
            return reusable, session_dir

        staging_dir = f"{session_dir}.partial"
        shutil.rmtree(staging_dir, ignore_errors=True)
        os.makedirs(staging_dir, exist_ok=True)
        try:
            if len(messages) == 1:
                path = await self._download_single(messages[0], staging_dir)
                file_paths = [path] if path else []
            else:
                file_paths = await self._download_group(messages, staging_dir)
            # Move the staged bytes into place only once they are all present.
            shutil.rmtree(session_dir, ignore_errors=True)
            os.replace(staging_dir, session_dir)
        except BaseException:
            shutil.rmtree(staging_dir, ignore_errors=True)
            raise
        return [os.path.join(session_dir, os.path.basename(path)) for path in file_paths], session_dir

    @staticmethod
    def _reusable_files(session_dir: str, expected: int) -> List[str]:
        if expected <= 0 or not os.path.isdir(session_dir):
            return []
        files = sorted(
            os.path.join(session_dir, name)
            for name in os.listdir(session_dir)
            if os.path.isfile(os.path.join(session_dir, name))
        )
        if len(files) != expected:
            return []
        if any(os.path.getsize(path) <= 0 for path in files):
            return []
        return files

    async def _download_single(self, message: Message, dest: str) -> Optional[str]:
        """Download media from a single message"""
        if not message.media:
            return None

        logger.debug(t("log.forward.downloader.downloading"))
        path = await self.client.download_media(message, file=dest)

        if path:
            file_size_mb = os.path.getsize(path) / 1048576
            logger.debug(t("log.forward.downloader.complete", filename=os.path.basename(path), size=f"{file_size_mb:.1f}"))

        return path

    async def _download_group(self, messages: List[Message], dest: str) -> List[str]:
        """Download all media from a media group"""
        logger.debug(t("log.forward.downloader.group_downloading", count=len(messages)))
        file_paths = []

        for i, msg in enumerate(messages):
            if msg.media:
                path = await self.client.download_media(msg, file=dest)
                if path:
                    file_paths.append(path)
                    logger.debug(t("log.forward.downloader.group_progress", current=i+1, total=len(messages), filename=os.path.basename(path)))

        if file_paths:
            logger.debug(t("log.forward.downloader.group_complete", count=len(file_paths)))

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
