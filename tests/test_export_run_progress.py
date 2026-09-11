"""A running export publishes its message count before it finishes."""

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from backend.exporter import service as exporter_service
from backend.exporter.models import MessageRecord
from backend.exporter.service import ExportService
from backend.exporter.store import ExportStore

FULL_START = datetime(1970, 1, 1, tzinfo=timezone.utc)
FULL_END = datetime(2100, 1, 1, tzinfo=timezone.utc)


def sample_record(message_id: int) -> MessageRecord:
    date = f"2024-05-05T10:{message_id % 60:02d}:00+00:00"
    return MessageRecord(
        message_id=message_id,
        chat_id=-1001,
        chat_title="News",
        date=date,
        sender_id=7,
        sender_name="Alice",
        sender_username="alice",
        text="hello",
        media_type="text",
        content="hello",
        reply_to_message_id=None,
        edited_at=None,
        grouped_id=None,
        date_utc=date,
        raw={"_": "Message", "id": message_id, "message": "hello"},
        sender_raw={"_": "User", "id": 7, "first_name": "Alice"},
    )


class ProgressProbeSource:
    """Yield records and read the persisted run row between them."""

    def __init__(self):
        self.records = []
        self.probe = None

    def iter_message_records(self, **_kwargs):
        for record in self.records:
            yield record
            if self.probe is not None:
                self.probe()


class ExportRunProgressTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        config = SimpleNamespace(
            export_root_dir=str(self.root / "exports"),
            export_message_db_dir=str(self.root / "db"),
            export_concurrency=1,
            export_timezone="Asia/Shanghai",
        )
        self.source = ProgressProbeSource()
        self.store = ExportStore(self.root / "exports.db", export_root=self.root / "exports")
        self.service = ExportService(
            config,
            bot_manager=None,
            source=self.source,
            store=self.store,
        )
        self.addCleanup(self.service.shutdown)
        self.chat_id = -1001
        self.run_id = None

    def _run(self, records: int = 60):
        self.source.records = [sample_record(index + 1) for index in range(records)]
        observed = []

        def probe():
            run = self.store.list_runs()[0]
            self.run_id = run.id
            observed.append(run.message_count)

        self.source.probe = probe
        state = self.service._new_job("messages")
        self.service._run_message_export(
            state.id,
            None,
            self.chat_id,
            "News",
            FULL_START,
            FULL_END,
            ("json",),
            self.service._validated_directory("messages"),
            None,
        )
        snapshot = self.service.get_job(state.id)
        self.assertEqual(snapshot.status, "completed", snapshot.error)
        return observed

    def test_first_message_is_published_before_the_run_ends(self):
        observed = self._run()

        self.assertTrue(observed)
        # The very first message reaches the run row instead of leaving it at 0,
        # and the terminal count is still the exact total.
        self.assertEqual(observed[0], 1)
        self.assertEqual(self.store.get_run(self.run_id).message_count, 60)

    def test_count_grows_when_the_write_interval_elapses(self):
        with mock.patch.object(exporter_service, "RUN_PROGRESS_INTERVAL_SECONDS", 0.0):
            observed = self._run()

        # Without the rate limit the row follows every message; the production
        # interval only bounds how often that write happens.
        self.assertEqual(observed, list(range(1, 61)))
        self.assertEqual(self.store.get_run(self.run_id).message_count, 60)

    def test_published_count_stays_partial_mid_run(self):
        # The default two-second interval bounds the number of writes: a fast
        # export must not turn into one SQLite transaction per message.
        observed = self._run()

        self.assertEqual(set(observed), {1})
        self.assertEqual(self.store.get_run(self.run_id).message_count, 60)

    def test_finished_run_ignores_a_late_progress_write(self):
        run_id = self.store.start_run(task_id=None, run_type="messages", chat_id=self.chat_id)
        self.store.finish_run(run_id, status="completed", message_count=7)

        self.store.update_run_progress(run_id, 99)

        self.assertEqual(self.store.get_run(run_id).message_count, 7)

    def test_running_run_accepts_progress_writes(self):
        run_id = self.store.start_run(task_id=None, run_type="messages", chat_id=self.chat_id)

        self.store.update_run_progress(run_id, 12)

        run = self.store.get_run(run_id)
        self.assertEqual(run.message_count, 12)
        self.assertEqual(run.status, "running")


if __name__ == "__main__":
    unittest.main()
