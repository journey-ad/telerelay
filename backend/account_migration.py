"""One-time migration from shared and UUID-based account storage layouts."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from backend.account_paths import AccountPathRegistry, AccountPaths, normalize_telegram_user_id
from backend.logger import get_logger

if TYPE_CHECKING:
    from backend.telegram_accounts import TelegramAccountService

logger = get_logger()


class AccountMigration:
    """Upgrade legacy account metadata and files before normal services start."""

    LEGACY_DEFAULT_ID = "default"
    LEGACY_DEFAULT_LABEL = "Telegram 账号"

    def __init__(self, paths: AccountPathRegistry):
        self.paths = paths
        self.registry_path = paths.data_dir / "telegram_accounts.json"

    def run(self) -> bool:
        """Prepare and migrate every account whose Telegram id is already known."""
        self._prepare_default_registry()
        if not self.registry_path.is_file():
            return False
        try:
            payload = json.loads(self.registry_path.read_text(encoding="utf-8"))
            accounts = payload.get("accounts")
            if not isinstance(accounts, list) or not accounts:
                return False
        except (OSError, ValueError, TypeError):
            logger.warning("Skipped unreadable Telegram account registry migration")
            return False

        changed = False
        id_map: dict[str, str] = {}
        seen_ids: set[str] = set()
        normalized_accounts: list[dict] = []
        for raw_account in accounts:
            if not isinstance(raw_account, dict) or "id" not in raw_account:
                logger.warning("Skipped malformed Telegram account registry migration")
                return False
            account = dict(raw_account)
            legacy_id = str(account["id"])
            target_id = legacy_id
            telegram_user_id = account.get("telegram_user_id")
            if telegram_user_id is not None:
                try:
                    target_id = normalize_telegram_user_id(telegram_user_id)
                    account["telegram_user_id"] = int(target_id)
                except ValueError:
                    account["telegram_user_id"] = None
                    changed = True

            if target_id in seen_ids:
                logger.warning("Ignored duplicate Telegram account id during migration: %s", target_id)
                changed = True
                continue
            seen_ids.add(target_id)
            if legacy_id != target_id:
                self.migrate_account_data(legacy_id, target_id)
                account["id"] = target_id
                id_map[legacy_id] = target_id
                changed = True
            elif account.get("telegram_user_id") is not None:
                pass
            normalized_accounts.append(account)

        active_id = str(payload.get("active_account_id") or "")
        if active_id in id_map:
            active_id = id_map[active_id]
            changed = True
        if active_id not in seen_ids:
            active_id = str(normalized_accounts[0]["id"])
            changed = True

        if changed:
            payload["accounts"] = normalized_accounts
            payload["active_account_id"] = active_id
            self._save_registry(payload)
        self._cleanup_legacy_preview_cache()
        return changed

    async def resolve_default_account(self, accounts: TelegramAccountService) -> bool:
        """Connect an old default session when its Telegram id was never persisted."""
        try:
            accounts.store.get_public(self.LEGACY_DEFAULT_ID)
        except ValueError:
            return False
        if not accounts.store.has_session(self.LEGACY_DEFAULT_ID):
            return False

        def finish(legacy_id: str, target_id: str) -> None:
            self.migrate_account_data(legacy_id, target_id, adopted_session=True)

        return await accounts.start_authentication(
            self.LEGACY_DEFAULT_ID,
            on_finalized=finish,
        )

    def migrate_account_data(
        self,
        legacy_account_id: str,
        telegram_user_id: str | int,
        *,
        adopted_session: bool = False,
    ) -> AccountPaths:
        """Move known legacy artifacts without overwriting existing destinations."""
        paths = self.paths.for_account(telegram_user_id)
        if legacy_account_id == self.LEGACY_DEFAULT_ID:
            self._migrate_default(paths, adopted_session=adopted_session)
        else:
            self._migrate_named_account(legacy_account_id, paths)
        return paths

    def _prepare_default_registry(self) -> None:
        if self.registry_path.exists():
            return
        legacy_session = self.paths.data_dir / "telegram_session.session"
        if not legacy_session.is_file():
            return
        payload = {
            "version": 1,
            "active_account_id": self.LEGACY_DEFAULT_ID,
            "accounts": [
                {
                    "id": self.LEGACY_DEFAULT_ID,
                    "label": self.LEGACY_DEFAULT_LABEL,
                    "display_name": "",
                    "username": "",
                    "telegram_user_id": None,
                    "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                }
            ],
        }
        self._save_registry(payload)

    def _save_registry(self, payload: dict) -> None:
        self.paths.data_dir.mkdir(parents=True, exist_ok=True)
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=".telegram-accounts-migration-",
            suffix=f"-{uuid.uuid4().hex}.tmp",
            dir=self.paths.data_dir,
        )
        try:
            with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            os.replace(temporary_name, self.registry_path)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)

    def _migrate_default(self, target: AccountPaths, *, adopted_session: bool) -> None:
        self._move_file(self.paths.config_dir / "config.yaml", target.config_file)
        legacy_session = self.paths.data_dir / "telegram_session.session"
        if adopted_session and Path(f"{target.session_name}.session").is_file():
            self._remove_sqlite(legacy_session)
        else:
            self._move_sqlite(legacy_session, Path(f"{target.session_name}.session"))
        self._move_sqlite(self.paths.data_dir / "forward_queue.db", target.queue_db)
        self._move_sqlite(self.paths.data_dir / "stats.db", target.stats_db)
        self._move_sqlite(self.paths.data_dir / "exports.db", target.exports_db)
        self._merge_directory(self.paths.data_dir / "db", target.message_db_dir)
        self._merge_directory(self.paths.data_dir / "exports", target.export_dir)
        self._move_file(
            self.paths.data_dir / "telegram_avatars" / "default.jpg",
            target.avatar,
        )

    def _migrate_named_account(self, legacy_id: str, target: AccountPaths) -> None:
        config_candidates = (
            self.paths.config_dir / "accounts" / f"account_{legacy_id}.yaml",
            self.paths.config_dir / "accounts" / f"{legacy_id}.yaml",
            self.paths.config_dir / f"{legacy_id}.yaml",
        )
        for source in config_candidates:
            if self._move_file(source, target.config_file):
                break

        self._merge_directory(self.paths.data_dir / legacy_id, target.data_dir)
        self._move_sqlite(
            self.paths.data_dir / "telegram_sessions" / f"account_{legacy_id}.session",
            Path(f"{target.session_name}.session"),
        )
        self._move_sqlite(
            self.paths.data_dir / "forward_queues" / f"account_{legacy_id}.db",
            target.queue_db,
        )
        old_data = self.paths.data_dir / "account_data" / f"account_{legacy_id}"
        self._move_sqlite(old_data / "stats.db", target.stats_db)
        self._move_sqlite(old_data / "exports.db", target.exports_db)
        self._merge_directory(old_data / "db", target.message_db_dir)
        self._merge_directory(old_data / "exports", target.export_dir)
        self._move_file(
            self.paths.data_dir / "telegram_avatars" / f"{legacy_id}.jpg",
            target.avatar,
        )

    def _cleanup_legacy_preview_cache(self) -> None:
        legacy_root = self.paths.data_dir / "telegram_preview_cache"
        if legacy_root.is_dir():
            # Finder metadata must not keep an otherwise migrated cache root alive.
            (legacy_root / ".DS_Store").unlink(missing_ok=True)
            try:
                legacy_root.rmdir()
            except OSError:
                return
        if not legacy_root.exists():
            (self.paths.data_dir / ".telegram_preview_cache.key").unlink(missing_ok=True)

    def _move_sqlite(self, source: Path, destination: Path) -> None:
        if not self._move_file(source, destination):
            return
        for suffix in ("-wal", "-shm", "-journal"):
            self._move_file(Path(f"{source}{suffix}"), Path(f"{destination}{suffix}"))

    @staticmethod
    def _remove_sqlite(path: Path) -> None:
        for suffix in ("", "-wal", "-shm", "-journal"):
            Path(f"{path}{suffix}").unlink(missing_ok=True)

    @staticmethod
    def _move_file(source: Path, destination: Path) -> bool:
        if not source.is_file():
            return False
        if destination.exists():
            logger.warning(
                "Account migration kept legacy source because destination exists: %s -> %s",
                source,
                destination,
            )
            return False
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))
        logger.info("Migrated account data: %s -> %s", source, destination)
        return True

    @staticmethod
    def _copy_file(source: Path, destination: Path) -> bool:
        if not source.is_file():
            return False
        if destination.exists():
            return destination.read_bytes() == source.read_bytes()
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        logger.info("Migrated shared account data: %s -> %s", source, destination)
        return True

    def _merge_directory(self, source: Path, destination: Path) -> None:
        if not source.is_dir():
            return
        if not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(destination))
            logger.info("Migrated account data: %s -> %s", source, destination)
            return
        for child in list(source.iterdir()):
            target = destination / child.name
            if child.is_dir():
                self._merge_directory(child, target)
            else:
                self._move_file(child, target)
        try:
            source.rmdir()
        except OSError:
            logger.warning("Account migration retained conflicting directory: %s", source)
