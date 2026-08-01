"""Canonical paths for authenticated Telegram accounts."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

def normalize_telegram_user_id(value: object) -> str:
    """Return a positive Telegram user id as its canonical decimal string."""
    try:
        account_id = str(int(value))
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid Telegram user id") from exc
    if account_id == "0" or account_id.startswith("-"):
        raise ValueError("Invalid Telegram user id")
    if int(account_id) > 9_223_372_036_854_775_807:
        raise ValueError("Invalid Telegram user id")
    return account_id


def is_telegram_user_id(value: str) -> bool:
    try:
        normalize_telegram_user_id(value)
        return value == str(int(value))
    except (TypeError, ValueError):
        return False


@dataclass(frozen=True)
class AccountPaths:
    account_id: str
    config_file: Path
    data_dir: Path

    @property
    def session_name(self) -> Path:
        return self.data_dir / "telegram"

    @property
    def queue_db(self) -> Path:
        return self.data_dir / "forward_queue.db"

    @property
    def stats_db(self) -> Path:
        return self.data_dir / "stats.db"

    @property
    def exports_db(self) -> Path:
        return self.data_dir / "exports.db"

    @property
    def message_db_dir(self) -> Path:
        return self.data_dir / "db"

    @property
    def export_dir(self) -> Path:
        return self.data_dir / "exports"

    @property
    def avatar(self) -> Path:
        return self.data_dir / "avatar.jpg"


class AccountPathRegistry:
    """Resolve canonical paths and migrate data from pre-isolation layouts."""

    def __init__(
        self,
        *,
        config_dir: str | Path = "config",
        data_dir: str | Path = "data",
    ):
        self.config_dir = Path(config_dir)
        self.data_dir = Path(data_dir)

    def for_account(self, account_id: str | int) -> AccountPaths:
        normalized = normalize_telegram_user_id(account_id)
        return AccountPaths(
            account_id=normalized,
            config_file=self.config_dir / f"{normalized}.yaml",
            data_dir=self.data_dir / normalized,
        )

    def adopt_session(self, session_name: str | Path, account_id: str | int) -> bool:
        """Move a disconnected temporary Telethon session into its final account."""
        paths = self.for_account(account_id)
        moved = self._move_file(
            Path(f"{session_name}.session"),
            Path(f"{paths.session_name}.session"),
        )
        self._move_file(
            Path(f"{session_name}.session-journal"),
            Path(f"{paths.session_name}.session-journal"),
        )
        return moved

    def remove_account_data(self, account_id: str | int) -> None:
        """Remove a finalized account's isolated data and configuration."""
        paths = self.for_account(account_id)
        paths.config_file.unlink(missing_ok=True)
        if paths.data_dir.is_dir():
            shutil.rmtree(paths.data_dir)
