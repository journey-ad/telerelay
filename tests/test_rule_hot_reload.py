import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from backend.bot_manager import BotManager
from backend.button_actions import ButtonActionRule
from backend.config import Config
from backend.rule import ForwardingRule
from backend.schemas import ForwardingRulePayload
from backend.services import RuleService


class FakeClientManager:
    def __init__(self):
        self.added = []
        self.removed = []

    def add_message_handler(self, callback, chats=None, incoming=None):
        registration = SimpleNamespace(
            callback=callback,
            chats=list(chats or []),
            incoming=incoming,
        )
        self.added.append(registration)
        return registration

    def remove_message_handler(self, registration):
        if registration is not None:
            self.removed.append(registration)


class LiveConfig:
    def __init__(self):
        self.rules = [
            ForwardingRule(
                name="news",
                source_chats=[-1001, -1002],
                target_chats=[-2001],
                filter_keywords=["release"],
            )
        ]
        self.button_rules = [
            ButtonActionRule(
                name="confirm",
                enabled=True,
                source_chats=[-1003],
                button_texts=["Confirm"],
            )
        ]

    def get_enabled_rules(self):
        return self.rules

    def get_enabled_button_action_rules(self):
        return self.button_rules


class RuleHotReloadTests(unittest.IsolatedAsyncioTestCase):
    async def test_runtime_replaces_handlers_and_preserves_queued_rule_snapshots(self):
        config = LiveConfig()
        manager = BotManager(config)
        manager.is_connected = True
        manager.client_manager = FakeClientManager()
        manager._forwarding_handler = "old-forwarding"
        manager._button_handler = "old-button"
        old_queue_forwarder = object()
        manager._queue_forwarders = {"queued-rule": old_queue_forwarder}

        def create_forwarder(rule):
            return SimpleNamespace(rule=rule), SimpleNamespace(rule=rule)

        manager._create_forwarder = create_forwarder

        reloaded = await manager.reload_rules()

        self.assertTrue(reloaded)
        self.assertEqual(list(manager.rule_forwarder_map), ["news"])
        self.assertIs(manager._queue_forwarders["queued-rule"], old_queue_forwarder)
        self.assertIsNotNone(manager.button_action_engine)
        self.assertEqual(
            manager.client_manager.removed,
            ["old-forwarding", "old-button"],
        )
        self.assertEqual(manager.client_manager.added[0].chats, [-1001, -1002])
        self.assertIsNone(manager.client_manager.added[0].incoming)
        self.assertEqual(manager.client_manager.added[1].chats, [-1003])
        self.assertTrue(manager.client_manager.added[1].incoming)

        forwarding_registration = manager._forwarding_handler
        button_registration = manager._button_handler
        config.rules = []
        config.button_rules = []

        await manager.reload_rules()

        self.assertEqual(manager.rule_forwarder_map, {})
        self.assertEqual(manager.forwarders, [])
        self.assertIsNone(manager.forwarder)
        self.assertIsNone(manager.button_action_engine)
        self.assertIn(forwarding_registration, manager.client_manager.removed)
        self.assertIn(button_registration, manager.client_manager.removed)
        self.assertIs(manager._queue_forwarders["queued-rule"], old_queue_forwarder)

    async def test_rule_service_reloads_live_runtime_without_restart(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = Config(
                env_file=str(root / "missing.env"),
                config_file=str(root / "config.yaml"),
            )
            runtime = SimpleNamespace(
                is_running=True,
                reload_count=0,
                restart_count=0,
            )

            async def reload_rules():
                runtime.reload_count += 1
                return True

            async def restart():
                runtime.restart_count += 1
                return True

            runtime.reload_rules = reload_rules
            runtime.restart = restart
            service = RuleService(config, runtime)

            await service.create_rule(
                ForwardingRulePayload(
                    name="live",
                    enabled=True,
                    source_chats=[-1001],
                    target_chats=[-2001],
                )
            )

            self.assertEqual(runtime.reload_count, 1)
            self.assertEqual(runtime.restart_count, 0)


if __name__ == "__main__":
    unittest.main()
