"""
Logger configuration module
Provides unified logging configuration and management
"""
import logging
import os
import re
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler
from src.constants import LOG_FILE_BACKUP_COUNT


class DailyFileHandler(TimedRotatingFileHandler):
    """Daily rotating file handler with name_YYYYMMDD.log format

    Current log:  logs/telerelay.log
    Rotated logs: logs/telerelay_20260226.log
    """

    def __init__(self, log_dir, base_name, backupCount=30, encoding='utf-8'):
        self._base_name = base_name
        self._log_dir = str(log_dir)
        log_file = os.path.join(self._log_dir, f"{base_name}.log")
        super().__init__(
            log_file,
            when='midnight',
            interval=1,
            backupCount=backupCount,
            encoding=encoding,
        )
        self.suffix = '%Y%m%d'
        self.extMatch = re.compile(r'^\d{4}\d{2}\d{2}$')

    def rotation_filename(self, default_name):
        # default_name: "logs/telerelay.log.20260226"
        # target:       "logs/telerelay_20260226.log"
        date_str = default_name.rsplit('.', 1)[-1]
        return os.path.join(self._log_dir, f"{self._base_name}_{date_str}.log")

    def getFilesToDelete(self):
        prefix = f"{self._base_name}_"
        suffix = ".log"
        result = []
        for f in os.listdir(self._log_dir):
            if f.startswith(prefix) and f.endswith(suffix):
                date_part = f[len(prefix):-len(suffix)]
                if self.extMatch.match(date_part):
                    result.append(os.path.join(self._log_dir, f))
        result.sort()
        if len(result) <= self.backupCount:
            return []
        return result[:len(result) - self.backupCount]


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

    # File handler - daily rotation
    file_handler = DailyFileHandler(
        log_dir, name, backupCount=LOG_FILE_BACKUP_COUNT
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
