import shutil
import tempfile
import unittest
from datetime import datetime
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
            export_timezone="Asia/Shanghai",
            session_type="user",
        )
        self.store = ExportStore(self.root / "exports.db", export_root=self.exports)
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

    def test_legacy_run_files_remap_to_current_export_root(self):
        legacy_root = self.root / "legacy-data" / "exports"
        legacy_file = legacy_root / "messages" / "chat.html.zip"
        legacy_file.parent.mkdir(parents=True)
        legacy_file.write_bytes(b"archive")
        run_id = self.store.start_run(task_id=None, run_type="instant")
        self.store.finish_run(run_id, status="completed", files=[str(legacy_file)])

        moved = self.exports / "messages" / legacy_file.name
        moved.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(legacy_file), str(moved))

        run = self.service.list_runs()[0]
        self.assertEqual(run.files, (str(moved.resolve()),))

    def _create_task(self, **overrides):
        values = {
            "name": "Daily archive",
            "chat_id": -1001,
            "chat_title": "News",
            "initial_start_at": None,
            "formats": ["json"],
            "subdirectory": "scheduled",
            "schedule_type": "daily",
            "minute": 0,
            "hour": 2,
            "weekday": 0,
            "enabled": True,
        }
        values.update(overrides)
        return self.service.save_task(**values)

    def _edit_values(self, task, **overrides):
        values = {
            "task_id": task.id,
            "name": task.name,
            "chat_id": task.chat_id,
            "chat_title": task.chat_title,
            "initial_start_at": task.initial_start_at,
            "formats": list(task.formats),
            "subdirectory": task.subdirectory,
            "schedule_type": task.schedule_type,
            "minute": task.minute,
            "hour": task.hour,
            "weekday": task.weekday,
            "enabled": task.enabled,
        }
        values.update(overrides)
        return values

    def test_task_without_start_time_archives_from_now(self):
        task = self._create_task()

        start = datetime.fromisoformat(task.initial_start_at)
        self.assertTrue(task.initial_start_at.endswith("+08:00"))
        self.assertLess(abs((datetime.now(start.tzinfo) - start).total_seconds()), 60)

    def test_editing_a_task_keeps_the_export_cursor(self):
        task = self._create_task()
        self.store.update_task(
            task.id,
            last_message_id=500,
            last_success_at="2026-01-01T00:00:00+08:00",
        )

        updated = self.service.save_task(
            **self._edit_values(
                task,
                name="Weekly archive",
                formats=["json", "csv"],
                schedule_type="weekly",
                minute=15,
                hour=4,
                weekday=3,
                enabled=False,
            )
        )

        self.assertEqual(updated.id, task.id)
        self.assertEqual(updated.name, "Weekly archive")
        self.assertEqual(updated.schedule_type, "weekly")
        self.assertEqual((updated.minute, updated.hour, updated.weekday), (15, 4, 3))
        self.assertEqual(updated.formats, ("json", "csv"))
        self.assertFalse(updated.enabled)
        self.assertEqual(updated.last_message_id, 500)
        self.assertEqual(updated.last_success_at, "2026-01-01T00:00:00+08:00")

    def test_moving_a_task_to_another_chat_resets_the_cursor(self):
        task = self._create_task()
        self.store.update_task(task.id, last_message_id=500)

        moved = self.service.save_task(
            **self._edit_values(task, chat_id=-2002, chat_title="Other")
        )

        self.assertEqual(moved.chat_id, -2002)
        self.assertIsNone(moved.last_message_id)

    def test_editing_a_missing_task_raises(self):
        task = self._create_task()

        with self.assertRaises(KeyError):
            self.service.save_task(**self._edit_values(task, task_id=999))


if __name__ == "__main__":
    unittest.main()
