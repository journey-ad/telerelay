import json
import tempfile
import unittest
from pathlib import Path

from backend.auth_manager import AuthManager
from backend.telegram_accounts import (
    TelegramAccountError,
    TelegramAccountService,
    TelegramAccountStore,
)


class FakeBot:
    def __init__(self, session_name: Path):
        self.session_name = session_name
        self.is_running = False
        self.is_connected = False
        self.actions: list[tuple[str, str]] = []

    async def start(self) -> bool:
        self.actions.append(("start", str(self.session_name)))
        self.is_running = True
        return True

    async def stop(self) -> bool:
        self.actions.append(("stop", str(self.session_name)))
        self.is_running = False
        self.is_connected = False
        return True

    def set_session_name(self, session_name: Path) -> None:
        if self.is_running:
            raise RuntimeError("session changed before runtime stopped")
        self.session_name = Path(session_name)
        self.actions.append(("select", str(self.session_name)))


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
        bot = FakeBot(store.active_session_name)
        service = TelegramAccountService(store, bot, AuthManager(input_timeout=1))

        service.update_active_identity(
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
        self.bot = FakeBot(self.store.active_session_name)
        self.auth = AuthManager(input_timeout=1)
        self.service = TelegramAccountService(self.store, self.bot, self.auth)

    async def test_create_stops_runtime_before_selecting_new_session(self):
        self.bot.is_running = True

        account = await self.service.create("新账号")

        self.assertEqual([action for action, _ in self.bot.actions], ["stop", "select"])
        self.assertEqual(account["id"], self.store.active_account_id)
        self.assertFalse(self.bot.is_running)

    async def test_activate_authenticated_account_stops_selects_and_starts(self):
        new_account = self.store.create("已登录账号")
        self.store.update_identity(new_account.id, {"telegram_user_id": 456})
        Path(f"{self.store.session_name(new_account.id)}.session").parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        Path(f"{self.store.session_name(new_account.id)}.session").touch()
        self.store.set_active("default")
        self.bot.is_running = True

        await self.service.activate(new_account.id)

        self.assertEqual(
            [action for action, _ in self.bot.actions],
            ["stop", "select", "start"],
        )
        self.assertEqual(self.store.active_account_id, new_account.id)

    async def test_duplicate_label_does_not_stop_active_runtime(self):
        self.bot.is_running = True

        with self.assertRaises(TelegramAccountError):
            await self.service.create("Telegram 账号")

        self.assertEqual(self.bot.actions, [])
        self.assertTrue(self.bot.is_running)

    async def test_deleting_last_account_does_not_stop_active_runtime(self):
        self.bot.is_running = True

        with self.assertRaises(TelegramAccountError):
            await self.service.delete("default")

        self.assertEqual(self.bot.actions, [])
        self.assertTrue(self.bot.is_running)

    async def test_activate_unauthenticated_account_does_not_start(self):
        new_account = self.store.create("待登录账号")
        self.store.set_active("default")

        await self.service.activate(new_account.id)

        self.assertEqual([action for action, _ in self.bot.actions], ["select"])
        self.assertFalse(self.bot.is_running)


if __name__ == "__main__":
    unittest.main()
