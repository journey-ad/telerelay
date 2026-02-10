"""
Logger configuration module
Provides unified logging configuration and management
"""
import logging
import os
from pathlib import Path
from datetime import datetime
from logging.handlers import RotatingFileHandler
from src.constants import LOG_FILE_MAX_BYTES, LOG_FILE_BACKUP_COUNT


def setup_logger(name: str = "telerelay", level: str = "INFO") -> logging.Logger:
    """
    Set up and return a configured logger

    Args:
        name: Logger name
        level: Log level (DEBUG, INFO, WARNING, ERROR)

    Returns:
        Configured Logger object
    """
    # Create log directory
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Avoid adding duplicate handlers
    if logger.handlers:
        return logger

    # Log format
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler - using rotation mechanism
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


def get_logger(name: str = "telerelay") -> logging.Logger:
    """
    Get configured logger

    Args:
        name: Logger name

    Returns:
        Logger object
    """
    return logging.getLogger(name)


class UIUpdateHandler(logging.Handler):
    """
    Custom log handler that triggers UI updates when logging
    """

    def __init__(self, bot_manager):
        """
        Initialize handler

        Args:
            bot_manager: BotManager instance
        """
        super().__init__()
        self.bot_manager = bot_manager

    def emit(self, record):
        """
        Handle log record and trigger UI update

        Args:
            record: Log record object
        """
        try:
            # Trigger UI update (has debounce mechanism, won't be too frequent)
            if self.bot_manager:
                self.bot_manager.trigger_ui_update()
        except Exception:
            # Avoid log handler errors affecting program execution
            pass


def add_ui_update_handler(bot_manager, logger_name: str = "telerelay") -> None:
    """
    Add UI update handler to logger

    Args:
        bot_manager: BotManager instance
        logger_name: Logger name
    """
    logger = get_logger(logger_name)

    # Check if UIUpdateHandler has already been added
    for handler in logger.handlers:
        if isinstance(handler, UIUpdateHandler):
            return

    # Add UI update handler
    ui_handler = UIUpdateHandler(bot_manager)
    ui_handler.setLevel(logging.DEBUG)  # All log levels trigger updates
    logger.addHandler(ui_handler)
