"""Last known chat names, kinds and usernames, kept for peers Telegram scrubs."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Peers kept per account. Telegram listings are longer, so entries are trimmed
# by least recent use and the peers touched most keep their place.
MAX_NAMES = 2000

# Bumped whenever the stored shape changes, so an older file is dropped and
# rebuilt instead of being migrated.
CACHE_VERSION = 3


@dataclass(frozen=True)
class ChatPeer:
    """What Telegram last reported for one peer."""

    name: str = ""
    kind: str = ""
    username: str = ""
    invalid_reason: str = ""
    # Metadata rather than identity, so it stays out of equality checks.
    seen_at: str = field(default="", compare=False)


class ChatNameCache:
    """Remember the last name and kind Telegram reported for each peer.

    Deleted accounts arrive as ``UserEmpty`` and banned chats stop resolving, so
    a listing can only report their id. Cached peers let those keep the name,
    the username and the kind they had while Telegram still reported them — the
    username being what tells a scrubbed bot apart from a private user.
    """

    def __init__(self, account_store: Any):
        self.account_store = account_store
        self._lock = threading.Lock()

    def load(self, account_id: str) -> dict[int, ChatPeer]:
        """Read the cached peers without recording anything."""
        with self._lock:
            return self._read(account_id)

    def merge(
        self, account_id: str, entries: Iterable[tuple[int, ChatPeer]]
    ) -> dict[int, ChatPeer]:
        """Store the peers seen now and return every peer known for the account."""
        seen_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._lock:
            peers = self._read(account_id)
            seen = False
            for chat_id, entry in entries:
                stored = peers.get(chat_id)
                if not entry.name and stored is None:
                    # A peer Telegram names nowhere carries no kind of its own,
                    # so caching it would only store a guess.
                    continue
                # A scrubbed peer reports no name, which must not erase the one
                # already known; every sighting refreshes the timestamp.
                peers.pop(chat_id, None)
                peers[chat_id] = replace(
                    entry, name=entry.name or stored.name, seen_at=seen_at
                )
                seen = True
            overflow = len(peers) - MAX_NAMES
            if overflow > 0:
                for stale in sorted(peers, key=lambda chat_id: peers[chat_id].seen_at)[
                    :overflow
                ]:
                    peers.pop(stale, None)
                seen = True
            if seen:
                self._save(account_id, peers)
            return peers

    def _path(self, account_id: str) -> Path:
        session = Path(f"{self.account_store.session_name(account_id)}.session")
        return session.parent / "chat_names.json"

    def _read(self, account_id: str) -> dict[int, ChatPeer]:
        try:
            payload = json.loads(self._path(account_id).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(payload, dict) or payload.get("version") != CACHE_VERSION:
            return {}
        stored = payload.get("peers")
        if not isinstance(stored, dict):
            return {}
        peers: dict[int, ChatPeer] = {}
        for key, value in stored.items():
            if not isinstance(value, dict):
                continue
            try:
                chat_id = int(key)
            except (TypeError, ValueError):
                continue
            peers[chat_id] = ChatPeer(
                name=str(value.get("name") or ""),
                kind=str(value.get("kind") or ""),
                username=str(value.get("username") or ""),
                invalid_reason=str(value.get("invalid_reason") or ""),
                seen_at=str(value.get("seen_at") or ""),
            )
        return peers

    def _save(self, account_id: str, peers: dict[int, ChatPeer]) -> None:
        path = self._path(account_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=".chat-names-",
            suffix=".tmp",
            dir=path.parent,
        )
        try:
            with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "version": CACHE_VERSION,
                        "peers": {
                            str(chat_id): asdict(peer) for chat_id, peer in peers.items()
                        },
                    },
                    handle,
                    ensure_ascii=False,
                )
                handle.write("\n")
            os.replace(temporary_name, path)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)
