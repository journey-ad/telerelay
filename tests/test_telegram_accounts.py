import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend.client import TelegramClientManager
from backend.telegram_accounts import (
    TelegramAccountError,
    TelegramAccountService,
    TelegramAccountStore,
)
from backend.telegram_runtimes import TelegramRuntimeRegistry


class FakeRuntime:
    def __init__(self, config, auth_manager, session_name, queue_db_path, account_id):
        self.session_name = session_name
        self.queue_db_path = Path(queue_db_path)
        self.account_id = account_id
        self.is_running = False
        self.is_connected = False
        self.actions: list[tuple[str, str]] = []
        self.on_user_authenticated = None
        self.client_manager = None
        self.forwarders = []

    async def start(self) -> bool:
        self.actions.append(("start", str(self.session_name)))
        self.is_running = True
        return True

    async def stop(self) -> bool:
        self.actions.append(("stop", str(self.session_name)))
        self.is_running = False
        self.is_connected = False
        return True

    async def restart(self) -> bool:
        self.actions.append(("restart", str(self.session_name)))
        self.is_running = True
        return True

    def bind_loop(self, loop) -> None:
        self.loop = loop

    def get_status(self):
        return {
            "is_running": self.is_running,
            "is_connected": self.is_connected,
            "queue": {"counts": {}, "paused_until": 0, "pause_reason": None},
        }


def make_registry(store: TelegramAccountStore) -> TelegramRuntimeRegistry:
    config = SimpleNamespace(forward_queue_db_path=str(store.data_dir / "forward_queue.db"))
    return TelegramRuntimeRegistry(
        config,
        store,
        auth_timeout=1,
        bot_factory=FakeRuntime,
    )


class TelegramAccountStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)

    def test_default_account_keeps_legacy_session_path(self):
        (self.root / "telegram_session.session").touch()
        store = TelegramAccountStore(self.root)

        account = store.list_public()[0]

        self.assertEqual(account["id"], "default")
        self.assertTrue(account["authenticated"])
        self.assertEqual(store.active_session_name, self.root / "telegram_session")

    def test_registry_round_trip_and_identity_update(self):
        store = TelegramAccountStore(self.root)
        account = store.create("工作账号")
        store.update_identity(
            account.id,
            {
                "display_name": "Test User",
                "username": "test_user",
                "telegram_user_id": 123,
            },
        )
        Path(f"{store.session_name(account.id)}.session").parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        Path(f"{store.session_name(account.id)}.session").touch()

        restored = TelegramAccountStore(self.root)
        active = next(item for item in restored.list_public() if item["active"])

        self.assertEqual(active["id"], account.id)
        self.assertEqual(active["display_name"], "Test User")
        self.assertEqual(active["username"], "test_user")
        self.assertTrue(active["authenticated"])
        payload = json.loads((self.root / "telegram_accounts.json").read_text())
        self.assertNotIn("password", payload)

    def test_last_account_cannot_be_deleted(self):
        store = TelegramAccountStore(self.root)

        with self.assertRaises(TelegramAccountError) as raised:
            store.delete("default")

        self.assertEqual(raised.exception.code, "last_account")

    def test_clear_identity_marks_new_account_unauthenticated(self):
        store = TelegramAccountStore(self.root)
        account = store.create("工作账号")
        store.update_identity(account.id, {"telegram_user_id": 123})

        store.clear_identity(account.id)

        self.assertFalse(store.get_public(account.id)["authenticated"])

    def test_avatar_cache_is_versioned_and_can_be_cleared(self):
        store = TelegramAccountStore(self.root)

        store.update_avatar("default", b"first-avatar")

        account = store.get_public("default")
        self.assertIsNotNone(account["avatar_version"])
        self.assertEqual(store.get_avatar_path("default").read_bytes(), b"first-avatar")

        store.update_avatar("default", None)

        self.assertIsNone(store.get_avatar_path("default"))
        self.assertIsNone(store.get_public("default")["avatar_version"])

    def test_identity_callback_updates_avatar_when_payload_includes_it(self):
        store = TelegramAccountStore(self.root)
        service = TelegramAccountService(store, make_registry(store))

        service.update_identity(
            "default",
            {
                "display_name": "Avatar User",
                "telegram_user_id": 789,
                "avatar_bytes": b"avatar-bytes",
            }
        )

        self.assertEqual(store.get_avatar_path("default").read_bytes(), b"avatar-bytes")


class TelegramAccountServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.store = TelegramAccountStore(self.root)
        self.registry = make_registry(self.store)
        self.service = TelegramAccountService(self.store, self.registry)
        self.default_runtime = self.registry.ensure_runtime("default")

    async def test_create_keeps_existing_runtime_running(self):
        self.default_runtime.is_running = True

        account = await self.service.create("新账号")

        self.assertTrue(self.default_runtime.is_running)
        self.assertEqual(account["id"], self.store.active_account_id)
        self.assertEqual(self.registry.ensure_runtime(account["id"]).actions, [])

    async def test_activate_authenticated_account_does_not_stop_or_start_any_runtime(self):
        new_account = self.store.create("已登录账号")
        self.store.update_identity(new_account.id, {"telegram_user_id": 456})
        Path(f"{self.store.session_name(new_account.id)}.session").parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        Path(f"{self.store.session_name(new_account.id)}.session").touch()
        self.store.set_active("default")
        self.default_runtime.is_running = True
        new_runtime = self.registry.ensure_runtime(new_account.id)
        new_runtime.is_running = True

        await self.service.activate(new_account.id)

        self.assertEqual(self.store.active_account_id, new_account.id)
        self.assertTrue(self.default_runtime.is_running)
        self.assertTrue(new_runtime.is_running)
        self.assertEqual(self.default_runtime.actions, [])
        self.assertEqual(new_runtime.actions, [])

    async def test_duplicate_label_does_not_stop_active_runtime(self):
        self.default_runtime.is_running = True

        with self.assertRaises(TelegramAccountError):
            await self.service.create("Telegram 账号")

        self.assertEqual(self.default_runtime.actions, [])
        self.assertTrue(self.default_runtime.is_running)

    async def test_deleting_last_account_does_not_stop_active_runtime(self):
        self.default_runtime.is_running = True

        with self.assertRaises(TelegramAccountError):
            await self.service.delete("default")

        self.assertEqual(self.default_runtime.actions, [])
        self.assertTrue(self.default_runtime.is_running)

    async def test_activate_unauthenticated_account_does_not_start(self):
        new_account = self.store.create("待登录账号")
        self.store.set_active("default")

        await self.service.activate(new_account.id)

        self.assertEqual(self.store.active_account_id, new_account.id)
        self.assertFalse(self.registry.ensure_runtime(new_account.id).is_running)

    async def test_delete_stops_only_the_deleted_runtime(self):
        account = self.store.create("并行账号")
        self.store.update_identity(account.id, {"telegram_user_id": 123})
        Path(f"{self.store.session_name(account.id)}.session").parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        Path(f"{self.store.session_name(account.id)}.session").touch()
        target = self.registry.ensure_runtime(account.id)
        self.default_runtime.is_running = True
        target.is_running = True
        target.queue_db_path.parent.mkdir(parents=True, exist_ok=True)
        target.queue_db_path.touch()
        Path(f"{target.queue_db_path}-wal").touch()

        await self.service.delete(account.id)

        self.assertTrue(self.default_runtime.is_running)
        self.assertEqual(target.actions[0][0], "stop")
        self.assertFalse(target.queue_db_path.exists())
        self.assertFalse(Path(f"{target.queue_db_path}-wal").exists())
        with self.assertRaises(TelegramAccountError):
            self.registry.get_runtime(account.id)

    async def test_registry_starts_all_authenticated_accounts_with_isolated_queues(self):
        Path(f"{self.store.session_name('default')}.session").touch()
        account = self.store.create("第二账号")
        self.store.update_identity(account.id, {"telegram_user_id": 456})
        session_path = Path(f"{self.store.session_name(account.id)}.session")
        session_path.parent.mkdir(parents=True, exist_ok=True)
        session_path.touch()

        started = await self.registry.start()

        second = self.registry.get_runtime(account.id)
        self.assertTrue(started)
        self.assertTrue(self.default_runtime.is_running)
        self.assertTrue(second.is_running)
        self.assertEqual(
            self.default_runtime.queue_db_path,
            self.root / "forward_queue.db",
        )
        self.assertEqual(
            second.queue_db_path,
            self.root / "forward_queues" / f"account_{account.id}.db",
        )

    async def test_identity_callback_is_bound_to_originating_account(self):
        account = self.store.create("登录中账号")
        runtime = self.registry.ensure_runtime(account.id)
        self.store.set_active("default")
        self.registry.on_user_authenticated = self.service.update_identity

        runtime.on_user_authenticated(
            {
                "display_name": "Parallel User",
                "telegram_user_id": 9001,
            }
        )

        self.assertEqual(self.store.get_public(account.id)["display_name"], "Parallel User")
        self.assertEqual(self.store.get_public("default")["display_name"], "")

    async def test_each_account_has_an_independent_auth_manager(self):
        account = await self.service.create("独立认证账号")

        self.assertIsNot(
            self.registry.get_auth("default"),
            self.registry.get_auth(account["id"]),
        )

    async def test_account_list_reports_all_connected_runtimes(self):
        account = await self.service.create("在线账号")
        second = self.registry.get_runtime(account["id"])
        self.default_runtime.is_running = self.default_runtime.is_connected = True
        second.is_running = second.is_connected = True

        listed = self.service.list_accounts()

        self.assertEqual({item["id"] for item in listed if item["connected"]}, {
            "default",
            account["id"],
        })

    async def test_selected_connection_state_is_independent_from_global_online_state(self):
        account = await self.service.create("离线账号")
        self.default_runtime.is_running = self.default_runtime.is_connected = True
        self.store.set_active("default")
        self.assertTrue(self.registry.is_connected)

        await self.service.activate(account["id"])

        self.assertFalse(self.registry.is_connected)
        self.assertTrue(self.registry.is_account_connected("default"))

    async def test_one_account_start_failure_does_not_block_other_accounts(self):
        Path(f"{self.store.session_name('default')}.session").touch()
        account = self.store.create("可用账号")
        self.store.update_identity(account.id, {"telegram_user_id": 456})
        session_path = Path(f"{self.store.session_name(account.id)}.session")
        session_path.parent.mkdir(parents=True, exist_ok=True)
        session_path.touch()
        second = self.registry.ensure_runtime(account.id)

        async def fail_start():
            raise RuntimeError("connection failed")

        self.default_runtime.start = fail_start

        started = await self.registry.start()

        self.assertTrue(started)
        self.assertFalse(self.default_runtime.is_running)
        self.assertTrue(second.is_running)

    async def test_delete_keeps_registry_record_when_session_cleanup_fails(self):
        account = await self.service.create("待删除账号")

        with patch.object(
            TelegramClientManager,
            "clear_session_files",
            side_effect=OSError("permission denied"),
        ), self.assertRaises(OSError):
            await self.service.delete(account["id"])

        self.assertEqual(self.store.get_public(account["id"])["label"], "待删除账号")
        self.assertFalse(self.registry.is_account_blocked(account["id"]))
        self.assertEqual(self.registry.ensure_runtime(account["id"]).account_id, account["id"])

    async def test_blocked_account_cannot_be_recreated_during_deletion(self):
        account = await self.service.create("删除中账号")
        self.registry.block_account(account["id"])
        self.addCleanup(self.registry.unblock_account, account["id"])

        with self.assertRaises(TelegramAccountError) as raised:
            self.registry.ensure_runtime(account["id"])

        self.assertEqual(raised.exception.code, "account_unavailable")


if __name__ == "__main__":
    unittest.main()
