"""Runs a previous process left `running` are closed as interrupted."""

import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from backend.account_paths import AccountPathRegistry
from backend.exporter.paths import purge_partial_files
from backend.exporter.registry import AccountExportRegistry
from backend.exporter.store import ExportStore

ACCOUNT_ID = "12345"


def config_for(root: Path):
    return SimpleNamespace(
        export_root_dir=str(root / "exports"),
        export_message_db_dir=str(root / "db"),
        export_concurrency=1,
        export_timezone="Asia/Shanghai",
    )


class InterruptRunningRunsTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.store = ExportStore(self.root / "exports.db", export_root=self.root / "exports")

    def _begin_run(self, run_type: str = "scheduled") -> int:
        return self.store.start_run(
            task_id=None, run_type=run_type, chat_id=-1001, chat_title="News"
        )

    def test_running_rows_become_interrupted_and_keep_their_count(self):
        run_id = self._begin_run()
        self.store.update_run_progress(run_id, 42)

        self.assertEqual(self.store.interrupt_running_runs(), [run_id])

        run = self.store.get_run(run_id)
        self.assertEqual(run.status, "interrupted")
        self.assertEqual(run.message_count, 42)
        self.assertIsNotNone(run.finished_at)

    def test_terminal_rows_are_left_alone(self):
        done = self._begin_run("messages")
        self.store.finish_run(done, status="completed", message_count=7)
        cancelled = self._begin_run("messages")
        self.store.finish_run(cancelled, status="cancelled", message_count=3)
        failed = self._begin_run("messages")
        self.store.finish_run(failed, status="failed", error="boom")

        self.assertEqual(self.store.interrupt_running_runs(), [])

        self.assertEqual(self.store.get_run(done).status, "completed")
        self.assertEqual(self.store.get_run(cancelled).status, "cancelled")
        self.assertEqual(self.store.get_run(failed).status, "failed")

    def test_no_running_rows_reports_nothing(self):
        self.assertEqual(self.store.interrupt_running_runs(), [])

    def test_interrupted_rows_are_not_reported_twice(self):
        run_id = self._begin_run()

        self.assertEqual(self.store.interrupt_running_runs(), [run_id])
        self.assertEqual(self.store.interrupt_running_runs(), [])


class AccountExportRegistryRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.paths = AccountPathRegistry(
            config_dir=self.root / "config", data_dir=self.root / "data"
        )
        account_paths = self.paths.for_account(ACCOUNT_ID)
        account_paths.data_dir.mkdir(parents=True, exist_ok=True)
        self.exports_db = account_paths.exports_db
        store = ExportStore(self.exports_db, export_root=account_paths.export_dir)
        self.orphan_id = store.start_run(
            task_id=None, run_type="scheduled", chat_id=-1001, chat_title="News"
        )
        store.update_run_progress(self.orphan_id, 11)
        done_id = store.start_run(task_id=None, run_type="messages")
        store.finish_run(done_id, status="completed", message_count=4)
        self.done_id = done_id
        store.engine.dispose()
        self.accounts = [{"id": ACCOUNT_ID}]

    def _registry(self) -> AccountExportRegistry:
        runtimes = SimpleNamespace(
            get_runtime=lambda account_id: None,
            account_kind=lambda account_id: "user",
            account_store=SimpleNamespace(list_public=lambda: list(self.accounts)),
        )
        configs = SimpleNamespace(
            for_account=lambda account_id: config_for(self.root / account_id)
        )
        return AccountExportRegistry(configs, runtimes, self.paths)

    def test_start_closes_orphans_before_scheduling(self):
        registry = self._registry()

        async def scenario():
            registry.start()
            try:
                store = registry.for_account(ACCOUNT_ID).store
                orphan = store.get_run(self.orphan_id)
                self.assertEqual(orphan.status, "interrupted")
                self.assertEqual(orphan.message_count, 11)
                self.assertEqual(store.get_run(self.done_id).status, "completed")
            finally:
                registry.shutdown()

        asyncio.run(scenario())

        reopened = ExportStore(self.exports_db)
        self.assertEqual(reopened.get_run(self.orphan_id).status, "interrupted")

    def test_start_skips_accounts_without_a_telegram_id(self):
        self.accounts = [{"id": "pending-uuid"}]
        registry = self._registry()

        async def scenario():
            registry.start()
            try:
                self.assertEqual(registry._services, {})
            finally:
                registry.shutdown()

        asyncio.run(scenario())

        reopened = ExportStore(self.exports_db)
        self.assertEqual(reopened.get_run(self.orphan_id).status, "running")


class PartialExportCleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)

    def _touch(self, relative: str, content: bytes = b"staged") -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def test_staged_files_are_removed_and_finished_files_kept(self):
        document = self._touch("messages/archive.json.part")
        spool = self._touch("messages/archive.html.zip.part.records")
        finished = self._touch("messages/archive.json")
        other = self._touch("scheduled/notes.partial")
        nested = self._touch("custom/deep/archive.csv.part")

        removed, freed = purge_partial_files(self.root)

        self.assertEqual(removed, 3)
        self.assertEqual(freed, len(b"staged") * 3)
        for path in (document, spool, nested):
            self.assertFalse(path.exists())
        self.assertTrue(finished.exists())
        self.assertTrue(other.exists())

    def test_missing_root_is_not_an_error(self):
        self.assertEqual(purge_partial_files(self.root / "absent"), (0, 0))

    def test_directory_named_like_a_staged_file_is_kept(self):
        directory = self.root / "messages" / "archive.json.part"
        directory.mkdir(parents=True)
        (directory / "inner.txt").write_text("keep", encoding="utf-8")

        self.assertEqual(purge_partial_files(self.root), (0, 0))
        self.assertTrue(directory.is_dir())

    def test_startup_purges_staged_files_of_every_account(self):
        export_root = self.root / ACCOUNT_ID / "exports"
        staged = export_root / "messages" / "archive.json.part"
        staged.parent.mkdir(parents=True)
        staged.write_bytes(b"staged")
        finished = export_root / "messages" / "archive.json"
        finished.write_bytes(b"{}")
        paths = AccountPathRegistry(
            config_dir=self.root / "config", data_dir=self.root / ACCOUNT_ID / "data"
        )
        runtimes = SimpleNamespace(
            get_runtime=lambda account_id: None,
            account_kind=lambda account_id: "user",
            account_store=SimpleNamespace(list_public=lambda: [{"id": ACCOUNT_ID}]),
        )
        configs = SimpleNamespace(
            for_account=lambda account_id: config_for(self.root / account_id)
        )
        registry = AccountExportRegistry(configs, runtimes, paths)

        async def scenario():
            registry.start()
            try:
                self.assertFalse(staged.exists())
                self.assertTrue(finished.exists())
            finally:
                registry.shutdown()

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
