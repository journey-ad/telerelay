import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from backend.exporter.service import ExportService
from backend.exporter.store import ExportStore


class ExportRunDeletionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.exports = self.root / "exports"
        self.exports.mkdir(parents=True)
        config = SimpleNamespace(
            export_root_dir=str(self.exports),
            export_message_db_dir=str(self.root / "db"),
            export_concurrency=1,
            session_type="user",
        )
        self.store = ExportStore(self.root / "exports.db")
        self.service = ExportService(
            config,
            bot_manager=None,
            source=SimpleNamespace(),
            store=self.store,
        )

    def test_delete_run_removes_record_and_files(self):
        run_id = self.store.start_run(
            task_id=None,
            run_type="instant",
            chat_id=-1001,
            chat_title="News",
        )
        file_path = self.exports / "news.json"
        file_path.write_text('{"messages": []}')
        self.store.finish_run(run_id, status="completed", files=[str(file_path)])
        self.assertTrue(file_path.exists())

        self.service.delete_run(run_id)

        self.assertFalse(file_path.exists())
        self.assertIsNone(self.store.get_run(run_id))

    def test_delete_run_does_not_touch_files_outside_root(self):
        run_id = self.store.start_run(task_id=None, run_type="instant")
        outside = self.root / "outside.txt"
        outside.write_text("x")
        self.store.finish_run(run_id, status="completed", files=[str(outside)])

        self.service.delete_run(run_id)

        self.assertTrue(outside.exists())

    def test_delete_missing_run_raises(self):
        with self.assertRaises(KeyError):
            self.service.delete_run(999)


if __name__ == "__main__":
    unittest.main()
