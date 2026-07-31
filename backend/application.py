"""Application dependency container constructed by FastAPI lifespan."""

from dataclasses import dataclass
from threading import Thread

from backend.config import Config
from backend.events import EventBus, EventLogHandler
from backend.exporter.scheduler import ExportScheduler
from backend.exporter.service import ExportService
from backend.services import RuleService
from backend.telegram_accounts import TelegramAccountService
from backend.telegram_chats import TelegramChatService
from backend.telegram_preview import TelegramPreviewService


@dataclass
class ApplicationContext:
    config: Config
    bot: object
    exports: ExportService
    scheduler: ExportScheduler
    rules: RuleService
    events: EventBus
    log_handler: EventLogHandler
    accounts: TelegramAccountService | None = None
    telegram_chats: TelegramChatService | None = None
    telegram_preview: TelegramPreviewService | None = None
    admin_thread: Thread | None = None
