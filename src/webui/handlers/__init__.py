"""
WebUI handlers module
"""
from .bot_control import BotControlHandler
from .config import ConfigHandler
from .log import LogHandler
from .auth import AuthHandler
from .history import HistoryHandler
from .stats import StatsHandler
from .backup import BackupHandler
from .export import ExportHandler

__all__ = ['BotControlHandler', 'ConfigHandler', 'LogHandler', 'AuthHandler',
           'HistoryHandler', 'StatsHandler', 'BackupHandler', 'ExportHandler']
