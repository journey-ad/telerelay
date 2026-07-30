"""Application dependency container constructed by FastAPI lifespan."""

from dataclasses import dataclass
from threading import Thread

from backend.auth_manager import AuthManager
from backend.bot_manager import BotManager
from backend.config import Config
from backend.events import EventBus, EventLogHandler
from backend.exporter.scheduler import ExportScheduler
from backend.exporter.service import ExportService
from backend.services import RuleService


@dataclass
class ApplicationContext:
    config: Config
    auth: AuthManager | None
    bot: BotManager
    exports: ExportService
    scheduler: ExportScheduler
    rules: RuleService
    events: EventBus
    log_handler: EventLogHandler
    admin_thread: Thread | None = None

