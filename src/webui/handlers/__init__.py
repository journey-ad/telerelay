"""
WebUI handlers module
"""
from .bot_control import BotControlHandler
from .config import ConfigHandler
from .log import LogHandler
from .auth import AuthHandler

__all__ = ['BotControlHandler', 'ConfigHandler', 'LogHandler', 'AuthHandler']
