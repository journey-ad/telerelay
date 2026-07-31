"""Parallel Telegram account runtime orchestration."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from backend.auth_manager import AuthManager
from backend.bot_manager import BotManager
from backend.stats_db import get_stats_db
from backend.telegram_accounts import TelegramAccountError, TelegramAccountStore


class TelegramRuntimeRegistry:
    """Own one isolated Telegram runtime per account on a shared event loop."""

    def __init__(
        self,
        config: Any,
        account_store: TelegramAccountStore,
        *,
        auth_timeout: float = 300,
        bot_factory: Callable[..., Any] = BotManager,
        auth_factory: Callable[..., AuthManager] = AuthManager,
        events: Any = None,
    ):
        self.config = config
        self.account_store = account_store
        self.auth_timeout = auth_timeout
        self.bot_factory = bot_factory
        self.auth_factory = auth_factory
        self.events = events
        self.loop: asyncio.AbstractEventLoop | None = None
        self.on_user_authenticated: Callable[[str, dict[str, Any]], None] | None = None
        self._runtimes: dict[str, Any] = {}
        self._auth_managers: dict[str, AuthManager] = {}
        self._blocked_account_ids: set[str] = set()
        self._state_lock = threading.RLock()
        self._lifecycle_lock = asyncio.Lock()

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        with self._state_lock:
            runtimes = list(self._runtimes.values())
        for runtime in runtimes:
            runtime.bind_loop(loop)

    def ensure_runtime(self, account_id: str) -> Any:
        self.account_store.get_public(account_id)
        with self._state_lock:
            if account_id in self._blocked_account_ids:
                raise TelegramAccountError(
                    "account_unavailable",
                    "Telegram account is being removed",
                )
            runtime = self._runtimes.get(account_id)
            if runtime is not None:
                return runtime

            auth = self.auth_factory(input_timeout=self.auth_timeout)
            runtime = self.bot_factory(
                self.config,
                auth,
                session_name=self.account_store.session_name(account_id),
                queue_db_path=self.queue_db_path(account_id),
                account_id=account_id,
            )
            runtime.events = self.events
            runtime.on_user_authenticated = (
                lambda identity, target=account_id: self._authenticated(target, identity)
            )
            if self.loop is not None:
                runtime.bind_loop(self.loop)
            self._auth_managers[account_id] = auth
            self._runtimes[account_id] = runtime
            return runtime

    def get_runtime(self, account_id: str | None = None) -> Any:
        target = account_id or self.account_store.active_account_id
        return self.ensure_runtime(target)

    def get_auth(self, account_id: str | None = None) -> AuthManager:
        target = account_id or self.account_store.active_account_id
        self.ensure_runtime(target)
        with self._state_lock:
            return self._auth_managers[target]

    def queue_db_path(self, account_id: str) -> Path:
        configured = Path(self.config.forward_queue_db_path)
        if account_id == self.account_store.DEFAULT_ACCOUNT_ID:
            return configured
        return configured.parent / "forward_queues" / f"account_{account_id}.db"

    def is_account_running(self, account_id: str) -> bool:
        with self._state_lock:
            if account_id in self._blocked_account_ids:
                return False
            runtime = self._runtimes.get(account_id)
        return bool(runtime and runtime.is_running)

    def is_account_connected(self, account_id: str) -> bool:
        with self._state_lock:
            if account_id in self._blocked_account_ids:
                return False
            runtime = self._runtimes.get(account_id)
        return bool(runtime and runtime.is_connected)

    @property
    def current_runtime(self) -> Any:
        return self.get_runtime()

    @property
    def is_running(self) -> bool:
        with self._state_lock:
            return any(runtime.is_running for runtime in self._runtimes.values())

    @property
    def is_connected(self) -> bool:
        return self.is_account_connected(self.account_store.active_account_id)

    def block_account(self, account_id: str) -> None:
        self.account_store.get_public(account_id)
        with self._state_lock:
            self._blocked_account_ids.add(account_id)

    def unblock_account(self, account_id: str) -> None:
        with self._state_lock:
            self._blocked_account_ids.discard(account_id)

    def is_account_blocked(self, account_id: str) -> bool:
        with self._state_lock:
            return account_id in self._blocked_account_ids

    async def start(self) -> bool:
        """Start every authenticated account that is not already running."""
        async with self._lifecycle_lock:
            targets = [
                account["id"]
                for account in self.account_store.list_public()
                if account["authenticated"]
                and not self.is_account_blocked(account["id"])
                and not self.is_account_running(account["id"])
            ]
            if not targets:
                return False
            results = await asyncio.gather(
                *(self._start_one(account_id) for account_id in targets),
                return_exceptions=True,
            )
            return any(result is True for result in results)

    async def start_account(self, account_id: str, *, require_session: bool = False) -> bool:
        async with self._lifecycle_lock:
            self.account_store.get_public(account_id)
            if require_session and not self.account_store.has_session(account_id):
                return False
            return await self.ensure_runtime(account_id).start()

    async def stop(self) -> bool:
        async with self._lifecycle_lock:
            with self._state_lock:
                running = [runtime for runtime in self._runtimes.values() if runtime.is_running]
            if not running:
                return False
            results = await asyncio.gather(
                *(runtime.stop() for runtime in running),
                return_exceptions=True,
            )
            with self._state_lock:
                auth_managers = list(self._auth_managers.values())
            for auth in auth_managers:
                auth.reset()
            return any(result is True for result in results)

    async def stop_account(self, account_id: str) -> bool:
        async with self._lifecycle_lock:
            with self._state_lock:
                runtime = self._runtimes.get(account_id)
            stopped = bool(runtime and runtime.is_running and await runtime.stop())
            with self._state_lock:
                auth = self._auth_managers.get(account_id)
            if auth:
                auth.reset()
            return stopped

    async def restart(self) -> bool:
        """Bring every authenticated account through a fresh runtime start."""
        async with self._lifecycle_lock:
            targets = [
                account["id"]
                for account in self.account_store.list_public()
                if account["authenticated"] and not self.is_account_blocked(account["id"])
            ]
            if not targets:
                return False
            results = await asyncio.gather(
                *(self._start_one(account_id, restart=True) for account_id in targets),
                return_exceptions=True,
            )
            return any(result is True for result in results)

    async def reload_rules(self) -> bool:
        """Reload rules in every running account without reconnecting clients."""
        async with self._lifecycle_lock:
            with self._state_lock:
                runtimes = [
                    runtime for runtime in self._runtimes.values() if runtime.is_running
                ]
            if not runtimes:
                return False
            results = await asyncio.gather(
                *(runtime.reload_rules() for runtime in runtimes),
                return_exceptions=True,
            )
            return any(result is True for result in results)

    async def remove_runtime(self, account_id: str, *, clear_queue: bool = False) -> None:
        queue_path = self.queue_db_path(account_id)
        await self.stop_account(account_id)
        with self._state_lock:
            self._runtimes.pop(account_id, None)
            self._auth_managers.pop(account_id, None)
        if clear_queue:
            await asyncio.to_thread(self._clear_queue_files, queue_path)

    def submit_telegram(self, callback, *args):
        return self.current_runtime.submit_telegram(callback, *args)

    def get_status(self) -> dict[str, Any]:
        with self._state_lock:
            runtime_statuses = {}
            for account_id, runtime in self._runtimes.items():
                queue_status = {"counts": {}, "paused_until": 0, "pause_reason": None}
                queue_store = getattr(runtime, "forward_queue_store", None)
                if queue_store:
                    paused_until, pause_reason = queue_store.get_pause()
                    queue_status = {
                        "counts": queue_store.counts(),
                        "paused_until": paused_until,
                        "pause_reason": pause_reason,
                    }
                runtime_statuses[account_id] = {
                    "is_running": runtime.is_running,
                    "is_connected": runtime.is_connected,
                    "queue": queue_status,
                }
        counts: dict[str, int] = {}
        paused_until = 0.0
        pause_reasons: list[str] = []
        for status in runtime_statuses.values():
            queue = status.get("queue", {})
            for key, value in queue.get("counts", {}).items():
                counts[key] = counts.get(key, 0) + int(value)
            paused_until = max(paused_until, float(queue.get("paused_until") or 0))
            reason = queue.get("pause_reason")
            if reason and reason not in pause_reasons:
                pause_reasons.append(str(reason))

        database = get_stats_db()
        all_stats = database.get_all_stats()
        forwarded = sum(int(item.get("forwarded", 0)) for item in all_stats.values())
        filtered = sum(int(item.get("filtered", 0)) for item in all_stats.values())
        accounts = self.account_store.list_public()
        connected_ids = [
            account["id"]
            for account in accounts
            if runtime_statuses.get(account["id"], {}).get("is_connected")
        ]
        running_ids = [
            account["id"]
            for account in accounts
            if runtime_statuses.get(account["id"], {}).get("is_running")
        ]
        return {
            "is_running": bool(running_ids),
            "is_connected": bool(connected_ids),
            "running_account_count": len(running_ids),
            "connected_account_count": len(connected_ids),
            "authenticated_account_count": sum(account["authenticated"] for account in accounts),
            "running_account_ids": running_ids,
            "connected_account_ids": connected_ids,
            "accounts": runtime_statuses,
            "stats": {
                "forwarded": forwarded,
                "filtered": filtered,
                "total": forwarded + filtered,
            },
            "queue": {
                "counts": counts,
                "paused_until": paused_until,
                "pause_reason": "; ".join(pause_reasons) or None,
            },
        }

    def list_queue_items(self, limit: int = 50) -> list[dict[str, Any]]:
        accounts = {account["id"]: account for account in self.account_store.list_public()}
        with self._state_lock:
            runtimes = list(self._runtimes.items())
        items = []
        for account_id, runtime in runtimes:
            store = getattr(runtime, "forward_queue_store", None)
            if not store:
                continue
            account = accounts.get(account_id, {})
            label = str(account.get("label") or account_id)
            for item in store.list_active(limit):
                items.append(BotManager._queue_item_data(item, account_id, label))
        items.sort(
            key=lambda item: (
                item["status"] != "processing",
                item["available_at"],
                item["id"],
            )
        )
        return items[: max(1, min(int(limit), 100))]

    def reset_stats(self) -> None:
        get_stats_db().reset_stats()
        with self._state_lock:
            runtimes = list(self._runtimes.values())
        for runtime in runtimes:
            for forwarder in getattr(runtime, "forwarders", []):
                forwarder.forwarded_count = 0
                forwarder.filtered_count = 0

    def _authenticated(self, account_id: str, identity: dict[str, Any]) -> None:
        if self.on_user_authenticated:
            self.on_user_authenticated(account_id, identity)

    async def _start_one(self, account_id: str, *, restart: bool = False) -> bool:
        runtime = self.ensure_runtime(account_id)
        if restart and runtime.is_running:
            return await runtime.restart()
        return await runtime.start()

    @staticmethod
    def _clear_queue_files(queue_path: Path) -> None:
        for suffix in ("", "-wal", "-shm"):
            Path(f"{queue_path}{suffix}").unlink(missing_ok=True)
