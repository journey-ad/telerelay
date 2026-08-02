import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from telethon.tl.types import (
    KeyboardButtonCallback,
    KeyboardButtonRow,
    KeyboardButtonUrl,
    ReplyInlineMarkup,
)

from backend.button_actions import (
    ButtonActionEngine,
    ButtonActionRule,
    button_text_matches,
    chat_matches,
    iter_callback_buttons,
)
from backend.config import Config
from backend.schemas import ButtonActionRulePayload
from backend.services import RuleService, ServiceError


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

        self.assertEqual(await engine.handle(event), ("签到", ["立即签到"]))
        self.assertIsNone(await engine.handle(event))
        self.assertEqual(message.clicked_data, [b"check-in"])

    async def test_clicks_all_matching_callbacks_when_enabled(self):
        message = FakeMessage(
            43,
            [
                KeyboardButtonCallback(text="忽略", data=b"ignore"),
                KeyboardButtonCallback(text="立即签到", data=b"check-in"),
                KeyboardButtonCallback(text="确认签到", data=b"confirm"),
                KeyboardButtonUrl(text="签到说明", url="https://example.com"),
            ],
            chat=SimpleNamespace(username="daily_bot"),
        )
        event = SimpleNamespace(chat_id=123, chat=message.chat, message=message)
        engine = ButtonActionEngine(
            [
                ButtonActionRule(
                    name="签到",
                    enabled=True,
                    source_chats=["@daily_bot"],
                    button_texts=["签到"],
                    match_mode="contains",
                    click_all_matches=True,
                )
            ]
        )

        self.assertEqual(
            await engine.handle(event),
            ("签到", ["立即签到", "确认签到"]),
        )
        self.assertIsNone(await engine.handle(event))
        self.assertEqual(message.clicked_data, [b"check-in", b"confirm"])

    async def test_partial_multi_click_failure_marks_message_processed(self):
        message = FakeMessage(
            44,
            [
                KeyboardButtonCallback(text="确认一", data=b"first"),
                KeyboardButtonCallback(text="确认二", data=b"second"),
            ],
            chat=SimpleNamespace(username="example_bot"),
        )

        async def fail_second(*, data):
            if data == b"second":
                raise RuntimeError("second click failed")
            message.clicked_data.append(data)

        message.click = fail_second
        event = SimpleNamespace(chat_id=9, chat=message.chat, message=message)
        engine = ButtonActionEngine(
            [
                ButtonActionRule(
                    name="确认",
                    enabled=True,
                    source_chats=[9],
                    button_texts=["确认"],
                    match_mode="contains",
                    click_all_matches=True,
                )
            ]
        )

        with self.assertRaisesRegex(RuntimeError, "second click failed"):
            await engine.handle(event)
        self.assertIsNone(await engine.handle(event))
        self.assertEqual(message.clicked_data, [b"first"])

    async def test_multi_click_applies_delay_once_before_batch(self):
        message = FakeMessage(
            45,
            [
                KeyboardButtonCallback(text="确认一", data=b"first"),
                KeyboardButtonCallback(text="确认二", data=b"second"),
            ],
            chat=SimpleNamespace(username="example_bot"),
        )
        event = SimpleNamespace(chat_id=9, chat=message.chat, message=message)
        engine = ButtonActionEngine(
            [
                ButtonActionRule(
                    name="确认",
                    enabled=True,
                    source_chats=[9],
                    button_texts=["确认"],
                    match_mode="contains",
                    delay=0.5,
                    click_all_matches=True,
                )
            ]
        )

        with patch("backend.button_actions.asyncio.sleep", new_callable=AsyncMock) as sleep:
            await engine.handle(event)

        sleep.assert_awaited_once_with(0.5)
        self.assertEqual(message.clicked_data, [b"first", b"second"])

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
        self.assertEqual(results.count(("确认", ["确认"])), 1)
        self.assertEqual(message.clicked_data, [b"confirm"])


class ButtonActionConfigTests(unittest.IsolatedAsyncioTestCase):
    async def test_rule_service_saves_multiple_patterns_and_regex_mode(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.yaml"
            config = Config(
                env_file=str(Path(temp_dir) / "missing.env"),
                config_file=str(config_path),
            )
            service = RuleService(config, SimpleNamespace(is_running=False))

            result = await service.create_button_rule(
                ButtonActionRulePayload(
                    name="签到",
                    enabled=True,
                    source_chats=["@example_bot", -100123],
                    button_texts=["^确认.*$", "立即签到"],
                    match_mode="regex",
                    delay=0.5,
                    click_all_matches=True,
                )
            )

            self.assertEqual(result["name"], "签到")
            rules = config.get_button_action_rules()
            self.assertEqual(len(rules), 1)
            self.assertEqual(rules[0].source_chats, ["@example_bot", -100123])
            self.assertEqual(rules[0].button_texts, ["^确认.*$", "立即签到"])
            self.assertEqual(rules[0].match_mode, "regex")
            self.assertTrue(rules[0].click_all_matches)

    def test_old_config_defaults_to_first_matching_button(self):
        rule = ButtonActionRule.from_dict(
            {
                "name": "legacy",
                "enabled": True,
                "source_chats": [1],
                "button_texts": ["确认"],
            }
        )

        self.assertFalse(rule.click_all_matches)
        self.assertFalse(rule.to_dict()["click_all_matches"])

    async def test_rule_service_rejects_invalid_regex(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = Config(
                env_file=str(Path(temp_dir) / "missing.env"),
                config_file=str(Path(temp_dir) / "config.yaml"),
            )
            service = RuleService(config, SimpleNamespace(is_running=False))

            with self.assertRaises(ServiceError) as raised:
                await service.create_button_rule(
                    ButtonActionRulePayload(
                        name="invalid",
                        enabled=True,
                        source_chats=["@example_bot"],
                        button_texts=["[invalid"],
                        match_mode="regex",
                    )
                )

            self.assertEqual(raised.exception.code, "invalid_regex")
            self.assertEqual(config.get_button_action_rules(), [])

    async def test_rule_service_rejects_bot_mode_when_enabling(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = Config(
                env_file=str(Path(temp_dir) / "missing.env"),
                config_file=str(Path(temp_dir) / "config.yaml"),
            )
            service = RuleService(
                config,
                SimpleNamespace(is_running=False),
                session_type="bot",
            )

            with self.assertRaises(ServiceError) as raised:
                await service.create_button_rule(
                    ButtonActionRulePayload(
                        name="bot-mode",
                        enabled=True,
                        source_chats=["@example_bot"],
                        button_texts=["确认"],
                    )
                )

            self.assertEqual(raised.exception.code, "user_mode_required")
            self.assertEqual(config.get_button_action_rules(), [])

    async def test_bot_config_validate_accepts_store_token(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text("API_ID=12345\nAPI_HASH=test-hash\n", encoding="utf-8")
            config_path = Path(temp_dir) / "config.yaml"
            config_path.write_text(
                "session_type: bot\nforwarding_rules: []\n",
                encoding="utf-8",
            )
            config = Config(
                env_file=str(env_path),
                config_file=str(config_path),
            )

            valid, message = config.validate()
            self.assertFalse(valid)
            self.assertIn("BOT_TOKEN", message)

            valid, message = config.validate(bot_token="123456789:AA" + "x" * 30)
            self.assertFalse(valid)
            self.assertNotIn("BOT_TOKEN", message)


if __name__ == "__main__":
    unittest.main()
