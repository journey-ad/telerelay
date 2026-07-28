import asyncio
import stat
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from telethon.errors import FloodWaitError

from src.bot_manager import BotManager
from src.forward_queue import ForwardQueue, ForwardQueueStore
from src.forwarder.forwarder import MessageForwarder
from src.rule import ForwardingRule


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
            self.assertEqual(resumed.next_target_index, 1)
            self.assertEqual(resumed.attempt_count, 2)

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

            def enqueue(self, **kwargs):
                self.calls.append(kwargs)
                return SimpleNamespace(id=91), True

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

        await manager._central_message_handler(Event())

        self.assertEqual(len(manager.forward_queue.calls), 1)
        queued = manager.forward_queue.calls[0]
        self.assertEqual(queued["source_chat_id"], -1001)
        self.assertEqual(queued["source_message_id"], 42)
        self.assertEqual(queued["rule_data"]["name"], rule.name)

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


if __name__ == "__main__":
    unittest.main()
