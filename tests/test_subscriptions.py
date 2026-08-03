import sqlite3
import stat
import tempfile
import unittest
from pathlib import Path

from backend.subscriptions import AccountSubscriptionRegistry, SubscriberStore


class SubscriberStoreTests(unittest.TestCase):
    def test_record_and_status_roundtrip(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SubscriberStore(Path(temp_dir) / "subscribers.db")
            record = store.record(
                111, username="alice", first_name="Alice", last_name="Lee"
            )
            self.assertEqual(record["status"], "active")
            self.assertEqual(record["username"], "alice")
            self.assertEqual(record["first_name"], "Alice")
            self.assertEqual(record["delivered_count"], 0)
            self.assertFalse(store.is_suppressed(111))

            store.set_status(111, "paused")
            self.assertTrue(store.is_suppressed(111))
            self.assertEqual(store.get(111)["status"], "paused")

            store.set_status(111, "active")
            self.assertFalse(store.is_suppressed(111))

            self.assertTrue(store.increment_delivered(111))
            self.assertTrue(store.increment_delivered_username("@ALICE"))
            self.assertEqual(store.get(111)["delivered_count"], 2)
            self.assertFalse(store.increment_delivered(222))

    def test_record_preserves_opt_out_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SubscriberStore(Path(temp_dir) / "subscribers.db")
            store.record(111, username="alice")
            store.set_status(111, "paused")

            # Re-registering via /start must not silently re-enable push.
            store.record(111, username="alice", first_name="Alice")
            self.assertTrue(store.is_suppressed(111))
            self.assertEqual(store.get(111)["first_name"], "Alice")

    def test_username_lookup_is_case_insensitive(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SubscriberStore(Path(temp_dir) / "subscribers.db")
            store.record(111, username="Alice")
            store.set_status(111, "paused")
            self.assertTrue(store.is_suppressed_username("@alice"))
            self.assertTrue(store.is_suppressed_username("ALICE"))
            self.assertFalse(store.is_suppressed_username("@bob"))

    def test_set_status_upserts_unknown_user(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SubscriberStore(Path(temp_dir) / "subscribers.db")
            store.set_status(999, "paused")
            self.assertTrue(store.is_suppressed(999))
            record = store.get(999)
            self.assertIsNone(record["username"])

    def test_counts_and_list_order(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SubscriberStore(Path(temp_dir) / "subscribers.db")
            store.record(111, username="alice")
            store.record(222, username="bob")
            store.record(333, username="carol")
            store.set_status(333, "paused")

            self.assertEqual(store.counts(), {"total": 3, "active": 2, "paused": 1})
            user_ids = [record["user_id"] for record in store.list()]
            self.assertEqual(user_ids, [333, 222, 111])

    def test_persistence_across_reopen(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "subscribers.db"
            store = SubscriberStore(path)
            store.record(111, username="alice")
            store.set_status(111, "paused")

            reopened = SubscriberStore(path)
            self.assertTrue(reopened.is_suppressed(111))
            self.assertEqual(reopened.get(111)["username"], "alice")
            self.assertEqual(reopened.counts()["total"], 1)

    def test_file_permissions_are_restricted(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "subscribers.db"
            SubscriberStore(path)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_invalid_status_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SubscriberStore(Path(temp_dir) / "subscribers.db")
            with self.assertRaises(ValueError):
                store.set_status(111, "unknown")


class AccountSubscriptionRegistryTests(unittest.TestCase):
    def test_registry_isolates_accounts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = AccountSubscriptionRegistry(data_dir=temp_dir)
            first = registry.for_account("111")
            second = registry.for_account("222")
            self.assertIs(first, registry.for_account("111"))
            self.assertIsNot(first, second)
            self.assertNotEqual(first.db_path, second.db_path)

            first.record(1, username="a")
            self.assertIsNone(second.get(1))

            registry.discard("111")
            self.assertIsNot(first, registry.for_account("111"))
