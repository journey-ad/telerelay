"""Persistent Telegram account registry and active-session orchestration."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.client import TelegramClientManager
from backend.logger import get_logger
from backend.i18n import t

logger = get_logger()


class TelegramAccountError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass
class TelegramAccount:
    id: str
    label: str
    display_name: str = ""
    username: str = ""
    telegram_user_id: int | None = None
    created_at: str = ""


class TelegramAccountStore:
    """Store non-secret account metadata and derive safe session paths."""

    DEFAULT_ACCOUNT_ID = "default"
    DEFAULT_LABEL = "Telegram 账号"

    def __init__(self, data_dir: str | Path = "data"):
        self.data_dir = Path(data_dir)
        self.registry_path = self.data_dir / "telegram_accounts.json"
        self.sessions_dir = self.data_dir / "telegram_sessions"
        self.avatars_dir = self.data_dir / "telegram_avatars"
        self._lock = threading.RLock()
        self._accounts: list[TelegramAccount] = []
        self._active_account_id = self.DEFAULT_ACCOUNT_ID
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._load()

    @property
    def active_account_id(self) -> str:
        with self._lock:
            return self._active_account_id

    @property
    def active_session_name(self) -> Path:
        return self.session_name(self.active_account_id)

    def list_public(
        self,
        connected: bool = False,
        *,
        connected_account_ids: set[str] | None = None,
        running_account_ids: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        with self._lock:
            active_id = self._active_account_id
            accounts = list(self._accounts)
        return [
            self._public(
                account,
                account.id == active_id,
                account.id in connected_account_ids
                if connected_account_ids is not None
                else bool(connected and account.id == active_id),
                account.id in running_account_ids
                if running_account_ids is not None
                else bool(connected and account.id == active_id),
            )
            for account in accounts
        ]

    def get_public(
        self,
        account_id: str,
        connected: bool = False,
        running: bool | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            account = self._find(account_id)
            active = account.id == self._active_account_id
        return self._public(account, active, connected, connected if running is None else running)

    def create(self, label: str) -> TelegramAccount:
        label = self.validate_label(label)
        with self._lock:
            account = TelegramAccount(
                id=uuid.uuid4().hex,
                label=label,
                created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            )
            self._accounts.append(account)
            self._active_account_id = account.id
            self._save()
            return account

    def validate_label(self, label: str) -> str:
        label = label.strip()
        if not label:
            raise TelegramAccountError("account_label_required", "Account label is required")
        with self._lock:
            if any(account.label.casefold() == label.casefold() for account in self._accounts):
                raise TelegramAccountError(
                    "duplicate_account_label", "Telegram account labels must be unique"
                )
        return label

    def set_active(self, account_id: str) -> TelegramAccount:
        with self._lock:
            account = self._find(account_id)
            self._active_account_id = account.id
            self._save()
            return account

    def update_identity(self, account_id: str, identity: dict[str, Any]) -> None:
        with self._lock:
            account = self._find(account_id)
            account.display_name = str(identity.get("display_name") or "").strip()
            account.username = str(identity.get("username") or "").strip()
            user_id = identity.get("telegram_user_id")
            account.telegram_user_id = int(user_id) if user_id is not None else None
            if account.label == self.DEFAULT_LABEL and account.display_name:
                account.label = account.display_name
            self._save()

    def clear_identity(self, account_id: str) -> None:
        with self._lock:
            account = self._find(account_id)
            account.display_name = ""
            account.username = ""
            account.telegram_user_id = None
            self._save()

    def update_avatar(self, account_id: str, avatar_bytes: bytes | None) -> None:
        with self._lock:
            self._find(account_id)
            avatar_path = self.avatar_path(account_id)
            if avatar_bytes is None:
                avatar_path.unlink(missing_ok=True)
                return
            if not avatar_bytes or len(avatar_bytes) > 5 * 1024 * 1024:
                raise TelegramAccountError("invalid_avatar", "Invalid Telegram avatar data")
            self.avatars_dir.mkdir(parents=True, exist_ok=True)
            file_descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{account_id}-",
                suffix=".tmp",
                dir=self.avatars_dir,
            )
            try:
                with os.fdopen(file_descriptor, "wb") as handle:
                    handle.write(avatar_bytes)
                os.replace(temporary_name, avatar_path)
            finally:
                if os.path.exists(temporary_name):
                    os.unlink(temporary_name)

    def clear_avatar(self, account_id: str) -> None:
        self.avatar_path(account_id).unlink(missing_ok=True)

    def get_avatar_path(self, account_id: str) -> Path | None:
        with self._lock:
            self._find(account_id)
            path = self.avatar_path(account_id)
            return path if path.is_file() else None

    def delete(self, account_id: str) -> tuple[Path, TelegramAccount]:
        with self._lock:
            account = self.validate_delete(account_id)
            self._accounts = [item for item in self._accounts if item.id != account.id]
            if self._active_account_id == account.id:
                self._active_account_id = self._accounts[0].id
            self._save()
            return self.session_name(account.id), account

    def validate_delete(self, account_id: str) -> TelegramAccount:
        with self._lock:
            account = self._find(account_id)
            if len(self._accounts) == 1:
                raise TelegramAccountError(
                    "last_account", "At least one Telegram account must remain"
                )
            return account

    def session_name(self, account_id: str) -> Path:
        if account_id == self.DEFAULT_ACCOUNT_ID:
            return self.data_dir / "telegram_session"
        if not account_id or any(character not in "0123456789abcdef" for character in account_id):
            raise TelegramAccountError("invalid_account_id", "Invalid Telegram account id")
        return self.sessions_dir / f"account_{account_id}"

    def avatar_path(self, account_id: str) -> Path:
        if account_id != self.DEFAULT_ACCOUNT_ID and (
            not account_id
            or any(character not in "0123456789abcdef" for character in account_id)
        ):
            raise TelegramAccountError("invalid_account_id", "Invalid Telegram account id")
        return self.avatars_dir / f"{account_id}.jpg"

    def has_session(self, account_id: str) -> bool:
        return Path(f"{self.session_name(account_id)}.session").is_file()

    def _public(
        self,
        account: TelegramAccount,
        active: bool,
        connected: bool,
        running: bool,
    ) -> dict[str, Any]:
        authenticated = self.has_session(account.id) and (
            account.id == self.DEFAULT_ACCOUNT_ID or account.telegram_user_id is not None
        )
        avatar_path = self.avatar_path(account.id)
        avatar_version = str(avatar_path.stat().st_mtime_ns) if avatar_path.is_file() else None
        status = "connected" if connected else "authenticated" if authenticated else "needs_auth"
        return {
            **asdict(account),
            "active": active,
            "authenticated": authenticated,
            "running": bool(running),
            "connected": bool(connected),
            "status": status,
            "avatar_version": avatar_version,
        }

    def _find(self, account_id: str) -> TelegramAccount:
        for account in self._accounts:
            if account.id == account_id:
                return account
        raise TelegramAccountError("account_not_found", "Telegram account does not exist")

    def _load(self) -> None:
        with self._lock:
            if self.registry_path.is_file():
                try:
                    payload = json.loads(self.registry_path.read_text(encoding="utf-8"))
                    accounts = [
                        TelegramAccount(
                            id=str(item["id"]),
                            label=str(item["label"]),
                            display_name=str(item.get("display_name") or ""),
                            username=str(item.get("username") or ""),
                            telegram_user_id=item.get("telegram_user_id"),
                            created_at=str(item.get("created_at") or ""),
                        )
                        for item in payload.get("accounts", [])
                    ]
                    if accounts:
                        self._accounts = accounts
                        requested_active = str(payload.get("active_account_id") or "")
                        self._active_account_id = (
                            requested_active
                            if any(item.id == requested_active for item in accounts)
                            else accounts[0].id
                        )
                        return
                except (OSError, ValueError, KeyError, TypeError):
                    pass

            self._accounts = [
                TelegramAccount(
                    id=self.DEFAULT_ACCOUNT_ID,
                    label=self.DEFAULT_LABEL,
                    created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                )
            ]
            self._active_account_id = self.DEFAULT_ACCOUNT_ID
            self._save()

    def _save(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "active_account_id": self._active_account_id,
            "accounts": [asdict(account) for account in self._accounts],
        }
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=".telegram-accounts-",
            suffix=".tmp",
            dir=self.data_dir,
        )
        try:
            with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            os.replace(temporary_name, self.registry_path)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)


class TelegramAccountService:
    """Coordinate account metadata with isolated parallel runtimes."""

    def __init__(self, store: TelegramAccountStore, runtimes):
        self.store = store
        self.runtimes = runtimes
        self._mutation_lock = asyncio.Lock()

    def list_accounts(self) -> list[dict[str, Any]]:
        account_ids = [account["id"] for account in self.store.list_public()]
        connected_ids = {
            account_id
            for account_id in account_ids
            if self.runtimes.is_account_connected(account_id)
        }
        running_ids = {
            account_id
            for account_id in account_ids
            if self.runtimes.is_account_running(account_id)
        }
        return self.store.list_public(
            connected_account_ids=connected_ids,
            running_account_ids=running_ids,
        )

    async def create(self, label: str) -> dict[str, Any]:
        async with self._mutation_lock:
            label = self.store.validate_label(label)
            account = self.store.create(label)
            self.runtimes.ensure_runtime(account.id)
            return self._public(account.id)

    async def activate(self, account_id: str) -> dict[str, Any]:
        async with self._mutation_lock:
            self.store.set_active(account_id)
            self.runtimes.ensure_runtime(account_id)
            return self._public(account_id)

    async def delete(self, account_id: str) -> None:
        async with self._mutation_lock:
            self.store.validate_delete(account_id)
            session_name = self.store.session_name(account_id)
            self.runtimes.block_account(account_id)
            try:
                await self.runtimes.remove_runtime(account_id, clear_queue=True)
                await asyncio.to_thread(TelegramClientManager.clear_session_files, session_name)
                await asyncio.to_thread(self.store.clear_avatar, account_id)
                self.store.delete(account_id)
            finally:
                self.runtimes.unblock_account(account_id)

    async def clear_active_session(self) -> None:
        async with self._mutation_lock:
            account_id = self.store.active_account_id
            await self.runtimes.stop_account(account_id)
            await asyncio.to_thread(
                TelegramClientManager.clear_session_files,
                self.store.session_name(account_id),
            )
            self.store.clear_identity(account_id)
            await asyncio.to_thread(self.store.clear_avatar, account_id)

    def update_identity(self, account_id: str, identity: dict[str, Any]) -> None:
        self.store.update_identity(account_id, identity)
        if "avatar_bytes" in identity:
            try:
                self.store.update_avatar(account_id, identity["avatar_bytes"])
            except (OSError, TelegramAccountError) as exc:
                logger.warning(t("log.account.avatar_cache_failed", error=str(exc)))
        events = getattr(self.runtimes, "events", None)
        if events:
            events.publish("telegram-account", {"action": "authenticated", "account_id": account_id})
            events.publish("telegram-auth", {"state": "success", "account_id": account_id})

    def get_auth(self):
        return self.runtimes.get_auth(self.store.active_account_id)

    async def start_authentication(self) -> bool:
        account_id = self.store.active_account_id
        self.get_auth().reset()
        return await self.runtimes.start_account(account_id)

    def _public(self, account_id: str) -> dict[str, Any]:
        return self.store.get_public(
            account_id,
            connected=self.runtimes.is_account_connected(account_id),
            running=self.runtimes.is_account_running(account_id),
        )
