import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from backend.account_paths import AccountPathRegistry
from backend.account_migration import AccountMigration
from backend.application import AccountScopeRegistry
from backend.config import AccountConfigRegistry, Config
from backend.stats_db import AccountStatsRegistry
from backend.telegram_accounts import TelegramAccountError, TelegramAccountStore
from backend.telegram_runtimes import TelegramRuntimeRegistry


class FakeRuntime:
    def __init__(
        self,
        config,
        auth_manager,
        session_name,
        queue_db_path,
        account_id,
        stats_db=None,
        bot_token=None,
        session_type=None,
    ):
        self.config = config
        self.auth_manager = auth_manager
        self.session_name = Path(session_name)
        self.queue_db_path = Path(queue_db_path)
        self.account_id = account_id
        self.stats_db = stats_db
        self.is_running = False
        self.is_connected = False
        self.events = None
        self.on_user_authenticated = None
        self.forwarders = []

    def bind_loop(self, loop):
        self.loop = loop


class AccountIsolationTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.config_dir = self.root / "config"
        self.data_dir = self.root / "data"
        self.config_dir.mkdir()
        self.data_dir.mkdir()
        self.paths = AccountPathRegistry(
            config_dir=self.config_dir,
            data_dir=self.data_dir,
        )

    def _write_legacy_registry(self, telegram_user_id=123) -> None:
        (self.data_dir / "telegram_accounts.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "active_account_id": "default",
                    "accounts": [
                        {
                            "id": "default",
                            "label": "Legacy",
                            "telegram_user_id": telegram_user_id,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

    def test_default_migration_moves_all_shared_data_and_is_idempotent(self):
        self._write_legacy_registry()
        files = {
            self.config_dir / "config.yaml": b"forwarding_rules: []\n",
            self.data_dir / "telegram_session.session": b"session",
            self.data_dir / "telegram_session.session-journal": b"journal",
            self.data_dir / "forward_queue.db": b"queue",
            self.data_dir / "forward_queue.db-wal": b"queue-wal",
            self.data_dir / "stats.db": b"stats",
            self.data_dir / "exports.db": b"exports-db",
            self.data_dir / "telegram_avatars" / "default.jpg": b"avatar",
            self.data_dir / "db" / "messages.sqlite3": b"messages",
            self.data_dir / "exports" / "archive.zip": b"archive",
        }
        for path, content in files.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)

        migration = AccountMigration(self.paths)
        self.assertTrue(migration.run())
        store = TelegramAccountStore(self.data_dir, paths=self.paths)
        target = self.paths.for_account("123")

        self.assertEqual(store.active_account_id, "123")
        self.assertEqual(target.config_file.read_bytes(), files[self.config_dir / "config.yaml"])
        self.assertEqual(Path(f"{target.session_name}.session").read_bytes(), b"session")
        self.assertEqual(Path(f"{target.session_name}.session-journal").read_bytes(), b"journal")
        self.assertEqual(Path(f"{target.queue_db}-wal").read_bytes(), b"queue-wal")
        self.assertEqual(target.stats_db.read_bytes(), b"stats")
        self.assertEqual(target.exports_db.read_bytes(), b"exports-db")
        self.assertEqual((target.message_db_dir / "messages.sqlite3").read_bytes(), b"messages")
        self.assertEqual((target.export_dir / "archive.zip").read_bytes(), b"archive")
        self.assertEqual(target.avatar.read_bytes(), b"avatar")
        self.assertFalse((self.data_dir / "telegram_preview_cache").exists())

        restored = TelegramAccountStore(self.data_dir, paths=self.paths)
        self.assertEqual(restored.active_account_id, "123")
        self.assertEqual(target.stats_db.read_bytes(), b"stats")

    def test_migration_never_overwrites_conflicting_destination(self):
        self._write_legacy_registry()
        source = self.config_dir / "config.yaml"
        destination = self.paths.for_account("123").config_file
        source.write_text("source: true\n", encoding="utf-8")
        destination.write_text("destination: true\n", encoding="utf-8")

        migration = AccountMigration(self.paths)
        self.assertTrue(migration.run())
        TelegramAccountStore(self.data_dir, paths=self.paths)

        self.assertEqual(source.read_text(encoding="utf-8"), "source: true\n")
        self.assertEqual(destination.read_text(encoding="utf-8"), "destination: true\n")

    def test_sqlite_conflict_keeps_legacy_database_and_sidecars_together(self):
        self._write_legacy_registry()
        source = self.data_dir / "forward_queue.db"
        source_wal = Path(f"{source}-wal")
        destination = self.paths.for_account("123").queue_db
        destination_wal = Path(f"{destination}-wal")
        source.write_bytes(b"legacy-database")
        source_wal.write_bytes(b"legacy-wal")
        destination.parent.mkdir(parents=True)
        destination.write_bytes(b"isolated-database")

        self.assertTrue(AccountMigration(self.paths).run())

        self.assertEqual(source.read_bytes(), b"legacy-database")
        self.assertEqual(source_wal.read_bytes(), b"legacy-wal")
        self.assertEqual(destination.read_bytes(), b"isolated-database")
        self.assertFalse(destination_wal.exists())

    def test_pending_account_only_persists_global_registry(self):
        store = TelegramAccountStore(self.data_dir, paths=self.paths)
        pending = store.create("Pending")

        self.assertFalse(pending.id.isdigit())
        self.assertEqual(
            sorted(path.name for path in self.data_dir.iterdir()),
            ["telegram_accounts.json"],
        )
        self.assertEqual(list(self.config_dir.iterdir()), [])

    def test_adopt_session_moves_main_database_and_sidecars(self):
        temporary_session = self.root / "pending" / "telegram"
        source = Path(f"{temporary_session}.session")
        source_wal = Path(f"{source}-wal")
        source.parent.mkdir()
        source.write_bytes(b"session")
        source_wal.write_bytes(b"wal")

        self.assertTrue(self.paths.adopt_session(temporary_session, "123"))

        destination = Path(f"{self.paths.for_account('123').session_name}.session")
        self.assertEqual(destination.read_bytes(), b"session")
        self.assertEqual(Path(f"{destination}-wal").read_bytes(), b"wal")
        self.assertFalse(source.exists())
        self.assertFalse(source_wal.exists())

    def test_adopt_session_conflict_leaves_temporary_session_intact(self):
        temporary_session = self.root / "pending" / "telegram"
        source = Path(f"{temporary_session}.session")
        source_journal = Path(f"{source}-journal")
        source.parent.mkdir()
        source.write_bytes(b"pending-session")
        source_journal.write_bytes(b"pending-journal")
        destination = Path(f"{self.paths.for_account('123').session_name}.session")
        destination.parent.mkdir(parents=True)
        destination.write_bytes(b"existing-session")

        self.assertFalse(self.paths.adopt_session(temporary_session, "123"))

        self.assertEqual(source.read_bytes(), b"pending-session")
        self.assertEqual(source_journal.read_bytes(), b"pending-journal")
        self.assertEqual(destination.read_bytes(), b"existing-session")
        self.assertFalse(Path(f"{destination}-journal").exists())

    def test_config_stats_and_export_stores_are_isolated(self):
        template_path = self.config_dir / "template.yaml"
        template_path.write_text("forwarding_rules: []\n", encoding="utf-8")
        base = Config(
            env_file=str(self.root / "missing.env"),
            config_file=str(template_path),
        )
        configs = AccountConfigRegistry(base, paths=self.paths)
        stats = AccountStatsRegistry(paths=self.paths)
        first = configs.for_account("101")
        second = configs.for_account("202")
        first.update({"forwarding_rules": [{"name": "first"}]})
        stats.for_account("101").increment_forwarded("first")

        self.assertEqual(second.get_forwarding_rules(), [])
        self.assertEqual(stats.for_account("202").get_all_stats(), {})
        self.assertEqual(first.config_file, str(self.config_dir / "101.yaml"))
        self.assertEqual(second.export_root_dir, str(self.data_dir / "202" / "exports"))

        runtimes = SimpleNamespace(
            get_runtime=lambda account_id: SimpleNamespace(
                account_id=account_id,
                is_connected=False,
            ),
            account_store=SimpleNamespace(list_public=list),
            account_kind=lambda account_id: "user",
        )
        registry = AccountScopeRegistry(configs, stats, runtimes, self.paths)
        self.addCleanup(registry.shutdown)
        first_exports = registry.for_account("101").exports
        second_exports = registry.for_account("202").exports
        first_exports.store.start_run(task_id=None, run_type="groups")

        self.assertEqual(len(first_exports.list_runs()), 1)
        self.assertEqual(second_exports.list_runs(), [])
        self.assertEqual(first_exports.store.db_path, self.data_dir / "101" / "exports.db")
        self.assertEqual(second_exports.store.db_path, self.data_dir / "202" / "exports.db")

    def test_account_configs_record_session_type(self):
        template_path = self.config_dir / "template.yaml"
        template_path.write_text("forwarding_rules: []\n", encoding="utf-8")
        store = TelegramAccountStore(self.data_dir, paths=self.paths)
        user = store.finalize_identity(store.active_account_id, {"telegram_user_id": 101})
        bot = store.finalize_identity(
            store.seed_bot("123456789:AA" + "x" * 30).id,
            {"telegram_user_id": 123456789},
        )
        base = Config(
            env_file=str(self.root / "missing.env"),
            config_file=str(template_path),
        )
        configs = AccountConfigRegistry(base, paths=self.paths, account_store=store)

        user_config = configs.for_account(user.id)
        bot_config = configs.for_account(bot.id)

        self.assertEqual(user_config.config_data.get("session_type"), "user")
        self.assertEqual(bot_config.config_data.get("session_type"), "bot")
        persisted = (self.config_dir / f"{bot.id}.yaml").read_text(encoding="utf-8")
        self.assertIn("session_type: bot", persisted)

        # A pre-existing config without session_type is patched on load.
        legacy_user_path = self.config_dir / f"{user.id}.yaml"
        legacy_user_path.write_text(
            "forwarding_rules: []\nforward_queue:\n  db_path: data/101/forward_queue.db\n",
            encoding="utf-8",
        )
        reloaded = AccountConfigRegistry(base, paths=self.paths, account_store=store)
        self.assertEqual(reloaded.for_account(user.id).config_data.get("session_type"), "user")
        self.assertIn("session_type: user", legacy_user_path.read_text(encoding="utf-8"))

    def test_runtime_receives_account_specific_dependencies(self):
        template = self.config_dir / "template.yaml"
        template.write_text("forwarding_rules: []\n", encoding="utf-8")
        store = TelegramAccountStore(self.data_dir, paths=self.paths)
        first = store.finalize_identity(store.active_account_id, {"telegram_user_id": 101})
        second_pending = store.create("Second")
        second = store.finalize_identity(second_pending.id, {"telegram_user_id": 202})
        base = Config(config_file=str(template), env_file=str(self.root / "missing.env"))
        configs = AccountConfigRegistry(base, paths=self.paths)
        stats = AccountStatsRegistry(paths=self.paths)
        runtimes = TelegramRuntimeRegistry(
            base,
            store,
            bot_factory=FakeRuntime,
            config_registry=configs,
            stats_registry=stats,
            paths=self.paths,
        )
        first_runtime = runtimes.ensure_runtime(first.id)
        second_runtime = runtimes.ensure_runtime(second.id)

        self.assertIsNot(first_runtime.config, second_runtime.config)
        self.assertIsNot(first_runtime.stats_db, second_runtime.stats_db)
        self.assertEqual(first_runtime.queue_db_path, self.data_dir / "101" / "forward_queue.db")
        self.assertEqual(second_runtime.session_name, self.data_dir / "202" / "telegram")

    def test_account_label_can_be_changed_but_must_remain_unique(self):
        store = TelegramAccountStore(self.data_dir, paths=self.paths)
        first_id = store.active_account_id
        second = store.create("Second")

        updated = store.update_label(first_id, "Primary")

        self.assertEqual(updated.label, "Primary")
        with self.assertRaises(TelegramAccountError) as raised:
            store.update_label(second.id, "primary")
        self.assertEqual(raised.exception.code, "duplicate_account_label")


if __name__ == "__main__":
    unittest.main()
