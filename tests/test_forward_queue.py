import asyncio
import stat
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from telethon.errors import FloodWaitError

from backend.bot_manager import BotManager
from backend.forward_queue import ForwardQueue, ForwardQueueStore
from backend.forwarder.forwarder import MessageForwarder
from backend.rule import ForwardingRule


def rule_data(name="queue-rule"):
    return {
        "name": name,
        "enabled": True,
        "source_chats": [-1001],
        "target_chats": [-2001, -2002],
        "filters": {
            "mode": "blacklist",
            "keywords": [],
            "regex_patterns": [],
            "media_types": [],
            "max_file_size": 0,
            "min_file_size": 0,
        },
        "ignore": {"user_ids": [], "keywords": []},
        "forwarding": {
            "preserve_format": True,
            "add_source_info": True,
            "delay": 0,
            "force_forward": False,
            "hide_sender": False,
            "deduplicate": False,
            "deduplicate_window": 3600,
        },
    }


class ForwardQueueStoreTests(unittest.TestCase):
    def test_processing_item_and_target_checkpoint_survive_reopen(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "forward_queue.db"
            store = ForwardQueueStore(db_path)
            item, inserted = store.enqueue(
                rule_data=rule_data(),
                source_chat_id=-1001,
                source_chat_name="Source Room",
                source_message_id=42,
                sender_id=7,
                grouped_id=None,
            )
            self.assertTrue(inserted)
            self.assertEqual(stat.S_IMODE(db_path.stat().st_mode), 0o600)

            claimed = store.claim_next()
            self.assertEqual(claimed.id, item.id)
            self.assertEqual(claimed.attempt_count, 1)
            store.update_target_index(item.id, 1)

            reopened = ForwardQueueStore(db_path)
            self.assertEqual(reopened.recover_processing(), 1)
            resumed = reopened.claim_next()
            self.assertEqual(resumed.id, item.id)
            self.assertEqual(resumed.source_chat_name, "Source Room")
            self.assertEqual(resumed.next_target_index, 1)
            self.assertEqual(resumed.attempt_count, 2)

    def test_source_chat_name_can_be_backfilled_for_existing_item(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ForwardQueueStore(Path(temp_dir) / "forward_queue.db")
            item, _ = store.enqueue(
                rule_data=rule_data(),
                source_chat_id=-1001,
                source_message_id=42,
                sender_id=7,
                grouped_id=None,
            )
            self.assertIsNone(item.source_chat_name)

            store.update_source_chat_name(item.id, "Backfilled Room")

            self.assertEqual(
                store.get_item(item.id).source_chat_name, "Backfilled Room"
            )

    def test_media_group_updates_merge_and_extend_settle_window(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ForwardQueueStore(Path(temp_dir) / "forward_queue.db")
            first, inserted = store.enqueue(
                rule_data=rule_data(),
                source_chat_id=-1001,
                source_message_id=12,
                sender_id=7,
                grouped_id=999,
                settle_seconds=0.2,
            )
            self.assertTrue(inserted)
            time.sleep(0.01)
            merged, inserted = store.enqueue(
                rule_data=rule_data(),
                source_chat_id=-1001,
                source_message_id=10,
                sender_id=7,
                grouped_id=999,
                settle_seconds=0.2,
            )
            self.assertFalse(inserted)
            self.assertEqual(first.id, merged.id)
            self.assertEqual(merged.source_message_id, 10)
            self.assertGreater(merged.available_at, first.available_at)
            self.assertEqual(store.counts(), {"pending": 1})

    def test_completed_item_is_a_dedup_tombstone(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ForwardQueueStore(Path(temp_dir) / "forward_queue.db")
            item, _ = store.enqueue(
                rule_data=rule_data(),
                source_chat_id=-1001,
                source_message_id=42,
                sender_id=7,
                grouped_id=None,
            )
            store.mark_completed(item.id)
            duplicate, inserted = store.enqueue(
                rule_data=rule_data(),
                source_chat_id=-1001,
                source_message_id=42,
                sender_id=7,
                grouped_id=None,
            )
            self.assertFalse(inserted)
            self.assertEqual(duplicate.status, "completed")

    def test_active_count_only_includes_unfinished_items(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ForwardQueueStore(Path(temp_dir) / "forward_queue.db")
            first, _ = store.enqueue(
                rule_data=rule_data(),
                source_chat_id=-1001,
                source_message_id=41,
                sender_id=7,
                grouped_id=None,
            )
            second, _ = store.enqueue(
                rule_data=rule_data(),
                source_chat_id=-1001,
                source_message_id=42,
                sender_id=7,
                grouped_id=None,
            )

            self.assertEqual(store.active_count(), 2)
            store.claim_next()
            self.assertEqual(store.active_count(), 2)
            store.mark_completed(first.id)
            self.assertEqual(store.active_count(), 1)
            store.claim_next()
            store.mark_failed(second.id, "test")
            self.assertEqual(store.active_count(), 0)

    def test_list_active_prioritizes_processing_and_excludes_terminal_items(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ForwardQueueStore(Path(temp_dir) / "forward_queue.db")
            processing, _ = store.enqueue(
                rule_data=rule_data("processing"),
                source_chat_id=-1001,
                source_message_id=1,
                sender_id=7,
                grouped_id=None,
            )
            completed, _ = store.enqueue(
                rule_data=rule_data("completed"),
                source_chat_id=-1001,
                source_message_id=2,
                sender_id=7,
                grouped_id=None,
            )
            pending, _ = store.enqueue(
                rule_data=rule_data("pending"),
                source_chat_id=-1001,
                source_message_id=3,
                sender_id=7,
                grouped_id=None,
            )
            store.claim_next()
            store.mark_completed(completed.id)

            active = store.list_active(50)

            self.assertEqual([item.id for item in active], [processing.id, pending.id])
            self.assertEqual(active[0].status, "processing")
            self.assertEqual([item.id for item in store.list_active(1)], [processing.id])


class ForwardQueueWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_floodwait_pauses_all_items_and_survives_restart(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ForwardQueueStore(Path(temp_dir) / "forward_queue.db")
            first, _ = store.enqueue(
                rule_data=rule_data("one"),
                source_chat_id=-1001,
                source_message_id=1,
                sender_id=7,
                grouped_id=None,
            )
            store.enqueue(
                rule_data=rule_data("two"),
                source_chat_id=-1001,
                source_message_id=2,
                sender_id=7,
                grouped_id=None,
            )
            calls = []

            async def processor(item):
                calls.append(item.id)
                raise FloodWaitError(None, capture=30)

            queue = ForwardQueue(
                store,
                processor,
                flood_wait_buffer=0,
                poll_interval=0.02,
            )
            await queue.start()
            for _ in range(50):
                if calls:
                    break
                await asyncio.sleep(0.01)

            self.assertEqual(calls, [first.id])
            paused_until, _ = store.get_pause()
            self.assertGreater(paused_until, time.time() + 20)
            self.assertEqual(store.counts(), {"pending": 2})
            self.assertEqual(store.get_item(first.id).failure_count, 0)
            await queue.stop()

            restarted = ForwardQueue(store, processor, poll_interval=0.02)
            await restarted.start()
            await asyncio.sleep(0.08)
            self.assertEqual(calls, [first.id])
            await restarted.stop()

    async def test_normal_failure_retries_then_completes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ForwardQueueStore(Path(temp_dir) / "forward_queue.db")
            item, _ = store.enqueue(
                rule_data=rule_data(),
                source_chat_id=-1001,
                source_message_id=3,
                sender_id=7,
                grouped_id=None,
            )
            calls = 0
            outcomes = []

            async def processor(_item):
                nonlocal calls
                calls += 1
                if calls == 1:
                    raise RuntimeError("temporary")
                return 0

            queue = ForwardQueue(
                store,
                processor,
                retry_base_seconds=0.02,
                poll_interval=0.01,
                on_outcome=lambda item, status, error: outcomes.append(
                    (item.id, status, str(error) if error else None)
                ),
            )
            await queue.start()
            for _ in range(100):
                if store.get_item(item.id).status == "completed":
                    break
                await asyncio.sleep(0.01)
            await queue.stop()

            saved = store.get_item(item.id)
            self.assertEqual(saved.status, "completed")
            self.assertEqual(saved.attempt_count, 2)
            self.assertEqual(saved.failure_count, 1)
            self.assertEqual(
                outcomes,
                [
                    (item.id, "retrying", "temporary"),
                    (item.id, "completed", None),
                ],
            )

    async def test_retry_limit_retains_failed_item(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ForwardQueueStore(Path(temp_dir) / "forward_queue.db")
            item, _ = store.enqueue(
                rule_data=rule_data(),
                source_chat_id=-1001,
                source_message_id=4,
                sender_id=7,
                grouped_id=None,
            )

            async def processor(_item):
                raise RuntimeError("permanent")

            queue = ForwardQueue(
                store,
                processor,
                max_retries=2,
                retry_base_seconds=0.01,
                poll_interval=0.01,
            )
            await queue.start()
            for _ in range(100):
                if store.get_item(item.id).status == "failed":
                    break
                await asyncio.sleep(0.01)
            await queue.stop()

            saved = store.get_item(item.id)
            self.assertEqual(saved.status, "failed")
            self.assertEqual(saved.failure_count, 2)
            self.assertEqual(saved.attempt_count, 2)

    async def test_new_enqueue_does_not_shorten_forwarding_delay(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ForwardQueueStore(Path(temp_dir) / "forward_queue.db")
            first, _ = store.enqueue(
                rule_data=rule_data("first"),
                source_chat_id=-1001,
                source_message_id=5,
                sender_id=7,
                grouped_id=None,
            )
            calls = []

            async def processor(item):
                calls.append((item.id, time.monotonic()))
                return 0.15 if item.id == first.id else 0

            queue = ForwardQueue(store, processor, poll_interval=0.01)
            await queue.start()
            for _ in range(50):
                if calls:
                    break
                await asyncio.sleep(0.01)
            queue.enqueue(
                rule_data=rule_data("second"),
                source_chat_id=-1001,
                source_message_id=6,
                sender_id=7,
                grouped_id=None,
            )
            for _ in range(100):
                if len(calls) == 2:
                    break
                await asyncio.sleep(0.01)
            await queue.stop()

            self.assertEqual(len(calls), 2)
            self.assertGreaterEqual(calls[1][1] - calls[0][1], 0.13)


class ForwardingIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_message_handler_only_enqueues_without_entity_requests(self):
        class FakeConfig:
            forward_queue_media_group_settle_seconds = 1

        class FakeQueue:
            def __init__(self):
                self.calls = []
                self.depth_calls = 0

            def enqueue(self, **kwargs):
                self.calls.append(kwargs)
                return SimpleNamespace(source_message_id=kwargs["source_message_id"]), True

            def active_count(self):
                self.depth_calls += 1
                return len(self.calls)

        class FakeFilter:
            def should_forward(self, message, sender_id):
                return True

        class Event:
            chat_id = -1001
            sender_id = 7
            chat = SimpleNamespace(title="Source")
            sender = SimpleNamespace(first_name="Sender", last_name=None)
            message = SimpleNamespace(
                id=42,
                text="hello",
                grouped_id=None,
                chat=chat,
                sender=sender,
                media=None,
            )

            async def get_chat(self):
                raise AssertionError("ingestion must not request chat entities")

            async def get_sender(self):
                raise AssertionError("ingestion must not request sender entities")

        rule = ForwardingRule.from_dict(rule_data())
        manager = BotManager(FakeConfig())
        manager.forward_queue = FakeQueue()
        manager.rule_forwarder_map = {
            rule.name: (rule, FakeFilter(), SimpleNamespace())
        }

        with patch("backend.bot_manager.logger.info") as log_info:
            await manager._central_message_handler(Event())

        self.assertEqual(len(manager.forward_queue.calls), 1)
        self.assertEqual(manager.forward_queue.depth_calls, 1)
        queued = manager.forward_queue.calls[0]
        self.assertEqual(queued["source_chat_id"], -1001)
        self.assertEqual(queued["source_chat_name"], "Source")
        self.assertEqual(queued["source_message_id"], 42)
        self.assertEqual(queued["rule_data"]["name"], rule.name)
        entry_log = log_info.call_args.args[0]
        self.assertIn("queue-rule", entry_log)
        self.assertIn("Source (-1001)/42", entry_log)
        self.assertNotIn("item", entry_log.lower())
        self.assertNotIn("队列项", entry_log)

    async def test_media_group_members_log_one_info_and_debug_merges(self):
        class FakeConfig:
            forward_queue_media_group_settle_seconds = 1

        class FakeQueue:
            def __init__(self):
                self.calls = []

            def enqueue(self, **kwargs):
                self.calls.append(kwargs)
                return SimpleNamespace(source_message_id=42), len(self.calls) == 1

            def active_count(self):
                return 1

        class Event:
            chat_id = -1001
            sender_id = 7
            chat = SimpleNamespace(title="Source")
            sender = SimpleNamespace(first_name="Sender", last_name=None)

            def __init__(self, message_id):
                self.message = SimpleNamespace(
                    id=message_id,
                    text="album",
                    grouped_id=999,
                    chat=self.chat,
                    sender=self.sender,
                    media=SimpleNamespace(),
                )

        rule = ForwardingRule.from_dict(rule_data())
        manager = BotManager(FakeConfig())
        manager.forward_queue = FakeQueue()
        manager.rule_forwarder_map = {
            rule.name: (rule, SimpleNamespace(), SimpleNamespace())
        }

        with (
            patch("backend.bot_manager.logger.info") as log_info,
            patch("backend.bot_manager.logger.debug") as log_debug,
        ):
            await manager._central_message_handler(Event(42))
            await manager._central_message_handler(Event(43))

        self.assertEqual(log_info.call_count, 1)
        enqueued_log = log_info.call_args.args[0]
        self.assertIn("Source (-1001)/42", enqueued_log)
        self.assertNotIn("999", enqueued_log)
        self.assertNotIn("anchor", enqueued_log.lower())
        self.assertNotIn("锚点", enqueued_log)
        merged_log = log_debug.call_args.args[0]
        self.assertIn("/43", merged_log)
        self.assertNotIn("999", merged_log)
        self.assertNotIn("/42", merged_log)
        self.assertNotIn("anchor", merged_log.lower())
        self.assertNotIn("锚点", merged_log)
        self.assertNotIn("item", merged_log.lower())
        self.assertNotIn("队列项", merged_log)

    async def test_button_action_success_log_contains_message_content(self):
        class FakeEngine:
            async def handle(self, event):
                return "button-rule", ["Confirm"]

        manager = BotManager(SimpleNamespace())
        manager.button_action_engine = FakeEngine()
        trigger_calls = []
        manager.stats_db = SimpleNamespace(increment_button_action=trigger_calls.append)
        event = SimpleNamespace(
            chat_id=-1001,
            message=SimpleNamespace(
                id=42,
                text="first line\nsecond line",
                media=None,
            ),
        )

        with patch("backend.bot_manager.logger.info") as log_info:
            await manager._button_action_handler(event)

        success_log = log_info.call_args.args[0]
        self.assertIn("button-rule", success_log)
        self.assertIn("Confirm", success_log)
        self.assertIn("-1001/42", success_log)
        self.assertIn("first line second line", success_log)
        self.assertEqual(trigger_calls, ["button-rule"])

    async def test_button_action_success_log_contains_media_description(self):
        class FakeEngine:
            async def handle(self, event):
                return "button-rule", ["Confirm", "Continue"]

        manager = BotManager(SimpleNamespace())
        manager.button_action_engine = FakeEngine()
        manager.stats_db = SimpleNamespace(increment_button_action=lambda name: None)
        event = SimpleNamespace(
            chat_id=-1001,
            message=SimpleNamespace(id=43, text=None, media=SimpleNamespace()),
        )

        with (
            patch("backend.bot_manager.logger.info") as log_info,
            patch("backend.utils.get_media_description", return_value="[video]"),
        ):
            await manager._button_action_handler(event)

        success_log = log_info.call_args.args[0]
        self.assertIn("[video]", success_log)
        self.assertIn("Confirm, Continue", success_log)
        self.assertIn("2", success_log)

    async def test_target_labels_are_resolved_once_and_cached(self):
        class FakeClient:
            def __init__(self):
                self.calls = []

            async def get_entity(self, target):
                self.calls.append(target)
                return SimpleNamespace()

        client = FakeClient()
        shared_cache = {}
        forwarder = MessageForwarder.__new__(MessageForwarder)
        forwarder.client = client
        forwarder._target_label_cache = shared_cache

        with (
            patch("backend.forwarder.forwarder.utils.get_display_name", return_value="Target Chat"),
            patch("backend.forwarder.forwarder.utils.get_peer_id", return_value=-100200),
        ):
            first = await forwarder._resolve_target_labels(["@target"])
            second = await forwarder._resolve_target_labels(["@target"])

        self.assertEqual(first, ["Target Chat (-100200)"])
        self.assertEqual(second, first)
        self.assertEqual(client.calls, ["@target"])

    def test_forward_summary_contains_business_context_without_queue_item_id(self):
        class FakeStats:
            def increment_forwarded(self, rule_name):
                pass

            def increment_daily(self, rule_name, is_forwarded):
                pass

            def insert_history(self, **kwargs):
                pass

        forwarder = MessageForwarder.__new__(MessageForwarder)
        forwarder.rule = SimpleNamespace(name="queue-rule", target_chats=[-100200])
        forwarder.forwarded_count = 0
        forwarder._stats_db = FakeStats()
        message = SimpleNamespace(
            id=42,
            text="hello",
            chat_id=-1001,
            chat=SimpleNamespace(title="Source Chat", username=None),
            sender_id=7,
            sender=None,
            media=None,
            grouped_id=None,
        )

        with patch("backend.forwarder.forwarder.logger.info") as log_info:
            forwarder._log_result(
                message,
                [message],
                success=1,
                total=1,
                target_labels=["Target Chat (-100200)"],
            )

        summary = log_info.call_args.args[0]
        self.assertIn("queue-rule", summary)
        self.assertIn("Source Chat (-1001)/42", summary)
        self.assertIn("Target Chat (-100200)", summary)
        self.assertNotIn("item", summary.lower())
        self.assertNotIn("队列项", summary)

    def test_media_group_summary_contains_count_without_grouped_id(self):
        class FakeStats:
            def increment_forwarded(self, rule_name):
                pass

            def increment_daily(self, rule_name, is_forwarded):
                pass

            def insert_history(self, **kwargs):
                pass

        forwarder = MessageForwarder.__new__(MessageForwarder)
        forwarder.rule = SimpleNamespace(name="queue-rule", target_chats=[-100200])
        forwarder.forwarded_count = 0
        forwarder._stats_db = FakeStats()
        message = SimpleNamespace(
            id=42,
            text="album",
            chat_id=-1001,
            chat=SimpleNamespace(title="Source Chat", username=None),
            sender_id=7,
            sender=None,
            media=SimpleNamespace(),
            grouped_id=999,
        )

        with patch("backend.forwarder.forwarder.logger.info") as log_info:
            forwarder._log_result(
                message,
                [message, SimpleNamespace(id=43)],
                success=1,
                total=1,
                target_labels=["Target Chat (-100200)"],
            )

        summary = log_info.call_args.args[0]
        self.assertIn("2", summary)
        self.assertNotIn("999", summary)
        self.assertNotIn("grouped_id", summary)

    async def test_forwarder_resumes_at_failed_target_checkpoint(self):
        forwarder = MessageForwarder.__new__(MessageForwarder)
        forwarder.rule = SimpleNamespace(
            target_chats=["one", "two", "three"],
            hide_sender=False,
            delay=0,
        )
        forwarder.downloader = SimpleNamespace()
        forwarder._build_source_text = lambda message: ""
        forwarder._log_result = lambda *args: None
        calls = []
        failed_once = False

        async def forward_normal(messages, target, source_data, source_text, is_noforwards):
            nonlocal failed_once
            calls.append(target)
            if target == "two" and not failed_once:
                failed_once = True
                raise FloodWaitError(None, capture=30)

        forwarder._forward_normal = forward_normal
        checkpoints = []
        message = SimpleNamespace()

        with self.assertRaises(FloodWaitError):
            await forwarder._do_forward(
                [message],
                message,
                need_download=False,
                is_noforwards=False,
                on_target_success=checkpoints.append,
            )
        self.assertEqual(calls, ["one", "two"])
        self.assertEqual(checkpoints, [1])

        await forwarder._do_forward(
            [message],
            message,
            need_download=False,
            is_noforwards=False,
            start_target_index=1,
            on_target_success=checkpoints.append,
        )
        self.assertEqual(calls, ["one", "two", "two", "three"])
        self.assertEqual(checkpoints, [1, 2, 3])

    async def test_forward_normal_strips_media_caption_when_hidden(self):
        forwarder = MessageForwarder.__new__(MessageForwarder)
        forwarder.rule = SimpleNamespace(
            hide_sender=False,
            hide_media_caption=True,
            preserve_format=True,
        )
        forwarder.client = SimpleNamespace(
            send_message=AsyncMock(),
            forward_messages=AsyncMock(),
        )
        message = SimpleNamespace(
            raw_text="media caption",
            entities=[],
            media=SimpleNamespace(),
        )

        await forwarder._forward_normal([message], "target", None, "", False)

        forwarder.client.forward_messages.assert_not_called()
        send_message = forwarder.client.send_message
        self.assertEqual(send_message.call_args.args[1], "")
        self.assertEqual(send_message.call_args.kwargs["file"], message.media)

    async def test_send_files_strips_media_caption_when_hidden(self):
        forwarder = MessageForwarder.__new__(MessageForwarder)
        forwarder.rule = SimpleNamespace(hide_media_caption=True)
        forwarder.client = SimpleNamespace(send_file=AsyncMock())
        message = SimpleNamespace(
            raw_text="media caption",
            entities=[],
            media=SimpleNamespace(),
        )

        await forwarder._send_files(["photo.jpg"], [message], "target", None, "")

        self.assertEqual(
            forwarder.client.send_file.call_args.kwargs["caption"],
            "",
        )


if __name__ == "__main__":
    unittest.main()
