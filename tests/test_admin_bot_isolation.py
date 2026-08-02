import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from backend.account_paths import AccountPathRegistry
from backend.application import AccountScopeRegistry, ApplicationContext
from backend.bot_commands import AdminBotManager
from backend.config import AccountConfigRegistry, Config
from backend.telegram_accounts import TelegramAccountStore


class FakeEvent:
    def __init__(self, raw_text: str):
        self.raw_text = raw_text
        self.replies = []

    async def reply(self, message=None, **kwargs):
        self.replies.append({"message": message, **kwargs})


class FakeStats:
    def __init__(self):
        self.deleted = []
        self.renamed = []

    def delete_rule(self, name):
        self.deleted.append(name)

    def rename_rule(self, old_name, new_name):
        self.renamed.append((old_name, new_name))

    def query_history(self, **kwargs):
        return [], 0


class FakeStatsRegistry:
    def __init__(self):
        self.databases = {}

    def for_account(self, account_id):
        return self.databases.setdefault(account_id, FakeStats())


class FakeRuntime:
    def __init__(self, account_id, bot_token=None, session_type=None):
        self.account_id = account_id
        self.bot_token = bot_token
        self.session_type = session_type
        self.is_running = False
        self.is_connected = False

    async def start(self):
        self.is_running = True
        return True

    async def stop(self):
        self.is_running = False
        return True

    async def restart(self):
        self.is_running = True
        return True


class FakeRuntimeRegistry:
    def __init__(self):
        self.loop = None
        self.runtimes = {}
        self.started = []
        self.stopped = []
        self.reset = []

    def account_kind(self, account_id):
        return str(self.account_store.get_public(account_id).get("kind") or "user")

    def get_runtime(self, account_id):
        return self.runtimes.setdefault(account_id, FakeRuntime(account_id))

    def get_status(self, account_id=None):
        runtime = self.get_runtime(account_id)
        return {
            "is_running": runtime.is_running,
            "is_connected": runtime.is_connected,
            "stats": {"forwarded": 0, "filtered": 0, "total": 0},
        }

    async def start_account(self, account_id):
        self.started.append(account_id)
        return await self.get_runtime(account_id).start()

    async def stop_account(self, account_id):
        self.stopped.append(account_id)
        return await self.get_runtime(account_id).stop()

    def reset_stats(self, account_id=None):
        self.reset.append(account_id)


class AdminBotIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        root = Path(self.temporary_directory.name)
        self.paths = AccountPathRegistry(
            config_dir=root / "config",
            data_dir=root / "data",
        )
        self.paths.config_dir.mkdir()
        self.paths.data_dir.mkdir()
        template = self.paths.config_dir / "template.yaml"
        template.write_text("forwarding_rules: []\n", encoding="utf-8")
        self.base_config = Config(
            env_file=str(root / "missing.env"),
            config_file=str(template),
        )
        self.configs = AccountConfigRegistry(self.base_config, paths=self.paths)
        self.stats = FakeStatsRegistry()
        self.store = TelegramAccountStore(self.paths.data_dir, paths=self.paths)
        first = self.store.finalize_identity(
            self.store.active_account_id,
            {"telegram_user_id": 101},
        )
        pending = self.store.create("Second")
        second = self.store.finalize_identity(pending.id, {"telegram_user_id": 202})
        self.first_id = first.id
        self.second_id = second.id
        self.store.set_active(self.first_id)
        self.runtimes = FakeRuntimeRegistry()
        self.runtimes.loop = asyncio.get_running_loop()
        self.runtimes.account_store = self.store
        self.account_registry = AccountScopeRegistry(
            self.configs,
            self.stats,
            self.runtimes,
            self.paths,
        )
        self.context = ApplicationContext(
            config=self.base_config,
            bot=self.runtimes,
            exports=SimpleNamespace(),
            scheduler=SimpleNamespace(),
            rules=SimpleNamespace(),
            events=SimpleNamespace(),
            log_handler=SimpleNamespace(),
            accounts=SimpleNamespace(store=self.store),
            account_registry=self.account_registry,
        )
        self.manager = AdminBotManager(self.base_config, self.runtimes, self.context)

    async def test_rule_commands_only_mutate_captured_account(self):
        first_config = self.configs.for_account(self.first_id)
        second_config = self.configs.for_account(self.second_id)
        first_config.update(
            {"forwarding_rules": [{"name": "first", "enabled": False}]}
        )
        second_config.update(
            {"forwarding_rules": [{"name": "second", "enabled": False}]}
        )
        event = FakeEvent("/rule toggle first")

        await self.manager._run_account_command(event, self.manager._handle_rule_cmd)

        self.assertTrue(first_config.get_forwarding_rules()[0].enabled)
        self.assertFalse(second_config.get_forwarding_rules()[0].enabled)

    async def test_stats_and_runtime_commands_target_current_account(self):
        stats_event = FakeEvent("/stats reset")
        start_event = FakeEvent("/bot start")

        await self.manager._run_account_command(stats_event, self.manager._handle_stats_cmd)
        await self.manager._run_account_command(start_event, self.manager._handle_bot_cmd)

        self.assertEqual(self.runtimes.reset, [self.first_id])
        self.assertEqual(self.runtimes.started, [self.first_id])
        self.assertFalse(self.runtimes.get_runtime(self.second_id).is_running)

    async def test_config_export_uses_current_account_file(self):
        self.configs.for_account(self.first_id)
        event = FakeEvent("/config export")

        await self.manager._run_account_command(event, self.manager._handle_config_cmd)

        self.assertEqual(event.replies[0]["file"], str(self.paths.config_dir / "101.yaml"))

    async def test_pending_account_cannot_access_account_resources(self):
        pending = self.store.create("Pending")
        event = FakeEvent("/rule list")

        await self.manager._run_account_command(event, self.manager._handle_rule_cmd)

        self.assertEqual(len(event.replies), 1)
        self.assertFalse((self.paths.config_dir / f"{pending.id}.yaml").exists())
        self.assertFalse((self.paths.data_dir / pending.id).exists())


if __name__ == "__main__":
    unittest.main()
