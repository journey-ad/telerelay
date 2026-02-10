"""
媒体下载模块
"""
import os
import tempfile
from typing import List, Optional
from telethon import TelegramClient
from telethon.tl.types import Message
from src.logger import get_logger

logger = get_logger()

# 临时文件目录
TEMP_DIR = os.path.join(tempfile.gettempdir(), "tg-box-cache")


class MediaDownloader:
    """处理媒体文件的下载和清理"""

    def __init__(self, client: TelegramClient, rule_name: str):
        self.client = client
        self.rule_name = rule_name

    async def download(self, messages: List[Message]) -> List[str]:
        """下载消息的媒体文件，返回文件路径列表"""
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
        """下载单条消息的媒体"""
        if not message.media:
            return None

        logger.info(f"[{self.rule_name}] ⬇️ 开始下载媒体文件...")
        path = await self.client.download_media(message, file=TEMP_DIR)

        if path:
            file_size_mb = os.path.getsize(path) / 1048576
            logger.info(f"[{self.rule_name}] ⬇️ 下载完成: {os.path.basename(path)} ({file_size_mb:.1f} MB)")

        return path

    async def _download_group(self, messages: List[Message]) -> List[str]:
        """下载媒体组的所有媒体"""
        logger.info(f"[{self.rule_name}] ⬇️ 开始下载媒体组 ({len(messages)} 项)...")
        file_paths = []

        for i, msg in enumerate(messages):
            if msg.media:
                path = await self.client.download_media(msg, file=TEMP_DIR)
                if path:
                    file_paths.append(path)
                    logger.debug(f"[{self.rule_name}] ⬇️ 下载 {i+1}/{len(messages)}: {os.path.basename(path)}")

        if file_paths:
            logger.info(f"[{self.rule_name}] ⬇️ 媒体组下载完成: {len(file_paths)} 个文件")

        return file_paths

    @staticmethod
    def cleanup(file_paths: List[str]) -> None:
        """清理临时文件"""
        for path in file_paths:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                    logger.debug(f"已清理临时文件: {path}")
                except OSError as e:
                    logger.warning(f"清理临时文件失败: {path}, {e}")
