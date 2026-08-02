"""Persistent Telegram account registry and active-session orchestration."""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import tempfile
import threading
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.account_paths import (
    AccountPathRegistry,
    is_telegram_user_id,
    normalize_telegram_user_id,
)
from backend.auth_manager import AuthManager
from backend.client import TelegramClientManager
from backend.i18n import t
from backend.logger import account_log_context, get_logger

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
    kind: str = "user"


@dataclass
class PendingAuthentication:
    account_id: str
    auth: AuthManager
    temporary_directory: tempfile.TemporaryDirectory
    session_name: Path
    task: asyncio.Task | None = None
    on_finalized: Callable[[str, str], None] | None = None


class TelegramAccountStore:
    """Store non-secret account metadata and derive safe session paths."""

    DEFAULT_ACCOUNT_ID = "default"
    DEFAULT_LABEL = "Telegram 账号"

    def __init__(
        self,
        data_dir: str | Path = "data",
        paths: AccountPathRegistry | None = None,
    ):
        self.data_dir = Path(data_dir)
        self.paths = paths or AccountPathRegistry(
            config_dir=self.data_dir.parent / "config",
            data_dir=self.data_dir,
        )
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

    def create(
        self,
        label: str,
        kind: str = "user",
        *,
        activate: bool = True,
    ) -> TelegramAccount:
        """Create a pending account row without creating account-scoped files."""
        label = self.validate_label(label)
        if kind not in ("user", "bot"):
            raise TelegramAccountError(
                "invalid_account_kind",
                "Account kind must be user or bot",
            )
        with self._lock:
            account = TelegramAccount(
                id=uuid.uuid4().hex,
                label=label,
                created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                kind=kind,
            )
            self._accounts.append(account)
            if activate:
                self._active_account_id = account.id
            self._save()
            return account

    @staticmethod
    def validate_bot_token(token: str) -> str:
        token = token.strip()
        if not re.fullmatch(r"\d+:[A-Za-z0-9_-]{20,}", token):
            raise TelegramAccountError("invalid_bot_token", "Bot token format is invalid")
        return token

    def set_bot_token(self, account_id: str, token: str) -> None:
        token = self.validate_bot_token(token)
        with self._lock:
            self._find(account_id)
        path = self.data_dir / "bot_tokens" / f"{account_id}.token"
        path.parent.mkdir(parents=True, exist_ok=True)
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=".bot-token-",
            suffix=".tmp",
            dir=path.parent,
        )
        try:
            with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
                handle.write(token)
                handle.write("\n")
            os.chmod(temporary_name, 0o600)
            os.replace(temporary_name, path)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)

    def get_bot_token(self, account_id: str) -> str:
        with self._lock:
            self._find(account_id)
        path = self.data_dir / "bot_tokens" / f"{account_id}.token"
        if not path.is_file():
            token = self._recover_orphaned_bot_token(account_id)
            if token is not None:
                return token
            raise TelegramAccountError(
                "bot_token_missing",
                "Bot token is missing for this account",
            )
        return path.read_text(encoding="utf-8").strip()

    def _recover_orphaned_bot_token(self, account_id: str) -> str | None:
        """Recover a bot token left under a pre-finalization account id."""
        if not is_telegram_user_id(account_id):
            return None
        directory = self.data_dir / "bot_tokens"
        if not directory.is_dir():
            return None
        expected_prefix = f"{account_id}:"
        for path in sorted(directory.glob("*.token")):
            if path.name == f"{account_id}.token":
                continue
            try:
                token = path.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if token.startswith(expected_prefix):
                destination = directory / f"{account_id}.token"
                try:
                    os.replace(path, destination)
                except OSError:
                    pass
                return token
        return None

    def clear_bot_token(self, account_id: str) -> None:
        (self.data_dir / "bot_tokens" / f"{account_id}.token").unlink(missing_ok=True)

    def seed_bot(self, token: str, label: str = "Telegram Bot") -> TelegramAccount:
        """Upgrade a legacy .env-only bot install into a first-class bot account."""
        token = self.validate_bot_token(token)
        with self._lock:
            existing = next(
                (account for account in self._accounts if account.kind == "bot"),
                None,
            )
            if existing is not None:
                try:
                    self.get_bot_token(existing.id)
                except TelegramAccountError:
                    self.set_bot_token(existing.id, token)
                return existing
            if len(self._accounts) == 1 and self._accounts[0].telegram_user_id is None:
                account = self._accounts[0]
                account.label = label
                account.kind = "bot"
            else:
                account = TelegramAccount(
                    id=uuid.uuid4().hex,
                    label=label,
                    created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    kind="bot",
                )
                self._accounts.append(account)
                self._active_account_id = account.id
            self._save()
        self.set_bot_token(account.id, token)
        self._adopt_legacy_bot_session(account.id)
        return account

    def _adopt_legacy_bot_session(self, account_id: str) -> None:
        legacy = self.data_dir / "telegram_session.session"
        if not legacy.is_file():
            return
        target = Path(f"{self.session_name(account_id)}.session")
        if target.exists():
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        for suffix in ("", "-wal", "-shm", "-journal"):
            source = Path(f"{legacy}{suffix}")
            if source.is_file():
                shutil.move(str(source), str(Path(f"{target}{suffix}")))

    def validate_label(self, label: str, exclude_account_id: str | None = None) -> str:
        label = label.strip()
        if not label:
            raise TelegramAccountError("account_label_required", "Account label is required")
        with self._lock:
            if any(
                account.id != exclude_account_id
                and account.label.casefold() == label.casefold()
                for account in self._accounts
            ):
                raise TelegramAccountError(
                    "duplicate_account_label", "Telegram account labels must be unique"
                )
        return label

    def update_label(self, account_id: str, label: str) -> TelegramAccount:
        label = self.validate_label(label, exclude_account_id=account_id)
        with self._lock:
            account = self._find(account_id)
            account.label = label
            self._save()
            return account

    def set_active(self, account_id: str) -> TelegramAccount:
        with self._lock:
            account = self._find(account_id)
            self._active_account_id = account.id
            self._save()
            return account

    def update_identity(self, account_id: str, identity: dict[str, Any]) -> None:
        with self._lock:
            account = self._find(account_id)
            requested_id = normalize_telegram_user_id(identity.get("telegram_user_id"))
            if account.id != requested_id:
                raise TelegramAccountError(
                    "account_not_finalized",
                    "Pending accounts must be finalized before updating identity",
                )
            account.display_name = str(identity.get("display_name") or "").strip()
            account.username = str(identity.get("username") or "").strip()
            user_id = identity.get("telegram_user_id")
            account.telegram_user_id = int(user_id) if user_id is not None else None
            if account.label == self.DEFAULT_LABEL and account.display_name:
                account.label = account.display_name
            self._save()

    def validate_finalization(self, account_id: str, telegram_user_id: object) -> str:
        target_id = normalize_telegram_user_id(telegram_user_id)
        with self._lock:
            self._find(account_id)
            if is_telegram_user_id(account_id) and account_id != target_id:
                raise TelegramAccountError(
                    "telegram_account_mismatch",
                    "Authenticated Telegram id does not match this account",
                )
            if any(account.id == target_id and account.id != account_id for account in self._accounts):
                raise TelegramAccountError(
                    "duplicate_telegram_account",
                    "This Telegram account already exists",
                )
        return target_id

    def finalize_identity(self, account_id: str, identity: dict[str, Any]) -> TelegramAccount:
        """Replace a pending/legacy row id with its authenticated Telegram id."""
        target_id = self.validate_finalization(account_id, identity.get("telegram_user_id"))
        with self._lock:
            account = self._find(account_id)
            if account.id != target_id:
                previous_id = account.id
                account.id = target_id
                if self._active_account_id == previous_id:
                    self._active_account_id = target_id
                if account.kind == "bot":
                    self._migrate_bot_token(previous_id, target_id)
            account.display_name = str(identity.get("display_name") or "").strip()
            account.username = str(identity.get("username") or "").strip()
            account.telegram_user_id = int(target_id)
            if account.label == self.DEFAULT_LABEL and account.display_name:
                account.label = account.display_name
            self._save()
            return account

    def _migrate_bot_token(self, previous_id: str, target_id: str) -> None:
        source = self.data_dir / "bot_tokens" / f"{previous_id}.token"
        if not source.is_file():
            return
        destination = self.data_dir / "bot_tokens" / f"{target_id}.token"
        if destination.exists():
            source.unlink(missing_ok=True)
            return
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(source, destination)

    def clear_identity(self, account_id: str) -> None:
        with self._lock:
            account = self._find(account_id)
            account.display_name = ""
            account.username = ""
            if not is_telegram_user_id(account.id):
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
            avatar_path.parent.mkdir(parents=True, exist_ok=True)
            file_descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{account_id}-",
                suffix=".tmp",
                dir=avatar_path.parent,
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
            self.clear_bot_token(account_id)
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
        if is_telegram_user_id(account_id):
            return self.paths.for_account(account_id).session_name
        if account_id == self.DEFAULT_ACCOUNT_ID:
            return self.data_dir / "telegram_session"
        if not account_id or any(character not in "0123456789abcdef" for character in account_id):
            raise TelegramAccountError("invalid_account_id", "Invalid Telegram account id")
        return self.sessions_dir / f"account_{account_id}"

    def avatar_path(self, account_id: str) -> Path:
        if is_telegram_user_id(account_id):
            return self.paths.for_account(account_id).avatar
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
        authenticated = self.has_session(account.id) and account.telegram_user_id is not None
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
                            kind=str(item.get("kind") or "user"),
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
                    id=uuid.uuid4().hex,
                    label=self.DEFAULT_LABEL,
                    created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                )
            ]
            self._active_account_id = self._accounts[0].id
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
        self._pending_authentications: dict[str, PendingAuthentication] = {}
        self._recent_auth: tuple[str, AuthManager] | None = None
        self._bot_auths: dict[str, AuthManager] = {}
        self.on_account_finalized = None
        self.on_account_deleted = None

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

    async def create(
        self,
        label: str,
        *,
        kind: str = "user",
        bot_token: str | None = None,
    ) -> dict[str, Any]:
        label = self.store.validate_label(label)
        if kind == "bot":
            if not bot_token:
                raise TelegramAccountError(
                    "bot_token_required",
                    "Bot token is required",
                )
            token = self.store.validate_bot_token(bot_token)
        else:
            token = None

        async with self._mutation_lock:
            account = self.store.create(label, kind=kind, activate=token is None)
            if token is not None:
                self.store.set_bot_token(account.id, token)

        if token is None:
            return self._public(account.id)

        finalized_id = account.id

        def finalized(_previous_id: str, account_id: str) -> None:
            nonlocal finalized_id
            finalized_id = account_id

        try:
            self._recent_auth = None
            auth = AuthManager(input_timeout=self.runtimes.auth_timeout)
            pending = self._new_pending_authentication(
                account.id,
                auth,
                on_finalized=finalized,
            )
            self._pending_authentications[account.id] = pending
            pending.task = asyncio.create_task(
                self._authenticate_pending(pending),
                name=f"telerelay-account-auth-{account.id}",
            )
            await asyncio.sleep(0)
            auth = pending.auth
            await asyncio.gather(pending.task, return_exceptions=True)
            state = auth.get_state()
            if state.get("state") != "success":
                raise TelegramAccountError(
                    "bot_auth_failed",
                    state.get("error") or "Bot account could not be authenticated",
                )
            async with self._mutation_lock:
                self.store.set_active(finalized_id)
            return self._public(finalized_id)
        except BaseException:
            try:
                await self.delete(finalized_id)
            except Exception:
                logger.exception(
                    "Failed to roll back Telegram bot account creation: %s",
                    finalized_id,
                )
            raise

    async def update_bot_token(self, account_id: str, token: str) -> dict[str, Any]:
        account = self.store.get_public(account_id)
        if account["kind"] != "bot":
            raise TelegramAccountError(
                "invalid_account_kind",
                "Bot token can only be updated for bot accounts",
            )
        token = self.store.validate_bot_token(token)
        identity = await self._verify_bot_token(account_id, token)
        runtime = self.runtimes.get_runtime(account_id)
        previous_token = self.store.get_bot_token(account_id)
        was_running = runtime.is_running

        async with self._mutation_lock:
            self.store.get_public(account_id)
            self.store.set_bot_token(account_id, token)
            runtime.bot_token = token

        try:
            started = await (runtime.restart() if was_running else runtime.start())
            if not started:
                raise TelegramAccountError(
                    "bot_restart_failed",
                    "Bot runtime could not be restarted",
                )
        except BaseException:
            async with self._mutation_lock:
                self.store.set_bot_token(account_id, previous_token)
                runtime.bot_token = previous_token
            if was_running and not runtime.is_running:
                await runtime.start()
            raise

        self.update_identity(account_id, identity)
        return self._public(account_id)

    async def _verify_bot_token(self, account_id: str, token: str) -> dict[str, Any]:
        identity: dict[str, Any] = {}
        auth = AuthManager(input_timeout=self.runtimes.auth_timeout)
        temporary_directory = tempfile.TemporaryDirectory(prefix="telerelay-bot-token-")
        session_name = Path(temporary_directory.name) / "telegram"
        config_registry = getattr(self.runtimes, "config_registry", None)
        config = (
            config_registry.for_account(account_id)
            if config_registry is not None
            else self.runtimes.config
        )
        manager = TelegramClientManager(
            config,
            auth,
            session_name=session_name,
            on_user_authenticated=lambda value: identity.update(value),
            bot_token=token,
        )
        try:
            with account_log_context(account_id):
                if not await manager.connect() or not identity:
                    state = auth.get_state()
                    raise TelegramAccountError(
                        "bot_auth_failed",
                        state.get("error") or "Bot account could not be authenticated",
                    )
            self.store.validate_finalization(
                account_id,
                identity.get("telegram_user_id"),
            )
            return identity
        finally:
            await manager.disconnect()
            temporary_directory.cleanup()

    async def activate(self, account_id: str) -> dict[str, Any]:
        async with self._mutation_lock:
            self.store.set_active(account_id)
            if is_telegram_user_id(account_id):
                self.runtimes.ensure_runtime(account_id)
            return self._public(account_id)

    async def rename(self, account_id: str, label: str) -> dict[str, Any]:
        async with self._mutation_lock:
            account = self.store.update_label(account_id, label)
            return self._public(account.id)

    async def delete(self, account_id: str) -> None:
        async with self._mutation_lock:
            self.store.validate_delete(account_id)
            self._bot_auths.pop(account_id, None)
            pending = self._pending_authentications.pop(account_id, None)
            if pending:
                if pending.task and not pending.task.done():
                    pending.task.cancel()
                    await asyncio.gather(pending.task, return_exceptions=True)
                pending.auth.reset()
                pending.temporary_directory.cleanup()
            if is_telegram_user_id(account_id):
                self.runtimes.block_account(account_id)
                try:
                    await self.runtimes.remove_runtime(
                        account_id,
                        clear_queue=getattr(self.runtimes, "paths", None) is None,
                    )
                    if self.on_account_deleted:
                        self.on_account_deleted(account_id)
                    await asyncio.to_thread(self.store.paths.remove_account_data, account_id)
                    self.store.delete(account_id)
                finally:
                    self.runtimes.unblock_account(account_id)
            else:
                self.store.delete(account_id)

    async def clear_session(self, account_id: str | None = None) -> None:
        async with self._mutation_lock:
            account_id = account_id or self.store.active_account_id
            self.store.get_public(account_id)
            await self.runtimes.stop_account(account_id)
            await asyncio.to_thread(
                TelegramClientManager.clear_session_files,
                self.store.session_name(account_id),
            )
            self.store.clear_identity(account_id)
            await asyncio.to_thread(self.store.clear_avatar, account_id)
            bot_auth = self._bot_auths.pop(account_id, None)
            if bot_auth is not None:
                bot_auth.reset()

    def update_identity(self, account_id: str, identity: dict[str, Any]) -> None:
        if is_telegram_user_id(account_id):
            self.store.update_identity(account_id, identity)
            finalized_id = account_id
        else:
            account = self.store.finalize_identity(account_id, identity)
            finalized_id = account.id
        if "avatar_bytes" in identity:
            try:
                self.store.update_avatar(finalized_id, identity["avatar_bytes"])
            except (OSError, TelegramAccountError) as exc:
                logger.warning(t("log.account.avatar_cache_failed", error=str(exc)))
        events = getattr(self.runtimes, "events", None)
        if events:
            events.publish(
                "telegram-account",
                {"action": "authenticated", "account_id": finalized_id},
            )
            events.publish("telegram-auth", {"state": "success", "account_id": finalized_id})
        if self.store.get_public(finalized_id).get("kind") == "bot":
            bot_auth = self._bot_auths.get(finalized_id)
            if bot_auth is None:
                bot_auth = AuthManager(input_timeout=self.runtimes.auth_timeout)
                self._bot_auths[finalized_id] = bot_auth
            user_info = " ".join(
                filter(
                    None,
                    [
                        str(identity.get("display_name") or ""),
                        f"@{identity['username']}" if identity.get("username") else "",
                    ],
                )
            ).strip()
            if user_info:
                bot_auth.set_user_info(user_info)
            if bot_auth.get_state()["state"] != "success":
                bot_auth.set_state("success")

    def get_auth(self, account_id: str | None = None):
        account_id = account_id or self.store.active_account_id
        self.store.get_public(account_id)
        pending = self._pending_authentications.get(account_id)
        if pending:
            return pending.auth
        if self._recent_auth and self._recent_auth[0] == account_id:
            return self._recent_auth[1]
        if is_telegram_user_id(account_id):
            if self.store.get_public(account_id)["kind"] == "bot":
                auth = self._bot_auths.get(account_id)
                if auth is None:
                    auth = AuthManager(input_timeout=self.runtimes.auth_timeout)
                    self._bot_auths[account_id] = auth
                return auth
            return self.runtimes.get_auth(account_id)
        auth = AuthManager(input_timeout=self.runtimes.auth_timeout)
        self._pending_authentications[account_id] = self._new_pending_authentication(
            account_id,
            auth,
        )
        return auth

    async def start_authentication(
        self,
        account_id: str | None = None,
        *,
        on_finalized: Callable[[str, str], None] | None = None,
    ) -> bool:
        account_id = account_id or self.store.active_account_id
        self.store.get_public(account_id)
        self._recent_auth = None
        if is_telegram_user_id(account_id) and self.store.has_session(account_id):
            self.get_auth(account_id).reset()
            return await self.runtimes.start_account(account_id)
        pending = self._pending_authentications.get(account_id)
        if pending and pending.task and not pending.task.done():
            return False
        if pending:
            pending.temporary_directory.cleanup()
        auth = pending.auth if pending else AuthManager(input_timeout=self.runtimes.auth_timeout)
        auth.reset()
        pending = self._new_pending_authentication(account_id, auth, on_finalized=on_finalized)
        self._pending_authentications[account_id] = pending
        pending.task = asyncio.create_task(
            self._authenticate_pending(pending),
            name=f"telerelay-account-auth-{account_id}",
        )
        await asyncio.sleep(0)
        return True

    async def shutdown(self) -> None:
        """Cancel pending authentication clients and remove their temporary sessions."""
        async with self._mutation_lock:
            pending_authentications = list(self._pending_authentications.values())
            self._pending_authentications.clear()
            self._recent_auth = None
            self._bot_auths.clear()
            tasks = []
            for pending in pending_authentications:
                if pending.task and not pending.task.done():
                    pending.task.cancel()
                    tasks.append(pending.task)
                pending.auth.reset()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            for pending in pending_authentications:
                pending.temporary_directory.cleanup()

    def is_authentication_running(self, account_id: str) -> bool:
        pending = self._pending_authentications.get(account_id)
        if pending and pending.task and not pending.task.done():
            return True
        return self.runtimes.is_account_running(account_id)

    def _new_pending_authentication(
        self,
        account_id: str,
        auth: AuthManager,
        *,
        on_finalized: Callable[[str, str], None] | None = None,
    ) -> PendingAuthentication:
        temporary_directory = tempfile.TemporaryDirectory(prefix="telerelay-auth-")
        session_name = Path(temporary_directory.name) / "telegram"
        legacy_name = self.store.session_name(account_id)
        for suffix in (".session", ".session-journal"):
            source = Path(f"{legacy_name}{suffix}")
            destination = Path(f"{session_name}{suffix}")
            if source.is_file():
                shutil.copy2(source, destination)
        auth.set_on_state_change(
            lambda state, error="", target=account_id: self.runtimes._publish_auth_state(
                target, state, error
            )
        )
        return PendingAuthentication(
            account_id,
            auth,
            temporary_directory,
            session_name,
            on_finalized=on_finalized,
        )

    async def _authenticate_pending(self, pending: PendingAuthentication) -> None:
        with account_log_context(pending.account_id):
            await self._authenticate_pending_scoped(pending)

    async def _authenticate_pending_scoped(self, pending: PendingAuthentication) -> None:
        identity: dict[str, Any] = {}
        account = self.store.get_public(pending.account_id)
        bot_token = (
            self.store.get_bot_token(pending.account_id)
            if account["kind"] == "bot"
            else None
        )
        if bot_token is not None:
            pending.auth.set_state("connecting")
        manager = TelegramClientManager(
            self.runtimes.config,
            pending.auth,
            session_name=pending.session_name,
            on_user_authenticated=lambda value: identity.update(value),
            bot_token=bot_token,
        )
        try:
            if not await manager.connect() or not identity:
                return
            await manager.disconnect()
            target_id = self.store.validate_finalization(
                pending.account_id,
                identity.get("telegram_user_id"),
            )
            if not self.store.paths.adopt_session(pending.session_name, target_id):
                raise TelegramAccountError(
                    "session_migration_failed",
                    "Authenticated Telegram session could not be saved",
                )
            account = self.store.finalize_identity(pending.account_id, identity)
            if "avatar_bytes" in identity:
                self.store.update_avatar(account.id, identity["avatar_bytes"])
            if bot_token is not None:
                pending.auth.set_state("success")
            if pending.on_finalized:
                pending.on_finalized(pending.account_id, account.id)
            self._pending_authentications.pop(pending.account_id, None)
            self._recent_auth = (account.id, pending.auth)
            if bot_token is not None:
                self._bot_auths[account.id] = pending.auth
            events = getattr(self.runtimes, "events", None)
            if events:
                events.publish(
                    "telegram-account",
                    {
                        "action": "authenticated",
                        "account_id": account.id,
                        "previous_account_id": pending.account_id,
                    },
                )
                events.publish(
                    "telegram-auth",
                    {
                        "state": "success",
                        "account_id": account.id,
                        "previous_account_id": pending.account_id,
                    },
                )
            runtime = self.runtimes.ensure_runtime(account.id)
            if self.on_account_finalized:
                self.on_account_finalized(account.id)
            await runtime.start()
        except asyncio.CancelledError:
            await manager.disconnect()
            raise
        except Exception as exc:
            pending.auth.set_state("error", str(exc))
            logger.exception("Pending Telegram account authentication failed: %s", exc)
        finally:
            await manager.disconnect()
            pending.temporary_directory.cleanup()

    def _public(self, account_id: str) -> dict[str, Any]:
        return self.store.get_public(
            account_id,
            connected=self.runtimes.is_account_connected(account_id),
            running=self.runtimes.is_account_running(account_id),
        )
