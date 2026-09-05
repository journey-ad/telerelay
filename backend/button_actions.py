"""Rules for interacting with buttons and Bot start links in Telegram messages."""

import asyncio
import re
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, urlparse

from telethon.helpers import add_surrogate, del_surrogate
from telethon.tl.functions.messages import StartBotRequest
from telethon.tl.types import (
    KeyboardButtonCallback,
    KeyboardButtonUrl,
    MessageEntityTextUrl,
    MessageEntityUrl,
)


_BOT_USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{1,28}bot$", re.IGNORECASE)
_START_PARAM_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_TELEGRAM_LINK_RE = re.compile(
    r"(?:(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me|telegram\.dog)/"
    r"[A-Za-z][A-Za-z0-9_]{1,28}bot\?[^\s<>]*)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class BotStartLink:
    username: str
    start_param: str


@dataclass(frozen=True)
class MessageAction:
    label: str
    callback_data: bytes | None = None
    bot_start: BotStartLink | None = None


@dataclass
class ButtonActionRule:
    """A rule that runs matching message actions in an incoming message."""

    name: str
    enabled: bool = False
    action_type: str = "callback"
    source_chats: list[Any] = field(default_factory=list)
    button_texts: list[str] = field(default_factory=list)
    match_mode: str = "exact"
    delay: float = 0.0
    click_all_matches: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ButtonActionRule":
        try:
            delay = max(0.0, min(float(data.get("delay", 0.0) or 0.0), 30.0))
        except (TypeError, ValueError):
            delay = 0.0
        return cls(
            name=str(data.get("name", "Button action")),
            enabled=bool(data.get("enabled", False)),
            action_type=(
                str(data.get("action_type", "callback")).lower()
                if str(data.get("action_type", "callback")).lower()
                in {"callback", "bot_start"}
                else "callback"
            ),
            source_chats=list(data.get("source_chats") or []),
            button_texts=[
                str(item)
                for item in (data.get("button_texts") or [])
                if str(item).strip()
            ],
            match_mode=str(data.get("match_mode", "exact")).lower()
            if str(data.get("match_mode", "exact")).lower()
            in {"exact", "contains", "regex"}
            else "exact",
            delay=delay,
            click_all_matches=bool(data.get("click_all_matches", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "enabled": self.enabled,
            "action_type": self.action_type,
            "source_chats": self.source_chats,
            "button_texts": self.button_texts,
            "match_mode": self.match_mode,
            "delay": self.delay,
            "click_all_matches": self.click_all_matches,
        }


def load_button_action_rules(config_data: dict[str, Any]) -> list[ButtonActionRule]:
    """Load independent message-button rules from the YAML configuration."""
    return [
        ButtonActionRule.from_dict(item)
        for item in (config_data.get("button_action_rules") or [])
        if isinstance(item, dict)
    ]


def save_button_action_rules(rules: Iterable[ButtonActionRule]) -> dict[str, Any]:
    return {"button_action_rules": [rule.to_dict() for rule in rules]}


def iter_callback_buttons(message: Any) -> Iterable[tuple[str, bytes]]:
    """Yield text/data pairs for callback buttons attached to a message."""
    markup = getattr(message, "reply_markup", None)
    for row in getattr(markup, "rows", ()) or ():
        for button in getattr(row, "buttons", ()) or ():
            if isinstance(button, KeyboardButtonCallback):
                yield button.text or "", button.data


def parse_bot_start_link(url: str) -> BotStartLink | None:
    """Parse a Telegram Bot deep link without accepting arbitrary URLs."""
    value = str(url or "").strip().rstrip(".,;:!?)]}\"'")
    if not value:
        return None
    if value.casefold().startswith("tg://"):
        parsed = urlparse(value)
        if parsed.netloc.casefold() != "resolve":
            return None
        query = parse_qs(parsed.query, keep_blank_values=True)
        username = (query.get("domain") or [""])[0]
    else:
        if "://" not in value:
            value = f"https://{value}"
        parsed = urlparse(value)
        if parsed.scheme.casefold() not in {"http", "https"}:
            return None
        host = (parsed.hostname or "").casefold()
        if host.startswith("www."):
            host = host[4:]
        if host not in {"t.me", "telegram.me", "telegram.dog"}:
            return None
        username = parsed.path.strip("/")
        if "/" in username:
            return None
        query = parse_qs(parsed.query, keep_blank_values=True)

    start_param = (query.get("start") or [""])[0]
    if not _BOT_USERNAME_RE.fullmatch(username) or not _START_PARAM_RE.fullmatch(
        start_param
    ):
        return None
    return BotStartLink(username=username, start_param=start_param)


def _entity_text(message_text: str, entity: Any) -> str:
    """Slice Telegram's UTF-16 entity offsets correctly."""
    surrogate_text = add_surrogate(message_text)
    value = surrogate_text[entity.offset : entity.offset + entity.length]
    return del_surrogate(value)


def iter_bot_start_links(message: Any) -> Iterable[tuple[str, BotStartLink]]:
    """Yield visible labels and valid Bot start links from markup and text."""
    seen: set[tuple[str, str]] = set()

    markup = getattr(message, "reply_markup", None)
    for row in getattr(markup, "rows", ()) or ():
        for button in getattr(row, "buttons", ()) or ():
            if not isinstance(button, KeyboardButtonUrl):
                continue
            link = parse_bot_start_link(button.url)
            if link and (link.username.casefold(), link.start_param) not in seen:
                seen.add((link.username.casefold(), link.start_param))
                yield button.text or button.url, link

    text = getattr(message, "raw_text", None) or getattr(message, "text", None) or ""
    for entity in getattr(message, "entities", ()) or ():
        if isinstance(entity, MessageEntityTextUrl):
            url = entity.url
        elif isinstance(entity, MessageEntityUrl):
            url = _entity_text(text, entity)
        else:
            continue
        link = parse_bot_start_link(url)
        key = (link.username.casefold(), link.start_param) if link else None
        if link and key not in seen:
            seen.add(key)
            yield _entity_text(text, entity) or url, link

    # Some synthetic/imported messages do not carry Telegram entities.
    for match in _TELEGRAM_LINK_RE.finditer(text):
        url = match.group(0)
        link = parse_bot_start_link(url)
        key = (link.username.casefold(), link.start_param) if link else None
        if link and key not in seen:
            seen.add(key)
            yield url, link


def iter_message_actions(
    message: Any, action_type: str = "callback"
) -> Iterable[MessageAction]:
    if action_type == "bot_start":
        for label, link in iter_bot_start_links(message):
            yield MessageAction(label=label, bot_start=link)
        return
    for button_text, button_data in iter_callback_buttons(message):
        yield MessageAction(label=button_text, callback_data=button_data)


def action_matches(action: MessageAction, configured_text: str, match_mode: str) -> bool:
    candidates = [action.label]
    if action.bot_start is not None:
        username = action.bot_start.username
        start_param = action.bot_start.start_param
        candidates.extend(
            [
                username,
                f"@{username}",
                f"https://t.me/{username}?start={start_param}",
                f"start={start_param}",
                start_param,
            ]
        )
    return any(
        button_text_matches(candidate, configured_text, match_mode)
        for candidate in candidates
    )


def button_text_matches(
    button_text: str, configured_text: str, match_mode: str
) -> bool:
    if match_mode == "contains":
        return configured_text in button_text
    if match_mode == "regex":
        try:
            return re.search(configured_text, button_text) is not None
        except re.error:
            return False
    return button_text == configured_text


def chat_matches(event: Any, configured_chats: Iterable[Any]) -> bool:
    """Match numeric IDs and @usernames without requiring extra API calls."""
    chat_id = getattr(event, "chat_id", None)
    chat = getattr(event, "chat", None) or getattr(
        getattr(event, "message", None), "chat", None
    )
    username = (getattr(chat, "username", None) or "").lstrip("@").casefold()

    for configured in configured_chats:
        if isinstance(configured, int) or (
            isinstance(configured, str) and configured.lstrip("-").isdigit()
        ):
            try:
                if int(configured) == chat_id:
                    return True
            except (TypeError, ValueError):
                pass
        else:
            value = str(configured).strip().lstrip("@").casefold()
            if value and value == username:
                return True
    return False


class ButtonActionEngine:
    """Apply interaction rules to incoming messages on a Telegram user session."""

    def __init__(self, rules: Iterable[ButtonActionRule], max_processed: int = 5000):
        self.rules = list(rules)
        self._processed = set()
        self._processing = set()
        self._processed_order = deque(maxlen=max_processed)

    def _already_processed(self, key: tuple[Any, Any]) -> bool:
        return key in self._processed

    def _mark_processed(self, key: tuple[Any, Any]) -> None:
        if key in self._processed:
            return
        if len(self._processed_order) == self._processed_order.maxlen:
            self._processed.discard(self._processed_order[0])
        self._processed_order.append(key)
        self._processed.add(key)

    def find_match(self, event: Any) -> tuple[ButtonActionRule, MessageAction] | None:
        """Return the first match for callers that only need one button."""
        match = self.find_matches(event)
        if match is None:
            return None
        rule, actions = match
        return rule, actions[0]

    def find_matches(
        self, event: Any
    ) -> tuple[ButtonActionRule, list[MessageAction]] | None:
        """Return message actions selected by the first matching enabled rule."""
        message = getattr(event, "message", None)
        if message is None:
            return None
        for rule in self.rules:
            if not rule.enabled or not chat_matches(event, rule.source_chats):
                continue
            matches: list[MessageAction] = []
            for action in iter_message_actions(message, rule.action_type):
                if any(
                    action_matches(action, text, rule.match_mode)
                    for text in rule.button_texts
                ):
                    matches.append(action)
                    if not rule.click_all_matches:
                        break
            if matches:
                return rule, matches
        return None

    async def handle(self, event: Any) -> tuple[str, list[str]] | None:
        """Run callback clicks or Telegram Bot start links selected by a rule."""
        message = getattr(event, "message", None)
        key = (getattr(event, "chat_id", None), getattr(message, "id", None))
        if message is None or self._already_processed(key) or key in self._processing:
            return None

        match = self.find_matches(event)
        if match is None:
            return None

        rule, actions = match
        clicked_texts: list[str] = []
        self._processing.add(key)
        try:
            if rule.delay:
                await asyncio.sleep(rule.delay)
            for action in actions:
                if action.callback_data is not None:
                    await message.click(data=action.callback_data)
                elif action.bot_start is not None:
                    client = getattr(event, "client", None)
                    if client is None:
                        raise RuntimeError("Telegram client is unavailable for Bot start link")
                    await client(
                        StartBotRequest(
                            bot=action.bot_start.username,
                            peer=action.bot_start.username,
                            start_param=action.bot_start.start_param,
                        )
                    )
                clicked_texts.append(action.label)
            return rule.name, clicked_texts
        finally:
            if clicked_texts:
                self._mark_processed(key)
            self._processing.discard(key)
