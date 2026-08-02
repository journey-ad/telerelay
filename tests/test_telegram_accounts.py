import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend.account_paths import AccountPathRegistry
from backend.telegram_accounts import (
    TelegramAccountError,
    TelegramAccountService,
    TelegramAccountStore,
)
from backend.account_migration import AccountMigration
from backend.telegram_runtimes import TelegramRuntimeRegistry


class FakeRuntime:
    def __init__(
        self,
        config,
        auth_manager,
        session_name,
        queue_db_path,
        account_id,
        bot_token=None,
        session_type=None,
    ):
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

    async def reload_rules(self) -> bool:
        self.actions.append(("reload_rules", str(self.session_name)))
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

    def test_default_account_migrates_to_telegram_user_id(self):
        (self.root / "telegram_accounts.json").write_text(json.dumps({
            "version": 1,
            "active_account_id": "default",
            "accounts": [{
                "id": "default",
                "label": "Legacy",
                "telegram_user_id": 123,
            }],
        }))
        (self.root / "telegram_session.session").touch()
        config_dir = self.root / "config"
        config_dir.mkdir()
        paths = AccountPathRegistry(data_dir=self.root, config_dir=config_dir)
        AccountMigration(paths).run()
        store = TelegramAccountStore(self.root, paths=paths)

        account = store.list_public()[0]

        self.assertEqual(account["id"], "123")
        self.assertTrue(account["authenticated"])
        self.assertEqual(store.active_session_name, self.root / "123" / "telegram")
        self.assertFalse((self.root / "telegram_session.session").exists())

    def test_registry_round_trip_and_identity_update(self):
        store = TelegramAccountStore(self.root)
        account = store.create("工作账号")
        account = store.finalize_identity(
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

        account_id = store.active_account_id
        with self.assertRaises(TelegramAccountError) as raised:
            store.delete(account_id)

        self.assertEqual(raised.exception.code, "last_account")

    def test_clear_identity_marks_new_account_unauthenticated(self):
        store = TelegramAccountStore(self.root)
        account = store.create("工作账号")
        account = store.finalize_identity(account.id, {"telegram_user_id": 123})

        store.clear_identity(account.id)

        self.assertFalse(store.get_public(account.id)["authenticated"])

    def test_finalized_account_rejects_a_different_telegram_identity(self):
        store = TelegramAccountStore(self.root)
        account = store.finalize_identity(
            store.active_account_id,
            {"telegram_user_id": 123},
        )

        with self.assertRaises(TelegramAccountError) as raised:
            store.finalize_identity(account.id, {"telegram_user_id": 456})

        self.assertEqual(raised.exception.code, "telegram_account_mismatch")
        self.assertEqual(store.get_public(account.id)["telegram_user_id"], 123)

    def test_avatar_cache_is_versioned_and_can_be_cleared(self):
        store = TelegramAccountStore(self.root)
        account = store.finalize_identity(
            store.active_account_id,
            {"telegram_user_id": 123},
        )

        store.update_avatar(account.id, b"first-avatar")

        public = store.get_public(account.id)
        self.assertIsNotNone(public["avatar_version"])
        self.assertEqual(store.get_avatar_path(account.id).read_bytes(), b"first-avatar")

        store.update_avatar(account.id, None)

        self.assertIsNone(store.get_avatar_path(account.id))
        self.assertIsNone(store.get_public(account.id)["avatar_version"])

    def test_identity_callback_updates_avatar_when_payload_includes_it(self):
        store = TelegramAccountStore(self.root)
        service = TelegramAccountService(store, make_registry(store))

        pending_id = store.active_account_id
        service.update_identity(
            pending_id,
            {
                "display_name": "Avatar User",
                "telegram_user_id": 789,
                "avatar_bytes": b"avatar-bytes",
            }
        )

        self.assertEqual(store.get_avatar_path("789").read_bytes(), b"avatar-bytes")

    def test_identity_update_publishes_account_and_auth_events(self):
        from backend.events import EventBus

        store = TelegramAccountStore(self.root)
        events = EventBus()
        registry = TelegramRuntimeRegistry(
            SimpleNamespace(
                forward_queue_db_path=str(store.data_dir / "forward_queue.db")
            ),
            store,
            auth_timeout=1,
            bot_factory=FakeRuntime,
            events=events,
        )
        service = TelegramAccountService(store, registry)

        service.update_identity(
            store.active_account_id,
            {"display_name": "User", "telegram_user_id": 1},
        )

        auth_events = events.recent(10, {"telegram-auth"})
        self.assertEqual(auth_events[0]["payload"]["state"], "success")
        self.assertEqual(auth_events[0]["payload"]["account_id"], "1")
        self.assertIn(
            "telegram-account",
            {event["type"] for event in events.recent(10)},
        )

    def test_auth_state_changes_publish_events(self):
        from backend.events import EventBus

        store = TelegramAccountStore(self.root)
        events = EventBus()
        registry = TelegramRuntimeRegistry(
            SimpleNamespace(
                forward_queue_db_path=str(store.data_dir / "forward_queue.db")
            ),
            store,
            auth_timeout=1,
            bot_factory=FakeRuntime,
            events=events,
        )

        account_id = store.active_account_id
        auth = registry.get_auth(account_id)
        auth.set_state("waiting_phone")

        event = events.recent(1, {"telegram-auth"})[0]
        self.assertEqual(event["payload"]["state"], "waiting_phone")
        self.assertEqual(event["payload"]["account_id"], account_id)


class TelegramAccountServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.store = TelegramAccountStore(self.root)
        primary = self.store.finalize_identity(
            self.store.active_account_id,
            {"telegram_user_id": 100},
        )
        Path(f"{self.store.session_name(primary.id)}.session").parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        Path(f"{self.store.session_name(primary.id)}.session").touch()
        self.registry = make_registry(self.store)
        self.service = TelegramAccountService(self.store, self.registry)
        self.primary_id = primary.id
        self.default_runtime = self.registry.ensure_runtime(self.primary_id)

    async def test_create_keeps_existing_runtime_running(self):
        self.default_runtime.is_running = True

        account = await self.service.create("新账号")

        self.assertTrue(self.default_runtime.is_running)
        self.assertEqual(account["id"], self.store.active_account_id)
        self.assertEqual(self.registry.ensure_runtime(account["id"]).actions, [])

    async def test_refresh_identity_updates_user_and_bot_avatars(self):
        self.registry.on_user_authenticated = self.service.update_identity
        bot = self.store.create("Avatar Bot", kind="bot")
        self.store.set_bot_token(bot.id, "123456789:AA" + "x" * 30)
        bot = self.store.finalize_identity(bot.id, {"telegram_user_id": 200})
        Path(f"{self.store.session_name(bot.id)}.session").parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        Path(f"{self.store.session_name(bot.id)}.session").touch()

        for account_id, display_name, avatar_bytes in (
            (self.primary_id, "Updated User", b"user-avatar"),
            (bot.id, "Updated Bot", b"bot-avatar"),
        ):
            runtime = self.registry.ensure_runtime(account_id)

            async def refresh_identity(
                target_runtime=runtime,
                identity={
                    "display_name": display_name,
                    "telegram_user_id": int(account_id),
                    "avatar_bytes": avatar_bytes,
                },
            ):
                target_runtime.on_user_authenticated(identity)
                return identity

            runtime.refresh_identity = refresh_identity
            refreshed = await self.service.refresh_identity(account_id)

            self.assertEqual(refreshed["display_name"], display_name)
            self.assertEqual(
                self.store.get_avatar_path(account_id).read_bytes(),
                avatar_bytes,
            )

    async def test_bot_authentication_does_not_block_other_account_mutations(self):
        authentication_started = asyncio.Event()
        release_authentication = asyncio.Event()

        class BlockingClientManager:
            def __init__(
                self,
                config,
                auth_manager=None,
                session_name=None,
                on_user_authenticated=None,
                bot_token=None,
            ):
                self.session_name = Path(session_name)
                self.on_user_authenticated = on_user_authenticated

            async def connect(self):
                authentication_started.set()
                await release_authentication.wait()
                Path(f"{self.session_name}.session").write_bytes(b"fake-session")
                if self.on_user_authenticated:
                    self.on_user_authenticated(
                        {
                            "display_name": "Parallel Bot",
                            "telegram_user_id": 200,
                        }
                    )
                return True

            async def disconnect(self):
                return None

        with patch(
            "backend.telegram_accounts.TelegramClientManager",
            BlockingClientManager,
        ):
            creation = asyncio.create_task(
                self.service.create(
                    "并行 Bot",
                    kind="bot",
                    bot_token="123456789:AA" + "x" * 30,
                )
            )
            await authentication_started.wait()
            try:
                activated = await asyncio.wait_for(
                    self.service.activate(self.primary_id),
                    timeout=0.2,
                )
            finally:
                release_authentication.set()
            created = await creation

        self.assertEqual(activated["id"], self.primary_id)
        self.assertEqual(created["id"], "200")

    async def test_activate_authenticated_account_does_not_stop_or_start_any_runtime(self):
        new_account = self.store.create("已登录账号")
        new_account = self.store.finalize_identity(new_account.id, {"telegram_user_id": 456})
        Path(f"{self.store.session_name(new_account.id)}.session").parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        Path(f"{self.store.session_name(new_account.id)}.session").touch()
        self.store.set_active(self.primary_id)
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
            await self.service.delete(self.primary_id)

        self.assertEqual(self.default_runtime.actions, [])
        self.assertTrue(self.default_runtime.is_running)

    async def test_activate_unauthenticated_account_does_not_start(self):
        new_account = self.store.create("待登录账号")
        self.store.set_active(self.primary_id)

        await self.service.activate(new_account.id)

        self.assertEqual(self.store.active_account_id, new_account.id)
        self.assertFalse(self.registry.ensure_runtime(new_account.id).is_running)

    async def test_delete_stops_only_the_deleted_runtime(self):
        account = self.store.create("并行账号")
        account = self.store.finalize_identity(account.id, {"telegram_user_id": 123})
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
        account = self.store.create("第二账号")
        account = self.store.finalize_identity(account.id, {"telegram_user_id": 456})
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
            self.root / "forward_queues" / f"account_{self.primary_id}.db",
        )
        self.assertEqual(
            second.queue_db_path,
            self.root / "forward_queues" / f"account_{account.id}.db",
        )

    async def test_rule_reload_only_fans_out_to_running_accounts(self):
        account = self.store.create("在线账号")
        online = self.registry.ensure_runtime(account.id)
        self.default_runtime.is_running = True
        online.is_running = True
        offline_account = self.store.create("离线账号")
        offline = self.registry.ensure_runtime(offline_account.id)

        reloaded = await self.registry.reload_rules()

        self.assertTrue(reloaded)
        self.assertEqual(self.default_runtime.actions[0][0], "reload_rules")
        self.assertEqual(online.actions[0][0], "reload_rules")
        self.assertEqual(offline.actions, [])

    async def test_identity_callback_is_bound_to_originating_account(self):
        account = self.store.create("登录中账号")
        runtime = self.registry.ensure_runtime(account.id)
        self.store.set_active(self.primary_id)
        self.registry.on_user_authenticated = self.service.update_identity

        runtime.on_user_authenticated(
            {
                "display_name": "Parallel User",
                "telegram_user_id": 9001,
            }
        )

        self.assertEqual(self.store.get_public(account.id)["display_name"], "Parallel User")
        self.assertEqual(self.store.get_public(self.primary_id)["display_name"], "")

    async def test_each_account_has_an_independent_auth_manager(self):
        account = await self.service.create("独立认证账号")

        self.assertIsNot(
            self.registry.get_auth(self.primary_id),
            self.registry.get_auth(account["id"]),
        )

    async def test_cleared_numeric_account_reauthenticates_in_temporary_session(self):
        session_path = Path(f"{self.store.session_name(self.primary_id)}.session")
        session_path.unlink()

        with patch.object(
            self.service,
            "_authenticate_pending",
            return_value=None,
        ) as authenticate:
            started = await self.service.start_authentication(self.primary_id)
            await asyncio.sleep(0)

        self.assertTrue(started)
        authenticate.assert_called_once()
        pending = authenticate.call_args.args[0]
        self.assertEqual(pending.account_id, self.primary_id)
        self.assertNotEqual(pending.session_name, self.store.session_name(self.primary_id))

    async def test_account_list_reports_all_connected_runtimes(self):
        account = await self.service.create("在线账号")
        second = self.registry.get_runtime(account["id"])
        self.default_runtime.is_running = self.default_runtime.is_connected = True
        second.is_running = second.is_connected = True

        listed = self.service.list_accounts()

        self.assertEqual({item["id"] for item in listed if item["connected"]}, {
            self.primary_id,
            account["id"],
        })

    async def test_selected_connection_state_is_independent_from_global_online_state(self):
        account = await self.service.create("离线账号")
        self.default_runtime.is_running = self.default_runtime.is_connected = True
        self.store.set_active(self.primary_id)
        self.assertTrue(self.registry.is_connected)

        await self.service.activate(account["id"])

        self.assertFalse(self.registry.is_connected)
        self.assertTrue(self.registry.is_account_connected(self.primary_id))

    async def test_one_account_start_failure_does_not_block_other_accounts(self):
        account = self.store.create("可用账号")
        account = self.store.finalize_identity(account.id, {"telegram_user_id": 456})
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
        pending = await self.service.create("待删除账号")
        account = self.store.finalize_identity(
            pending["id"],
            {"telegram_user_id": 999},
        )
        self.registry.ensure_runtime(account.id)

        with patch.object(
            self.store.paths,
            "remove_account_data",
            side_effect=OSError("permission denied"),
        ), self.assertRaises(OSError):
            await self.service.delete(account.id)

        self.assertFalse(self.registry.is_account_blocked(account.id))
        self.assertEqual(self.store.get_public(account.id)["id"], account.id)
        restored = TelegramAccountStore(self.root)
        self.assertEqual(restored.get_public(account.id)["id"], account.id)

    async def test_blocked_account_cannot_be_recreated_during_deletion(self):
        account = await self.service.create("删除中账号")
        self.registry.block_account(account["id"])
        self.addCleanup(self.registry.unblock_account, account["id"])

        with self.assertRaises(TelegramAccountError) as raised:
            self.registry.ensure_runtime(account["id"])

        self.assertEqual(raised.exception.code, "account_unavailable")


class BotAccountStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)

    def test_bot_token_is_stored_outside_public_metadata_and_removed_on_delete(self):
        store = TelegramAccountStore(self.root)
        account = store.create("Relay Bot", kind="bot")
        store.set_bot_token(account.id, "123456789:AA" + "x" * 30)

        self.assertEqual(store.get_bot_token(account.id), "123456789:AA" + "x" * 30)
        self.assertNotIn("bot_token", store.get_public(account.id))
        self.assertEqual(store.get_public(account.id)["kind"], "bot")

        store.delete(account.id)
        self.assertFalse(
            (store.data_dir / "bot_tokens" / f"{account.id}.token").exists()
        )

    def test_bot_token_follows_account_finalization(self):
        store = TelegramAccountStore(self.root)
        account = store.create("Relay Bot", kind="bot")
        token = "123456789:AA" + "x" * 30
        store.set_bot_token(account.id, token)
        previous_id = account.id

        finalized = store.finalize_identity(
            account.id,
            {"display_name": "Relay Bot", "telegram_user_id": 123456789},
        )

        self.assertEqual(finalized.id, "123456789")
        self.assertEqual(store.get_bot_token(finalized.id), token)
        self.assertFalse(
            (store.data_dir / "bot_tokens" / f"{previous_id}.token").exists()
        )
        self.assertTrue(
            (store.data_dir / "bot_tokens" / f"{finalized.id}.token").is_file()
        )

    def test_bot_token_is_recovered_from_pre_finalization_account_id(self):
        store = TelegramAccountStore(self.root)
        account = store.create("Relay Bot", kind="bot")
        token = "123456789:AA" + "x" * 30
        store.set_bot_token(account.id, token)
        previous_id = account.id
        finalized = store.finalize_identity(
            account.id,
            {"display_name": "Relay Bot", "telegram_user_id": 123456789},
        )
        canonical = store.data_dir / "bot_tokens" / f"{finalized.id}.token"
        orphan = store.data_dir / "bot_tokens" / f"{previous_id}.token"
        canonical.rename(orphan)

        self.assertEqual(store.get_bot_token(finalized.id), token)
        self.assertTrue(canonical.is_file())
        self.assertFalse(orphan.exists())

    def test_orphaned_bot_token_recovery_ignores_other_bots(self):
        store = TelegramAccountStore(self.root)
        account = store.create("Relay Bot", kind="bot")
        token = "123456789:AA" + "x" * 30
        store.set_bot_token(account.id, token)
        previous_id = account.id
        finalized = store.finalize_identity(
            account.id,
            {"display_name": "Relay Bot", "telegram_user_id": 123456789},
        )
        canonical = store.data_dir / "bot_tokens" / f"{finalized.id}.token"
        orphan = store.data_dir / "bot_tokens" / f"{previous_id}.token"
        canonical.rename(orphan)
        store.data_dir.joinpath("bot_tokens", "999999999.token").write_text(
            "999999999:AA" + "z" * 30,
            encoding="utf-8",
        )

        self.assertEqual(store.get_bot_token(finalized.id), token)
        self.assertTrue(canonical.is_file())
        self.assertTrue(store.data_dir.joinpath("bot_tokens", "999999999.token").is_file())

    def test_seed_bot_replaces_placeholder_and_adopts_legacy_session(self):
        legacy = self.root / "telegram_session.session"
        legacy.write_bytes(b"legacy-session")
        store = TelegramAccountStore(self.root)
        self.assertEqual(len(store.list_public()), 1)

        account = store.seed_bot("123456789:AA" + "y" * 30)

        self.assertEqual(store.list_public()[0]["kind"], "bot")
        self.assertEqual(store.get_bot_token(account.id), "123456789:AA" + "y" * 30)
        migrated = Path(f"{store.session_name(account.id)}.session")
        self.assertEqual(migrated.read_bytes(), b"legacy-session")

    def test_seed_bot_restores_missing_token_for_existing_bot(self):
        store = TelegramAccountStore(self.root)
        account = store.create("Relay Bot", kind="bot")
        store.set_bot_token(account.id, "123456789:AA" + "old" + "x" * 27)
        (store.data_dir / "bot_tokens" / f"{account.id}.token").unlink()

        seeded = store.seed_bot("987654321:BB" + "y" * 30)

        self.assertEqual(seeded.id, account.id)
        self.assertEqual(store.get_bot_token(account.id), "987654321:BB" + "y" * 30)

    def test_invalid_bot_token_is_rejected(self):
        store = TelegramAccountStore(self.root)
        with self.assertRaises(TelegramAccountError) as raised:
            store.validate_bot_token("not-a-token")
        self.assertEqual(raised.exception.code, "invalid_bot_token")


if __name__ == "__main__":
    unittest.main()
