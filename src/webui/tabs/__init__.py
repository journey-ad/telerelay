"""Gradio tab modules."""

from .auth import AuthTab
from .backup import BackupTab
from .config import ConfigTab
from .export import ExportTab
from .history import HistoryTab
from .log import LogTab
from .stats import StatsTab

__all__ = [
    "AuthTab",
    "BackupTab",
    "ConfigTab",
    "ExportTab",
    "HistoryTab",
    "LogTab",
    "StatsTab",
]
