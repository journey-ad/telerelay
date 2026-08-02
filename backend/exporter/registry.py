"""Per-account export service and scheduler ownership."""

from __future__ import annotations

import threading
from pathlib import Path

from backend.account_paths import AccountPathRegistry, is_telegram_user_id
from backend.logger import get_logger
from backend.telegram_accounts import TelegramAccountError

from .scheduler import ExportScheduler
from .service import ExportService
from .source import TelegramExportSource
from .store import ExportStore

logger = get_logger()


class AccountExportRegistry:
    def __init__(self, configs, runtimes, paths: AccountPathRegistry, events=None):
        self.configs = configs
        self.runtimes = runtimes
        self.paths = paths
        self.events = events
        self._services: dict[str, ExportService] = {}
        self._schedulers: dict[str, ExportScheduler] = {}
        self._lock = threading.RLock()
        self._started = False

    def for_account(self, account_id: str) -> ExportService:
        with self._lock:
            service = self._services.get(account_id)
            if service is not None:
                return service
            paths = self.paths.for_account(account_id)
            runtime = self.runtimes.get_runtime(account_id)
            service = ExportService(
                self.configs.for_account(account_id),
                runtime,
                store=ExportStore(paths.exports_db),
                source=TelegramExportSource(runtime),
                events=self.events,
                session_type=self.runtimes.account_kind(account_id),
            )
            scheduler = ExportScheduler(service)
            self._services[account_id] = service
            self._schedulers[account_id] = scheduler
            if self._started:
                scheduler.start()
            return service

    def scheduler_for_account(self, account_id: str) -> ExportScheduler:
        self.for_account(account_id)
        return self._schedulers[account_id]

    def start(self) -> None:
        with self._lock:
            self._started = True
        for account in self.runtimes.account_store.list_public():
            if is_telegram_user_id(account["id"]):
                try:
                    self.for_account(account["id"])
                except TelegramAccountError as exc:
                    logger.warning(
                        "Skipped export scope for account %s: %s",
                        account["id"],
                        exc,
                    )
        with self._lock:
            schedulers = list(self._schedulers.values())
        for scheduler in schedulers:
            scheduler.start()

    def recreate(self, account_id: str) -> ExportService:
        self.discard(account_id)
        return self.for_account(account_id)

    def discard(self, account_id: str) -> None:
        with self._lock:
            scheduler = self._schedulers.pop(account_id, None)
            service = self._services.pop(account_id, None)
        if scheduler:
            scheduler.shutdown()
        if service:
            service.shutdown()

    def resolve_preview_token(self, token: str) -> Path | None:
        with self._lock:
            services = list(self._services.values())
        for service in services:
            path = service.resolve_preview_token(token)
            if path is not None:
                return path
        return None

    def read_archive_file(self, zip_path: Path, inner: str) -> bytes | None:
        with self._lock:
            services = list(self._services.values())
        for service in services:
            content = service.read_archive_file(zip_path, inner)
            if content is not None:
                return content
        return None

    def shutdown(self) -> None:
        with self._lock:
            account_ids = list(self._services)
            self._started = False
        for account_id in account_ids:
            self.discard(account_id)
