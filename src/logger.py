"""
日志配置模块
提供统一的日志配置和管理
"""
import logging
import os
from pathlib import Path
from datetime import datetime
from logging.handlers import RotatingFileHandler
from src.constants import LOG_FILE_MAX_BYTES, LOG_FILE_BACKUP_COUNT


def setup_logger(name: str = "telegram_forwarder", level: str = "INFO") -> logging.Logger:
    """
    设置并返回配置好的日志记录器

    参数:
        name: 日志记录器名称
        level: 日志级别 (DEBUG, INFO, WARNING, ERROR)

    返回:
        配置好的 Logger 对象
    """
    # 创建日志目录
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    # 创建日志记录器
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # 避免重复添加处理器
    if logger.handlers:
        return logger

    # 日志格式
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 文件处理器 - 使用轮转机制
    log_file = log_dir / f"{name}.log"
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=LOG_FILE_MAX_BYTES,
        backupCount=LOG_FILE_BACKUP_COUNT,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


def get_logger(name: str = "telegram_forwarder") -> logging.Logger:
    """
    获取已配置的日志记录器

    参数:
        name: 日志记录器名称

    返回:
        Logger 对象
    """
    return logging.getLogger(name)


class UIUpdateHandler(logging.Handler):
    """
    自定义日志处理器，在日志记录时触发 UI 更新
    """

    def __init__(self, bot_manager):
        """
        初始化处理器

        参数:
            bot_manager: BotManager 实例
        """
        super().__init__()
        self.bot_manager = bot_manager

    def emit(self, record):
        """
        处理日志记录，触发 UI 更新

        参数:
            record: 日志记录对象
        """
        try:
            # 触发 UI 更新（已有防抖机制，不会过于频繁）
            if self.bot_manager:
                self.bot_manager.trigger_ui_update()
        except Exception:
            # 避免日志处理器本身出错影响程序运行
            pass


def add_ui_update_handler(bot_manager, logger_name: str = "telegram_forwarder") -> None:
    """
    为 logger 添加 UI 更新处理器

    参数:
        bot_manager: BotManager 实例
        logger_name: 日志记录器名称
    """
    logger = get_logger(logger_name)

    # 检查是否已经添加过 UIUpdateHandler
    for handler in logger.handlers:
        if isinstance(handler, UIUpdateHandler):
            return

    # 添加 UI 更新处理器
    ui_handler = UIUpdateHandler(bot_manager)
    ui_handler.setLevel(logging.DEBUG)  # 所有级别的日志都触发更新
    logger.addHandler(ui_handler)
