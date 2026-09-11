"""Last known chat names, kept for peers Telegram scrubs to an id."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from collections.abc import Iterable
from pathlib import Path
from typing import Any

# Names kept per account. Telegram listings are longer, so entries are trimmed
# by least recent use and the names touched most keep their place.
MAX_NAMES = 2000


class ChatNameCache:
    """Remember the last name Telegram reported for each peer.

    Deleted accounts arrive as ``UserEmpty`` and banned chats stop resolving, so
    a listing can only report their id. Cached names let those peers keep the
    name they had before.
    """

    def __init__(self, account_store: Any):
        self.account_store = account_store
        self._lock = threading.Lock()

    def merge(self, account_id: str, entries: Iterable[tuple[int, str]]) -> dict[int, str]:
        """Store the names seen now and return every name known for the account."""
        with self._lock:
            names = self._load(account_id)
            changed = False
            for chat_id, title in entries:
                name = title.strip()
                if not name:
                    continue
                key = str(chat_id)
                if names.get(key) == name:
                    continue
                names.pop(key, None)
                names[key] = name
                changed = True
            overflow = len(names) - MAX_NAMES
            if overflow > 0:
                for stale in list(names)[:overflow]:
                    names.pop(stale, None)
                changed = True
            if changed:
                self._save(account_id, names)
            return {int(key): name for key, name in names.items()}

    def _path(self, account_id: str) -> Path:
        session = Path(f"{self.account_store.session_name(account_id)}.session")
        return session.parent / "chat_names.json"

    def _load(self, account_id: str) -> dict[str, str]:
        try:
            payload = json.loads(self._path(account_id).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(payload, dict):
            return {}
        names = {}
        for key, value in payload.items():
            if not isinstance(value, str) or not value:
                continue
            try:
                names[str(int(key))] = value
            except (TypeError, ValueError):
                continue
        return names

    def _save(self, account_id: str, names: dict[str, str]) -> None:
        path = self._path(account_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=".chat-names-",
            suffix=".tmp",
            dir=path.parent,
        )
        try:
            with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
                json.dump(names, handle, ensure_ascii=False)
                handle.write("\n")
            os.replace(temporary_name, path)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)
