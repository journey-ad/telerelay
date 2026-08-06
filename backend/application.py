"""Application dependency container constructed by FastAPI lifespan."""

from contextvars import ContextVar
from dataclasses import dataclass, field
from threading import Thread

from backend.config import AccountConfigRegistry, Config
from backend.events import EventBus, EventLogHandler
from backend.services.rules import RuleService
from backend.stats_db import AccountStatsRegistry
from backend.telegram_accounts import TelegramAccountService
from backend.telegram_chats import TelegramChatService
from backend.telegram_preview import TelegramPreviewService


@dataclass(frozen=True)
class AccountScope:
    """All account-owned services, resolved once per account request."""

    account_id: str
    config: Config
    stats: object
    rules: RuleService
    exports: object
    scheduler: object
    runtime: object


class AccountScopeRegistry:
    """Own every service that belongs to an account."""

    def __init__(
        self,
        config_registry: AccountConfigRegistry,
        stats_registry: AccountStatsRegistry,
        runtimes,
        paths,
        events=None,
    ):
        import threading

        from backend.exporter.registry import AccountExportRegistry

        self.configs = config_registry
        self.stats = stats_registry
        self.runtimes = runtimes
        self._exports = AccountExportRegistry(config_registry, runtimes, paths, events=events)
        self._rules: dict[str, RuleService] = {}
        self._lock = threading.RLock()

    def for_account(self, account_id: str) -> AccountScope:
        from backend.account_paths import is_telegram_user_id

        if not is_telegram_user_id(account_id):
            raise ValueError("Telegram account must be authenticated first")
        kind = self.runtimes.account_kind(account_id)
        config = self.configs.for_account(account_id)
        stats = self.stats.for_account(account_id)
        runtime = self.runtimes.get_runtime(account_id)
        exports = self._exports.for_account(account_id)
        with self._lock:
            rules = self._rules.get(account_id)
            if rules is None:
                rules = RuleService(config, runtime, stats, session_type=kind)
                self._rules[account_id] = rules
        return AccountScope(
            account_id=account_id,
            config=config,
            stats=stats,
            rules=rules,
            exports=exports,
            scheduler=self._exports.scheduler_for_account(account_id),
            runtime=runtime,
        )

    def replace_config(self, account_id: str, config_data: dict) -> Config:
        config = self.configs.replace(account_id, config_data)
        self._exports.recreate(account_id)
        return config

    def discard(self, account_id: str) -> None:
        self._exports.discard(account_id)
        with self._lock:
            self._rules.pop(account_id, None)
        self.configs.discard(account_id)
        self.stats.discard(account_id)

    def resolve_preview_token(self, token: str):
        return self._exports.resolve_preview_token(token)

    def read_archive_file(self, zip_path, inner: str):
        return self._exports.read_archive_file(zip_path, inner)

    def start(self) -> None:
        self._exports.start()

    def shutdown(self) -> None:
        self._exports.shutdown()
        with self._lock:
            self._rules.clear()


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
    telegram_resource: object | None = None
    admin_thread: Thread | None = None
    account_registry: AccountScopeRegistry | None = None
    request_account_id: ContextVar[str | None] = field(
        default_factory=lambda: ContextVar("telerelay_request_account_id", default=None),
        repr=False,
    )

    def selected_account_id(self) -> str | None:
        """Return the account captured when the current request started."""
        if not self.accounts:
            return None
        account_id = self.request_account_id.get() or self.accounts.store.active_account_id
        self.accounts.store.get_public(account_id)
        return account_id

    def scope_for(self, account_id: str | None = None) -> AccountScope | None:
        """Resolve one account's service scope; defaults to the request-bound account."""
        if not self.accounts or not self.account_registry:
            return None
        if account_id is None:
            account_id = self.selected_account_id()
        return self.account_registry.for_account(account_id)
