import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from telethon.tl.types import (
    KeyboardButtonCallback,
    KeyboardButtonRow,
    KeyboardButtonUrl,
    ReplyInlineMarkup,
)

from src.button_actions import (
    ButtonActionEngine,
    ButtonActionRule,
    button_text_matches,
    chat_matches,
    iter_callback_buttons,
)
from src.config import Config
from src.webui.handlers.config import ConfigHandler


class FakeMessage:
    def __init__(self, message_id, buttons, chat=None):
        self.id = message_id
        self.chat = chat
        self.reply_markup = ReplyInlineMarkup(rows=[KeyboardButtonRow(buttons=buttons)])
        self.clicked_data = []

    async def click(self, *, data):
        self.clicked_data.append(data)
        return SimpleNamespace(message="ok")


class ButtonActionMatchingTests(unittest.TestCase):
    def test_supports_exact_contains_and_regex_modes(self):
        self.assertTrue(button_text_matches("立即签到", "立即签到", "exact"))
        self.assertFalse(button_text_matches("立即签到一次", "立即签到", "exact"))
        self.assertTrue(button_text_matches("立即签到一次", "签到", "contains"))
        self.assertTrue(
            button_text_matches("领取 10 积分", r"^领取 \d+ 积分$", "regex")
        )

    def test_only_callback_buttons_are_exposed(self):
        message = FakeMessage(
            1,
            [
                KeyboardButtonUrl(text="打开网页", url="https://example.com"),
                KeyboardButtonCallback(text="确认", data=b"confirm"),
            ],
        )
        self.assertEqual(list(iter_callback_buttons(message)), [("确认", b"confirm")])

    def test_chat_matching_supports_id_and_username(self):
        event = SimpleNamespace(
            chat_id=-100123,
            chat=SimpleNamespace(username="Example_Bot"),
            message=None,
        )
        self.assertTrue(chat_matches(event, [-100123]))
        self.assertTrue(chat_matches(event, ["@example_bot"]))
        self.assertFalse(chat_matches(event, ["@different_bot"]))


class ButtonActionEngineTests(unittest.IsolatedAsyncioTestCase):
    async def test_clicks_first_matching_callback_once(self):
        message = FakeMessage(
            42,
            [
                KeyboardButtonCallback(text="忽略", data=b"ignore"),
                KeyboardButtonCallback(text="立即签到", data=b"check-in"),
                KeyboardButtonCallback(text="确认签到", data=b"confirm"),
            ],
            chat=SimpleNamespace(username="daily_bot"),
        )
        event = SimpleNamespace(
            chat_id=123,
            chat=message.chat,
            message=message,
        )
        engine = ButtonActionEngine(
            [
                ButtonActionRule(
                    name="签到",
                    enabled=True,
                    source_chats=["@daily_bot"],
                    button_texts=["签到"],
                    match_mode="contains",
                )
            ]
        )

        self.assertEqual(await engine.handle(event), ("签到", "立即签到"))
        self.assertIsNone(await engine.handle(event))
        self.assertEqual(message.clicked_data, [b"check-in"])

    async def test_concurrent_duplicate_updates_click_only_once(self):
        message = FakeMessage(
            7,
            [KeyboardButtonCallback(text="确认", data=b"confirm")],
            chat=SimpleNamespace(username="example_bot"),
        )
        original_click = message.click

        async def delayed_click(*, data):
            await asyncio.sleep(0.01)
            return await original_click(data=data)

        message.click = delayed_click
        event = SimpleNamespace(chat_id=9, chat=message.chat, message=message)
        engine = ButtonActionEngine(
            [
                ButtonActionRule(
                    name="确认",
                    enabled=True,
                    source_chats=[9],
                    button_texts=["确认"],
                )
            ]
        )

        results = await asyncio.gather(engine.handle(event), engine.handle(event))
        self.assertEqual(results.count(("确认", "确认")), 1)
        self.assertEqual(message.clicked_data, [b"confirm"])


class ButtonActionConfigTests(unittest.TestCase):
    def test_config_handler_saves_multiple_patterns_and_regex_mode(self):
        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch.dict(os.environ, {"SESSION_TYPE": "user"}),
        ):
            config_path = Path(temp_dir) / "config.yaml"
            config = Config(
                env_file=str(Path(temp_dir) / "missing.env"),
                config_file=str(config_path),
            )
            handler = ConfigHandler(config, SimpleNamespace(is_running=False))

            result = handler.save_button_action_rule(
                0,
                True,
                "@example_bot\n-100123",
                "^确认.*$\n立即签到",
                "regex",
                0.5,
            )

            self.assertIn("✅", result)
            rules = config.get_button_action_rules()
            self.assertEqual(len(rules), 1)
            self.assertEqual(rules[0].source_chats, ["@example_bot", -100123])
            self.assertEqual(rules[0].button_texts, ["^确认.*$", "立即签到"])
            self.assertEqual(rules[0].match_mode, "regex")

    def test_config_handler_rejects_invalid_regex(self):
        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch.dict(os.environ, {"SESSION_TYPE": "user"}),
        ):
            config = Config(
                env_file=str(Path(temp_dir) / "missing.env"),
                config_file=str(Path(temp_dir) / "config.yaml"),
            )
            handler = ConfigHandler(config, SimpleNamespace(is_running=False))

            result = handler.save_button_action_rule(
                0, True, "@example_bot", "[invalid", "regex", 0
            )

            self.assertIn("❌", result)
            self.assertEqual(config.get_button_action_rules(), [])

    def test_config_handler_rejects_bot_mode_when_enabling(self):
        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch.dict(os.environ, {"SESSION_TYPE": "bot"}),
        ):
            config = Config(
                env_file=str(Path(temp_dir) / "missing.env"),
                config_file=str(Path(temp_dir) / "config.yaml"),
            )
            handler = ConfigHandler(config, SimpleNamespace(is_running=False))

            result = handler.save_button_action_rule(
                0, True, "@example_bot", "确认", "exact", 0
            )

            self.assertIn("❌", result)
            self.assertEqual(config.get_button_action_rules(), [])


if __name__ == "__main__":
    unittest.main()
