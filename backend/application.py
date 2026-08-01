"""Application dependency container constructed by FastAPI lifespan."""

from dataclasses import dataclass
from threading import Thread

from backend.account_paths import is_telegram_user_id
from backend.config import Config
from backend.events import EventBus, EventLogHandler
from backend.telegram_accounts import TelegramAccountService
from backend.telegram_chats import TelegramChatService
from backend.telegram_preview import TelegramPreviewService


@dataclass
class ApplicationContext:
    config: Config
    bot: object
    exports: object
    scheduler: object
    rules: object
    events: EventBus
    log_handler: EventLogHandler
    accounts: TelegramAccountService | None = None
    telegram_chats: TelegramChatService | None = None
    telegram_preview: TelegramPreviewService | None = None
    admin_thread: Thread | None = None
    config_registry: object | None = None
    stats_registry: object | None = None
    export_registry: object | None = None
    rule_registry: object | None = None

    def active_account_id(self) -> str | None:
        if not self.accounts:
            return None
        account_id = self.accounts.store.active_account_id
        account_scoping_enabled = any(
            value is not None
            for value in (
                self.config_registry,
                self.stats_registry,
                self.export_registry,
                self.rule_registry,
            )
        )
        if account_scoping_enabled and not is_telegram_user_id(account_id):
            raise ValueError("Telegram account must be authenticated first")
        return account_id

    def active_config(self) -> Config:
        account_id = self.active_account_id()
        if account_id and self.config_registry:
            return self.config_registry.for_account(account_id)
        return self.config

    def active_stats(self):
        account_id = self.active_account_id()
        if account_id and self.stats_registry:
            return self.stats_registry.for_account(account_id)
        from backend.stats_db import get_stats_db

        return get_stats_db()

    def active_exports(self):
        account_id = self.active_account_id()
        if account_id and self.export_registry:
            return self.export_registry.for_account(account_id)
        return self.exports

    def active_scheduler(self):
        account_id = self.active_account_id()
        if account_id and self.export_registry:
            return self.export_registry.scheduler_for_account(account_id)
        return self.scheduler

    def active_rules(self):
        account_id = self.active_account_id()
        if account_id and self.rule_registry:
            return self.rule_registry.for_account(account_id)
        return self.rules
