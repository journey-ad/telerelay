"""Telegram chat directory used by rules and exports."""

from __future__ import annotations

import json
import os
import tempfile
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from telethon import errors, utils
from telethon.tl import types

from backend.logger import get_logger
from backend.telegram_accounts import TelegramAccountError

logger = get_logger()

ChatKind = Literal["bot", "private", "group", "supergroup", "channel"]


class TelegramChatError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _chat_record(entity: Any, *, include_private: bool = False) -> TelegramChat | None:
    if isinstance(entity, types.User):
        if not include_private and not bool(getattr(entity, "bot", False)):
            return None
    elif not isinstance(entity, (types.Chat, types.Channel)):
        return None
    return TelegramChat(
        id=int(utils.get_peer_id(entity)),
        title=_display_name(entity),
        kind=_chat_kind(entity),
        username=getattr(entity, "username", None),
    )


@dataclass(frozen=True)
class TelegramChat:
    id: int
    title: str
    kind: ChatKind
    username: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _display_name(entity: Any) -> str:
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
    return name or str(getattr(entity, "id", ""))


def _chat_kind(entity: Any) -> ChatKind:
    if isinstance(entity, types.User):
        return "bot" if getattr(entity, "bot", False) else "private"
    if isinstance(entity, types.Chat):
        return "group"
    if isinstance(entity, types.Channel) and getattr(entity, "megagroup", False):
        return "supergroup"
    return "channel"


class TelegramChatService:
    MAX_KNOWN_CHATS = 1000

    def __init__(self, bot_manager: Any, account_store: Any):
        self.bot_manager = bot_manager
        self.account_store = account_store

    def list_chats(self, account_id: str, timeout: float = 90) -> list[TelegramChat]:
        try:
            public = self.account_store.get_public(account_id)
        except TelegramAccountError as exc:
            raise TelegramChatError(exc.code, str(exc)) from exc
        if public.get("kind") == "bot":
            return self._known_chats(account_id)
        return self._result(account_id, self._list_chats, timeout=timeout)

    def record_chat(self, account_id: str, entity: Any) -> None:
        """Persist one chat seen by a bot runtime so pickers can list it."""
        chat = _chat_record(entity, include_private=True)
        if chat is None:
            logger.debug(
                "跳过不可记录的会话实体 (account_id=%s, entity=%s)",
                account_id,
                type(entity).__name__,
            )
            return
        path = self._known_chats_path(account_id)
        known = self._load_known_chats(path)
        known[str(chat.id)] = chat.to_dict()
        if len(known) > self.MAX_KNOWN_CHATS:
            for stale in list(known)[: len(known) - self.MAX_KNOWN_CHATS]:
                known.pop(stale, None)
        self._save_known_chats(path, known)
        logger.debug(
            "已记录已知会话 (account_id=%s, chat_id=%s, title=%s, total=%d, path=%s)",
            account_id,
            chat.id,
            chat.title,
            len(known),
            path,
        )

    def _known_chats_path(self, account_id: str) -> Path:
        return Path(f"{self.account_store.session_name(account_id)}.session").parent / "known_chats.json"

    def _known_chats(self, account_id: str) -> list[TelegramChat]:
        known = self._load_known_chats(self._known_chats_path(account_id))
        chats = []
        for item in known.values():
            try:
                chats.append(TelegramChat(**item))
            except (TypeError, ValueError):
                continue
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
        chat = self._result(account_id, self._get_chat, int(chat_id), timeout=timeout)
        if chat is None:
            raise TelegramChatError("chat_not_found", "Telegram chat does not exist")
        return chat

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

    async def _list_chats(self, client) -> list[TelegramChat]:
        chats = []
        async for dialog in client.iter_dialogs():
            chat = _chat_record(dialog.entity)
            if chat:
                chats.append(chat)
        return sorted(chats, key=lambda item: (item.title.casefold(), item.id))

    async def _get_chat(self, client, chat_id: int) -> TelegramChat | None:
        try:
            entity = await client.get_entity(chat_id)
        except (errors.RPCError, TypeError, ValueError):
            return None
        return _chat_record(entity)
