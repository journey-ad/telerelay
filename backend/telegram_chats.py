"""Telegram chat directory used by rules and exports."""

from __future__ import annotations

import json
import os
import tempfile
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Literal, cast

from telethon import errors, utils
from telethon.tl import types

from backend.chat_names import ChatNameCache, ChatPeer
from backend.logger import get_logger
from backend.telegram_accounts import TelegramAccountError

logger = get_logger()

ChatKind = Literal["bot", "private", "group", "supergroup", "channel"]
CHAT_KINDS: tuple[ChatKind, ...] = ("bot", "private", "group", "supergroup", "channel")
ChatInvalidReason = Literal["deleted", "deactivated", "left", "blocked", "readonly", "missing"]

# Resolution failures that mean the chat is gone rather than temporarily
# unreachable, so a rate limit or connection error is not in this list.
# Telethon raises ValueError when Telegram does not know the id at all.
PERMANENT_RESOLVE_ERRORS = (
    errors.ChannelPrivateError,
    errors.ChannelInvalidError,
    errors.PeerIdInvalidError,
    ValueError,
)

# Referenced chats resolved per chat-directory request.
MAX_RESOLVED_CHATS = 50


def _resolve_reason(exc: Exception) -> ChatInvalidReason:
    return "missing" if isinstance(exc, ValueError) else "blocked"


class TelegramChatError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _chat_validity(entity: Any) -> ChatInvalidReason | None:
    """Report a chat that Telegram itself already marks as unusable.

    Reads only the flags carried by the dialog entity, so listing chats stays a
    single request. ``default_banned_rights`` describes plain members, so it is
    ignored for administrators of announcement-style channels.
    """
    if getattr(entity, "deleted", False):
        return "deleted"
    if getattr(entity, "deactivated", False):
        return "deactivated"
    if getattr(entity, "left", False):
        return "left"

    restrictions = [getattr(entity, "banned_rights", None)]
    if getattr(entity, "admin_rights", None) is None:
        restrictions.append(getattr(entity, "default_banned_rights", None))
    for rights in restrictions:
        if rights is None:
            continue
        if getattr(rights, "view_messages", False):
            return "blocked"
        if getattr(rights, "send_messages", False):
            return "readonly"

    return None


def _peer_id(entity: Any) -> int:
    """The peer id of an entity, including one Telegram scrubbed to its id."""
    if isinstance(entity, types.UserEmpty):
        return int(entity.id)
    return int(utils.get_peer_id(entity))


def _known_kind(known: ChatPeer | None) -> ChatKind | None:
    """The kind seen for a peer while Telegram still reported it."""
    if known and known.kind in CHAT_KINDS:
        return cast(ChatKind, known.kind)
    return None


def _peer_kind(chat_id: int) -> ChatKind:
    """The kind a peer id alone implies once Telegram stops resolving it.

    Users sit in the positive range, basic groups in the small negative range,
    and channels and supergroups behind the -100 prefix. The prefix does not
    tell a broadcast channel from a supergroup.
    """
    if chat_id >= 0:
        return "private"
    return "channel" if str(chat_id).startswith("-100") else "group"


def _chat_record(
    entity: Any, *, include_private: bool = False, known: ChatPeer | None = None
) -> TelegramChat | None:
    # Telegram replaces channels and groups the account was banned from with a
    # "forbidden" variant, and scrubs deleted or banned accounts to an id-only
    # user. Both are kept in the directory, marked, instead of being dropped.
    if isinstance(entity, (types.ChannelForbidden, types.ChatForbidden)):
        return TelegramChat(
            id=_peer_id(entity),
            title=_display_name(entity),
            kind=_chat_kind(entity),
            invalid_reason="blocked",
        )
    if isinstance(entity, types.UserEmpty):
        # An id-only peer carries neither its name nor its kind, so a scrubbed
        # bot would otherwise be listed as a private user.
        return TelegramChat(
            id=_peer_id(entity),
            title=known.name if known else "",
            kind=_known_kind(known) or "private",
            invalid_reason="deleted",
        )
    if isinstance(entity, types.User):
        if not include_private and not bool(getattr(entity, "bot", False)):
            return None
    elif not isinstance(entity, (types.Chat, types.Channel)):
        return None
    return TelegramChat(
        id=_peer_id(entity),
        title=_display_name(entity),
        kind=_chat_kind(entity),
        username=getattr(entity, "username", None),
        invalid_reason=_chat_validity(entity),
    )


@dataclass(frozen=True)
class TelegramChat:
    id: int
    title: str
    kind: ChatKind
    username: str | None = None
    invalid_reason: ChatInvalidReason | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _record_from_dict(item: Any) -> TelegramChat | None:
    if not isinstance(item, dict):
        return None
    try:
        return TelegramChat(**item)
    except (TypeError, ValueError):
        return None


def _display_name(entity: Any) -> str:
    """The name Telegram reported, empty when the peer carries none."""
    title = getattr(entity, "title", None)
    if title:
        return str(title)
    name = " ".join(
        str(part)
        for part in (
            getattr(entity, "first_name", None),
            getattr(entity, "last_name", None),
        )
        if part
    )
    username = getattr(entity, "username", None)
    return name or (f"@{username}" if username else "")


def _chat_kind(entity: Any) -> ChatKind:
    if isinstance(entity, types.User):
        return "bot" if getattr(entity, "bot", False) else "private"
    if isinstance(entity, (types.Chat, types.ChatForbidden)):
        return "group"
    return "supergroup" if getattr(entity, "megagroup", False) else "channel"


class TelegramChatService:
    MAX_KNOWN_CHATS = 1000

    def __init__(self, bot_manager: Any, account_store: Any, names: ChatNameCache | None = None):
        self.bot_manager = bot_manager
        self.account_store = account_store
        self.names = names or ChatNameCache(account_store)

    def list_chats(
        self,
        account_id: str,
        timeout: float = 90,
        include: tuple[int, ...] = (),
    ) -> list[TelegramChat]:
        try:
            public = self.account_store.get_public(account_id)
        except TelegramAccountError as exc:
            raise TelegramChatError(exc.code, str(exc)) from exc
        if public.get("kind") == "bot":
            # A bot gets no dialog list, so its picker reads the stored chats,
            # refreshed whenever the runtime sees the chat again.
            return self._known_chats(account_id)
        known = self.names.load(account_id)
        chats = self._result(account_id, self._list_chats, known, include, timeout=timeout)
        return self._named(account_id, chats)

    def record_chat(self, account_id: str, entity: Any) -> None:
        """Persist one chat seen by a bot runtime so pickers can list it."""
        chat = _chat_record(entity, include_private=True)
        if chat is None:
            # skip unrecordable entities
            return
        path = self._known_chats_path(account_id)
        known = self._load_known_chats(path)
        if isinstance(entity, types.UserEmpty):
            # Telegram only reports the id; keep the name already recorded.
            stored = _record_from_dict(known.get(str(chat.id)))
            if stored is not None:
                chat = replace(stored, invalid_reason="deleted")
        if known.get(str(chat.id)) == chat.to_dict():
            return
        known[str(chat.id)] = chat.to_dict()
        if len(known) > self.MAX_KNOWN_CHATS:
            for stale in list(known)[: len(known) - self.MAX_KNOWN_CHATS]:
                known.pop(stale, None)
        self._save_known_chats(path, known)

    def _known_chats_path(self, account_id: str) -> Path:
        return Path(f"{self.account_store.session_name(account_id)}.session").parent / "known_chats.json"

    def _known_chats(self, account_id: str) -> list[TelegramChat]:
        known = self._load_known_chats(self._known_chats_path(account_id))
        chats = [chat for chat in map(_record_from_dict, known.values()) if chat]
        return sorted(chats, key=lambda chat: (chat.title.casefold(), chat.id))

    @staticmethod
    def _load_known_chats(path: Path) -> dict[str, dict[str, Any]]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(payload, dict):
            return {}
        return {
            str(key): value
            for key, value in payload.items()
            if isinstance(value, dict)
        }

    @staticmethod
    def _save_known_chats(path: Path, known: dict[str, dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=".known-chats-",
            suffix=".tmp",
            dir=path.parent,
        )
        try:
            with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
                json.dump(known, handle, ensure_ascii=False)
                handle.write("\n")
            os.replace(temporary_name, path)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)

    def get_chat(
        self, account_id: str, chat_id: int, timeout: float = 30
    ) -> TelegramChat:
        known = self.names.load(account_id)
        chat = self._result(account_id, self._get_chat, known, int(chat_id), timeout=timeout)
        if chat is None:
            raise TelegramChatError("chat_not_found", "Telegram chat does not exist")
        return self._named(account_id, [chat])[0]

    def _named(self, account_id: str, chats: list[TelegramChat]) -> list[TelegramChat]:
        """Give peers Telegram no longer names the name last seen for them.

        Names and kinds reported by this listing refresh the cache, so a chat
        that is deleted or banned afterwards keeps what it had while it was
        usable.
        """
        peers = self.names.merge(
            account_id, ((chat.id, chat.title, chat.kind) for chat in chats)
        )
        restored = [replace(chat, title=chat.title or peers[chat.id].name) for chat in chats]
        return sorted(restored, key=lambda chat: (chat.title.casefold(), chat.id))

    def _result(self, account_id: str, callback, *args, timeout: float):
        try:
            self.account_store.get_public(account_id)
            runtime = self.bot_manager.get_runtime(account_id)
            return runtime.submit_telegram(callback, *args).result(timeout=timeout)
        except TelegramAccountError as exc:
            raise TelegramChatError(exc.code, str(exc)) from exc
        except FutureTimeoutError as exc:
            raise TelegramChatError(
                "telegram_timeout", "Telegram chat request timed out"
            ) from exc
        except RuntimeError as exc:
            raise TelegramChatError("telegram_not_connected", str(exc)) from exc

    async def _list_chats(
        self, client, known: dict[int, ChatPeer], include: tuple[int, ...] = ()
    ) -> list[TelegramChat]:
        chats = []
        async for dialog in client.iter_dialogs():
            entity = dialog.entity
            chat = _chat_record(entity, known=known.get(_peer_id(entity)))
            if chat:
                chats.append(chat)
        return await self._with_referenced_chats(client, chats, include, known)

    async def _with_referenced_chats(
        self,
        client,
        chats: list[TelegramChat],
        include: tuple[int, ...],
        known: dict[int, ChatPeer],
    ) -> list[TelegramChat]:
        """Add referenced chats that Telegram no longer lists.

        A banned or deleted chat often disappears from the dialog list (or is
        scrubbed), so rules and exports referencing it would otherwise show as
        merely "unknown" instead of invalid.
        """
        listed = {chat.id for chat in chats}
        missing = [chat_id for chat_id in include if chat_id not in listed]
        resolved = []
        for chat_id in missing[:MAX_RESOLVED_CHATS]:
            try:
                entity = await client.get_entity(chat_id)
            except PERMANENT_RESOLVE_ERRORS as exc:
                stored = known.get(chat_id)
                resolved.append(
                    TelegramChat(
                        id=chat_id,
                        title=stored.name if stored else "",
                        kind=_known_kind(stored) or _peer_kind(chat_id),
                        invalid_reason=_resolve_reason(exc),
                    )
                )
                continue
            except errors.RPCError:
                continue
            record = _chat_record(entity, include_private=True, known=known.get(chat_id))
            if record:
                resolved.append(record)
        return sorted([*chats, *resolved], key=lambda item: (item.title.casefold(), item.id))

    async def _get_chat(
        self, client, known: dict[int, ChatPeer], chat_id: int
    ) -> TelegramChat | None:
        try:
            entity = await client.get_entity(chat_id)
        except (errors.RPCError, TypeError, ValueError):
            return None
        return _chat_record(entity, known=known.get(int(chat_id)))
