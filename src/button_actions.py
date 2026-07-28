"""Rules for interacting with callback buttons in Telegram messages."""

import asyncio
import re
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from telethon.tl.types import KeyboardButtonCallback


@dataclass
class ButtonActionRule:
    """A rule that clicks one matching callback button in an incoming message."""

    name: str
    enabled: bool = False
    source_chats: list[Any] = field(default_factory=list)
    button_texts: list[str] = field(default_factory=list)
    match_mode: str = "exact"
    delay: float = 0.0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ButtonActionRule":
        try:
            delay = max(0.0, min(float(data.get("delay", 0.0) or 0.0), 30.0))
        except (TypeError, ValueError):
            delay = 0.0
        return cls(
            name=str(data.get("name", "Button action")),
            enabled=bool(data.get("enabled", False)),
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
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "enabled": self.enabled,
            "source_chats": self.source_chats,
            "button_texts": self.button_texts,
            "match_mode": self.match_mode,
            "delay": self.delay,
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
    """Apply button rules to incoming messages on a Telegram user session."""

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

    def find_match(self, event: Any) -> tuple[ButtonActionRule, str, bytes] | None:
        message = getattr(event, "message", None)
        if message is None:
            return None
        for rule in self.rules:
            if not rule.enabled or not chat_matches(event, rule.source_chats):
                continue
            for button_text, button_data in iter_callback_buttons(message):
                if any(
                    button_text_matches(button_text, text, rule.match_mode)
                    for text in rule.button_texts
                ):
                    return rule, button_text, button_data
        return None

    async def handle(self, event: Any) -> tuple[str, str] | None:
        """Click the first matching callback button and return rule/button text."""
        message = getattr(event, "message", None)
        key = (getattr(event, "chat_id", None), getattr(message, "id", None))
        if message is None or self._already_processed(key) or key in self._processing:
            return None

        match = self.find_match(event)
        if match is None:
            return None

        rule, button_text, button_data = match
        self._processing.add(key)
        try:
            if rule.delay:
                await asyncio.sleep(rule.delay)
            await message.click(data=button_data)
            self._mark_processed(key)
            return rule.name, button_text
        finally:
            self._processing.discard(key)
