import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.bot_manager import BotManager
from backend.forwarder.forwarder import MessageForwarder
from backend.rule import ForwardingRule
from backend.stats_db import StatsDB
from backend.subscriptions import SubscriberStore


class FakeEvent:
    """Minimal Telethon NewMessage stand-in for private commands."""

    def __init__(self, raw_text, *, is_private=True, sender_id=111, sender=None):
        self.message = SimpleNamespace(raw_text=raw_text)
        self.is_private = is_private
        self.sender_id = sender_id
        self.sender = sender
        self.replies = []

    async def reply(self, text):
        self.replies.append(text)


def make_manager(temp_dir, session_type="bot"):
    store = SubscriberStore(Path(temp_dir) / "subscribers.db")
    manager = BotManager(
        config=SimpleNamespace(),
        session_name=Path(temp_dir) / "telegram",
        queue_db_path=Path(temp_dir) / "forward_queue.db",
        account_id="123",
        session_type=session_type,
        subscriber_store=store,
        stats_db=SimpleNamespace(),
    )
    return manager, store


def alice_sender():
    return SimpleNamespace(
        username="alice", first_name="Alice", last_name="Lee"
    )


class BotCommandHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_registers_user_and_replies_help(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager, store = make_manager(temp_dir)
            event = FakeEvent("/start", sender=alice_sender())
            await manager._bot_command_handler(event)

            record = store.get(111)
            self.assertIsNotNone(record)
            self.assertEqual(record["username"], "alice")
            self.assertEqual(record["first_name"], "Alice")
            self.assertEqual(record["last_name"], "Lee")
            self.assertEqual(record["status"], "active")
            self.assertEqual(len(event.replies), 1)
            self.assertIn("/start", event.replies[0])
            self.assertIn("/stop", event.replies[0])

    async def test_start_with_botname_suffix(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager, store = make_manager(temp_dir)
            event = FakeEvent("/start@myrelaybot", sender=alice_sender())
            await manager._bot_command_handler(event)
            self.assertIsNotNone(store.get(111))
            self.assertEqual(len(event.replies), 1)

    async def test_stop_and_resume_toggle_status(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager, store = make_manager(temp_dir)
            store.record(111, username="alice")

            event = FakeEvent("/stop")
            await manager._bot_command_handler(event)
            self.assertTrue(store.is_suppressed(111))
            self.assertEqual(len(event.replies), 1)
            self.assertIn("/resume", event.replies[0])

            event = FakeEvent("/resume")
            await manager._bot_command_handler(event)
            self.assertFalse(store.is_suppressed(111))
            self.assertEqual(len(event.replies), 1)
            self.assertIn("恢复", event.replies[0])

    async def test_status_replies_reflect_each_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager, store = make_manager(temp_dir)

            event = FakeEvent("/status")
            await manager._bot_command_handler(event)
            self.assertEqual(len(event.replies), 1)
            self.assertIn("未订阅", event.replies[0])

            store.record(111, username="alice")
            event = FakeEvent("/status")
            await manager._bot_command_handler(event)
            self.assertIn("订阅中", event.replies[0])

            store.set_status(111, "paused")
            event = FakeEvent("/status")
            await manager._bot_command_handler(event)
            self.assertIn("已停止", event.replies[0])

    async def test_group_chat_and_unknown_commands_are_ignored(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager, store = make_manager(temp_dir)

            event = FakeEvent("/stop", is_private=False)
            await manager._bot_command_handler(event)
            self.assertEqual(event.replies, [])
            self.assertIsNone(store.get(111))

            event = FakeEvent("/unknown", sender=alice_sender())
            await manager._bot_command_handler(event)
            self.assertEqual(event.replies, [])
            self.assertIsNone(store.get(111))

            event = FakeEvent("plain text")
            await manager._bot_command_handler(event)
            self.assertEqual(event.replies, [])

    async def test_user_mode_ignores_commands(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager, store = make_manager(temp_dir, session_type="user")
            event = FakeEvent("/stop", sender=alice_sender())
            await manager._bot_command_handler(event)
            self.assertEqual(event.replies, [])
            self.assertIsNone(store.get(111))


def make_forwarder(
    client, targets, temp_dir, suppressed_check=None, delivered_callback=None
):
    rule = ForwardingRule(
        name="push",
        source_chats=[-100],
        target_chats=targets,
    )
    stats = StatsDB(Path(temp_dir) / "stats.db")
    return MessageForwarder(
        client=client,
        rule=rule,
        message_filter=SimpleNamespace(),
        stats_db=stats,
        suppressed_check=suppressed_check,
        delivered_callback=delivered_callback,
    )


def push_message():
    return SimpleNamespace(
        grouped_id=None,
        text="hello",
        chat=SimpleNamespace(username=None),
        chat_id=-100,
        id=1,
        sender_id=5,
        sender=SimpleNamespace(first_name="Sender", last_name=None),
        media=None,
    )


class ForwardSuppressionTests(unittest.IsolatedAsyncioTestCase):
    async def test_opted_out_target_is_skipped_and_checkpoint_advances(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client = AsyncMock()
            forwarder = make_forwarder(
                client,
                [111, 222, 333],
                temp_dir,
                suppressed_check=lambda target: target == 222,
            )
            checkpoints = []
            delivered = []
            forwarder.delivered_callback = delivered.append

            result = await forwarder.forward_message(
                push_message(),
                sender_id=5,
                on_target_success=lambda index: checkpoints.append(index),
            )

            self.assertTrue(result)
            self.assertEqual(client.forward_messages.await_count, 2)
            self.assertEqual(checkpoints, [1, 2, 3])
            self.assertEqual(delivered, [111, 333])

    async def test_all_targets_opted_out_sends_nothing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client = AsyncMock()
            forwarder = make_forwarder(
                client,
                [111, 222],
                temp_dir,
                suppressed_check=lambda target: True,
            )
            checkpoints = []
            delivered = []
            forwarder.delivered_callback = delivered.append

            result = await forwarder.forward_message(
                push_message(),
                sender_id=5,
                on_target_success=lambda index: checkpoints.append(index),
            )

            self.assertTrue(result)
            self.assertEqual(client.forward_messages.await_count, 0)
            self.assertEqual(checkpoints, [1, 2])
            self.assertEqual(delivered, [])

    async def test_resume_from_checkpoint_skips_already_delivered_targets(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client = AsyncMock()
            forwarder = make_forwarder(
                client,
                [111, 222, 333],
                temp_dir,
                suppressed_check=lambda target: target == 222,
            )
            checkpoints = []

            result = await forwarder.forward_message(
                push_message(),
                sender_id=5,
                start_target_index=2,
                on_target_success=lambda index: checkpoints.append(index),
            )

            self.assertTrue(result)
            self.assertEqual(client.forward_messages.await_count, 1)
            self.assertEqual(checkpoints, [3])

    async def test_no_suppressed_check_behaves_as_before(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client = AsyncMock()
            forwarder = make_forwarder(client, [111, 222], temp_dir)
            checkpoints = []

            result = await forwarder.forward_message(
                push_message(),
                sender_id=5,
                on_target_success=lambda index: checkpoints.append(index),
            )

            self.assertTrue(result)
            self.assertEqual(client.forward_messages.await_count, 2)
            self.assertEqual(checkpoints, [1, 2])


class BotCommandMenuTests(unittest.IsolatedAsyncioTestCase):
    async def test_set_bot_commands_registers_all_four_commands(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager, _ = make_manager(temp_dir)
            client = AsyncMock()
            manager.client_manager = SimpleNamespace(get_client=lambda: client)

            await manager._set_bot_commands()

            self.assertGreater(client.await_count, 0)
            request = client.await_args.args[0]
            self.assertEqual(len(request.commands), 4)
            commands = {command.command for command in request.commands}
            self.assertEqual(commands, {"start", "stop", "resume", "status"})

    async def test_set_bot_commands_failure_is_swallowed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager, _ = make_manager(temp_dir)

            async def broken(_request):
                raise RuntimeError("telegram error")

            client = AsyncMock(side_effect=broken)
            manager.client_manager = SimpleNamespace(get_client=lambda: client)

            # 失败只记录警告，不中断 runtime 启动流程
            await manager._set_bot_commands()

    async def test_set_bot_commands_noop_without_client(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager, _ = make_manager(temp_dir)
            manager.client_manager = None
            await manager._set_bot_commands()


class TargetSuppressionHelperTests(unittest.TestCase):
    def test_target_user_id_normalization(self):
        self.assertEqual(BotManager._target_user_id(111), 111)
        self.assertEqual(BotManager._target_user_id("111"), 111)
        self.assertEqual(BotManager._target_user_id("@alice"), None)
        self.assertEqual(BotManager._target_user_id(-1001), None)
        self.assertEqual(BotManager._target_user_id("channel"), None)
        self.assertEqual(BotManager._target_user_id(True), None)

    def test_is_target_suppressed_matches_store(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager, store = make_manager(temp_dir)
            store.record(111, username="alice")
            store.set_status(111, "paused")

            self.assertTrue(manager._is_target_suppressed(111))
            self.assertTrue(manager._is_target_suppressed("111"))
            self.assertTrue(manager._is_target_suppressed("@alice"))
            self.assertFalse(manager._is_target_suppressed(222))
            self.assertFalse(manager._is_target_suppressed(-1001))
            self.assertFalse(manager._is_target_suppressed("@bob"))
