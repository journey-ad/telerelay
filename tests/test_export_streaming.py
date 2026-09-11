"""Archive reads stream a range instead of materializing it in memory."""

import json
import tempfile
import unittest
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from backend.exporter.message_store import MessageArchiveStore
from backend.exporter.models import MessageRecord
from backend.exporter.service import ExportService
from backend.exporter.store import ExportStore

FULL_START = datetime(1970, 1, 1, tzinfo=timezone.utc)
FULL_END = datetime(2100, 1, 1, tzinfo=timezone.utc)


def sample_record(
    message_id: int,
    date_utc: str,
    text: str = "hello",
    chat_id: int = -1001,
) -> MessageRecord:
    """One message, usable as a stored payload or as a source record."""
    return MessageRecord(
        message_id=message_id,
        chat_id=chat_id,
        chat_title="News",
        date=date_utc,
        sender_id=7,
        sender_name="Alice",
        sender_username="alice",
        text=text,
        media_type="text",
        content=text,
        reply_to_message_id=None,
        edited_at=None,
        grouped_id=None,
        date_utc=date_utc,
        raw={"_": "Message", "id": message_id, "message": text},
        sender_raw={"_": "User", "id": 7, "first_name": "Alice"},
    )


def at(second: int) -> str:
    return f"2024-05-05T10:00:{second:02d}+00:00"


class FakeExportSource:
    def __init__(self, records=()):
        self.records = list(records)

    def iter_message_records(self, **_kwargs):
        yield from self.records


class MessageArchiveStreamingTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.store = MessageArchiveStore(self.root / "db", -1001)

    def _seed(self, count=5, same_date=False):
        self.store.upsert(
            [
                sample_record(
                    index + 1,
                    at(0) if same_date else at(index),
                ).to_dict()
                for index in range(count)
            ]
        )

    def _stream(self, batch_size=2, **overrides):
        values = {
            "start_at": FULL_START,
            "end_at": FULL_END,
            "output_timezone": timezone.utc,
            "batch_size": batch_size,
        }
        values.update(overrides)
        return self.store.iter_records(**values)

    def test_iter_records_spans_batches_in_order(self):
        self._seed(count=5)

        ids = [record["message_id"] for record in self._stream(batch_size=2)]

        self.assertEqual(ids, [1, 2, 3, 4, 5])

    def test_iter_records_keeps_records_sharing_one_date(self):
        self._seed(count=5, same_date=True)

        ids = [record["message_id"] for record in self._stream(batch_size=2)]

        self.assertEqual(ids, [1, 2, 3, 4, 5])

    def test_iter_records_filters_the_requested_range(self):
        self._seed(count=5)

        ids = [
            record["message_id"]
            for record in self._stream(
                batch_size=2,
                start_at=datetime(2024, 5, 5, 10, 0, 1, tzinfo=timezone.utc),
                end_at=datetime(2024, 5, 5, 10, 0, 3, tzinfo=timezone.utc),
            )
        ]

        self.assertEqual(ids, [2, 3, 4])

    def test_iter_records_restores_json_payloads_and_localized_dates(self):
        self._seed(count=1)

        record = next(self._stream(output_timezone=ZoneInfo("Asia/Shanghai")))

        self.assertEqual(record["raw"]["message"], "hello")
        self.assertEqual(record["sender_raw"]["first_name"], "Alice")
        self.assertEqual(record["date"], "2024-05-05T18:00:00+08:00")


class ExportArchiveStreamingTests(unittest.TestCase):
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
        self.source = FakeExportSource()
        self.store = ExportStore(self.root / "exports.db", export_root=self.root / "exports")
        self.service = ExportService(
            config,
            bot_manager=None,
            source=self.source,
            store=self.store,
        )
        self.addCleanup(self.service.shutdown)
        self.chat_id = -1001
        self.archive = self.service._message_store(self.chat_id)

    def _run(self, *, task_id=None, formats=("json",), start_at=FULL_START, end_at=FULL_END):
        state = self.service._new_job("messages", task_id)
        self.service._run_message_export(
            state.id,
            task_id,
            self.chat_id,
            "News",
            start_at,
            end_at,
            tuple(formats),
            self.service._validated_directory("messages"),
            None,
        )
        snapshot = self.service.get_job(state.id)
        self.assertEqual(snapshot.status, "completed", snapshot.error)
        return snapshot

    def test_manual_export_reads_the_whole_stored_range(self):
        self.archive.upsert([sample_record(1, at(0), "archived earlier").to_dict()])
        self.source.records = [sample_record(2, at(1), "live 2")]

        snapshot = self._run(formats=("json",))

        self.assertEqual(len(snapshot.files), 1)
        exported = json.loads(Path(snapshot.files[0]).read_text(encoding="utf-8"))
        self.assertEqual(
            [item["message_id"] for item in exported["messages"]], [1, 2]
        )
        self.assertEqual(exported["messages"][0]["content"], "archived earlier")

    def test_manual_export_writes_no_file_for_an_empty_archive(self):
        self.source.records = []

        snapshot = self._run(formats=("json",))

        self.assertEqual(snapshot.files, ())
        self.assertEqual(
            list((self.root / "exports" / "messages").glob("*.json")), []
        )

    def test_scheduled_html_export_rebuilds_the_archive_range(self):
        self.archive.upsert(
            [sample_record(index + 1, at(index)).to_dict() for index in range(3)]
        )
        task = self.service.save_task(
            name="Daily archive",
            chat_id=self.chat_id,
            chat_title="News",
            initial_start_at="2024-05-05T00:00:00+08:00",
            formats=["html"],
            subdirectory="scheduled",
            schedule_type="daily",
            minute=0,
            hour=2,
            weekday=0,
            timezone_name="Asia/Shanghai",
        )
        self.source.records = []

        snapshot = self._run(
            task_id=task.id,
            formats=("html",),
            start_at=datetime(2024, 5, 5, tzinfo=timezone.utc),
            end_at=FULL_END,
        )

        archives = [Path(path) for path in snapshot.files if path.endswith(".html.zip")]
        self.assertEqual(len(archives), 1)
        with zipfile.ZipFile(archives[0]) as archive:
            manifest = next(
                name for name in archive.namelist() if name.endswith("manifest.js")
            )
            self.assertIn('"total":3', archive.read(manifest).decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
