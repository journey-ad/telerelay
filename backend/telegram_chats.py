"""Telegram chat directory used by rules and exports."""

from __future__ import annotations

from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import asdict, dataclass
from typing import Any, Literal

from telethon import errors, utils
from telethon.tl import types

from backend.telegram_accounts import TelegramAccountError

ChatKind = Literal["bot", "group", "supergroup", "channel"]


class TelegramChatError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


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
        return "bot"
    if isinstance(entity, types.Chat):
        return "group"
    if isinstance(entity, types.Channel) and getattr(entity, "megagroup", False):
        return "supergroup"
    return "channel"


def _is_supported_chat(entity: Any) -> bool:
    return isinstance(entity, (types.Chat, types.Channel)) or (
        isinstance(entity, types.User) and bool(getattr(entity, "bot", False))
    )


class TelegramChatService:
    def __init__(self, bot_manager: Any, account_store: Any):
        self.bot_manager = bot_manager
        self.account_store = account_store

    def list_chats(self, account_id: str, timeout: float = 90) -> list[TelegramChat]:
        return self._result(account_id, self._list_chats, timeout=timeout)

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
            chat = self._chat(dialog.entity)
            if chat:
                chats.append(chat)
        return sorted(chats, key=lambda item: (item.title.casefold(), item.id))

    async def _get_chat(self, client, chat_id: int) -> TelegramChat | None:
        try:
            entity = await client.get_entity(chat_id)
        except (errors.RPCError, TypeError, ValueError):
            return None
        return self._chat(entity)

    @staticmethod
    def _chat(entity: Any) -> TelegramChat | None:
        if not _is_supported_chat(entity):
            return None
        return TelegramChat(
            id=int(utils.get_peer_id(entity)),
            title=_display_name(entity),
            kind=_chat_kind(entity),
            username=getattr(entity, "username", None),
        )
