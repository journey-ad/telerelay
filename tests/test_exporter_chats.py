"""Chat-list export metadata, status mapping, and failure isolation."""

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from telethon.tl import types
from telethon.tl.functions.channels import GetFullChannelRequest, GetParticipantRequest
from telethon.tl.functions.messages import GetFullChatRequest, GetHistoryRequest

from backend.exporter.models import ChatRecord
from backend.exporter.source import (
    TelegramExportSource,
    _chat_status,
    _message_preview,
)
from backend.telegram_chats import _chat_validity

JOINED = datetime(2023, 5, 1, 12, 0, tzinfo=timezone.utc)
LAST_MESSAGE = datetime(2024, 6, 2, 8, 30, tzinfo=timezone.utc)


def channel(**overrides):
    values = dict(id=100, title="Channel", photo=None, date=None)
    values.update(overrides)
    return types.Channel(**values)


def dialog(entity, *, archived=False, unread=0, date=None, message=None):
    return SimpleNamespace(
        entity=entity,
        archived=archived,
        unread_count=unread,
        date=date,
        message=message,
    )


class FakeFullChannel:
    def __init__(self, *, about, participant, count):
        self.full_chat = SimpleNamespace(
            about=about, participants_count=count, participant=participant
        )


class FakeClient:
    """Only the handful of calls the chat-list source is allowed to make."""

    def __init__(self, *, about="about", own_date=JOINED, count=42, history_count=7):
        self.calls = []
        self.about = about
        self.own_date = own_date
        self.count = count
        self.history_count = history_count

    async def __call__(self, request):
        self.calls.append(request)
        if isinstance(request, GetFullChannelRequest):
            participant = SimpleNamespace(date=self.own_date) if self.own_date else None
            return FakeFullChannel(about=self.about, participant=participant, count=self.count)
        if isinstance(request, GetParticipantRequest):
            participant = SimpleNamespace(date=self.own_date) if self.own_date else None
            return SimpleNamespace(participant=participant)
        if isinstance(request, GetHistoryRequest):
            return SimpleNamespace(count=self.history_count)
        if isinstance(request, GetFullChatRequest):
            raise AssertionError("plain groups are not exercised here")
        raise AssertionError(f"unexpected request {request!r}")

    async def get_me(self):
        return SimpleNamespace(id=99)


class ChatStatusTests(unittest.TestCase):
    def test_status_maps_each_telegram_flag(self):
        cases = {
            "ok": SimpleNamespace(),
            "deleted": SimpleNamespace(deleted=True),
            "deactivated": SimpleNamespace(deactivated=True),
            "left": SimpleNamespace(left=True),
            "readonly": SimpleNamespace(
                banned_rights=SimpleNamespace(view_messages=False, send_messages=True)
            ),
            "blocked": SimpleNamespace(
                banned_rights=SimpleNamespace(view_messages=True, send_messages=False)
            ),
        }
        for expected, entity in cases.items():
            with self.subTest(expected=expected):
                # The directory's own check decides deleted/deactivated/left.
                self.assertEqual(_chat_status(entity, _chat_validity(entity)), expected)

    def test_directory_validity_filter_is_not_lost(self):
        # A validity reported elsewhere in the app still reaches the export.
        self.assertEqual(_chat_status(SimpleNamespace(), "blocked"), "blocked")

    def test_forbidden_entity_reports_blocked(self):
        entity = types.ChannelForbidden(id=1, access_hash=1, title="gone")
        self.assertEqual(_chat_status(entity, _chat_validity(entity)), "blocked")

    def test_preview_is_bounded_and_tolerates_missing_message(self):
        self.assertIsNone(_message_preview(None))
        self.assertIsNone(_message_preview(SimpleNamespace(message="")))
        self.assertEqual(_message_preview(SimpleNamespace(message="hi")), "hi")
        long_text = "x" * 500
        self.assertEqual(len(_message_preview(SimpleNamespace(message=long_text))), 200)


class ChatRecordEnrichmentTests(unittest.IsolatedAsyncioTestCase):
    async def test_record_carries_status_join_time_counts_and_last_message(self):
        source = TelegramExportSource(bot_manager=None)
        client = FakeClient()
        message = SimpleNamespace(id=555, message="last words")
        entity = channel(username="public_name", participants_count=None)

        record = await source._build_chat_record(
            client, dialog(entity, date=LAST_MESSAGE, unread=3, message=message)
        )

        self.assertEqual(record.status, "ok")
        self.assertEqual(record.joined_at, JOINED.isoformat(timespec="seconds"))
        self.assertEqual(record.message_count, 7)
        self.assertEqual(record.member_count, 42)
        self.assertEqual(record.unread_count, 3)
        self.assertFalse(record.is_archived)
        self.assertEqual(record.last_message_id, 555)
        self.assertEqual(record.last_message_at, LAST_MESSAGE.isoformat(timespec="seconds"))
        self.assertEqual(record.last_message_text, "last words")
        self.assertEqual(record.public_link, "https://t.me/public_name")

    async def test_missing_join_date_degrades_to_none(self):
        source = TelegramExportSource(bot_manager=None)
        client = FakeClient(own_date=None)
        record = await source._build_chat_record(client, dialog(channel()))
        self.assertIsNone(record.joined_at)
        self.assertEqual(record.status, "ok")

    async def test_history_failure_keeps_the_row_and_leaves_count_empty(self):
        source = TelegramExportSource(bot_manager=None)

        class FailingHistory(FakeClient):
            async def __call__(self, request):
                if isinstance(request, GetHistoryRequest):
                    raise RuntimeError("flood")
                return await super().__call__(request)

        record = await source._build_chat_record(FailingHistory(), dialog(channel()))
        self.assertIsNone(record.message_count)
        self.assertEqual(record.title, "Channel")

    async def test_one_broken_chat_does_not_abort_the_listing(self):
        source = TelegramExportSource(bot_manager=None)
        broken = channel(id=200, title="Broken")

        class Exploding(FakeClient):
            async def __call__(self, request):
                if isinstance(request, GetFullChannelRequest):
                    raise RuntimeError("flood")
                return await super().__call__(request)

        async def fake_builder(client, item):
            if item.entity.id == 200:
                raise RuntimeError("flood")
            return await source._build_chat_record(client, item)

        source._build_chat_record = fake_builder
        records = []
        for entity in (channel(id=100, title="Ok"), broken):
            try:
                records.append(await source._build_chat_record(FakeClient(), dialog(entity)))
            except Exception as exc:  # pragma: no cover - build is patched to succeed
                records.append(source._fallback_chat_record(dialog(entity), exc))

        self.assertEqual(len(records), 2)

    async def test_fallback_record_keeps_identity_and_marks_the_warning(self):
        source = TelegramExportSource(bot_manager=None)
        record = source._fallback_chat_record(
            dialog(channel(title="Half", username="handle"), date=LAST_MESSAGE),
            RuntimeError("flood"),
        )
        self.assertEqual(record.title, "Half")
        self.assertEqual(record.username, "handle")
        self.assertEqual(record.status, "ok")
        self.assertIsNone(record.message_count)
        self.assertIsNone(record.joined_at)
        self.assertTrue(record.export_warning)


class ChatListTaskTests(unittest.TestCase):
    def _service(self, temp_dir):
        from backend.exporter.service import ExportService
        from backend.exporter.store import ExportStore

        root = Path(temp_dir)
        config = SimpleNamespace(
            export_root_dir=str(root / "exports"),
            export_message_db_dir=str(root / "db"),
            export_timezone="Asia/Shanghai",
            export_concurrency=1,
        )
        store = ExportStore(root / "exports.db", export_root=config.export_root_dir)
        return ExportService(config, SimpleNamespace(account_id="1"), store=store)

    def test_existing_database_gains_the_kind_column(self):
        import sqlite3

        from backend.exporter.store import ExportStore

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "exports.db"
            legacy = sqlite3.connect(db_path)
            legacy.execute(
                "CREATE TABLE export_tasks ("
                "id INTEGER PRIMARY KEY, name VARCHAR NOT NULL, chat_id INTEGER NOT NULL,"
                "chat_title VARCHAR NOT NULL, initial_start_at VARCHAR NOT NULL,"
                "formats TEXT NOT NULL, subdirectory VARCHAR NOT NULL,"
                "schedule_type VARCHAR NOT NULL, minute INTEGER NOT NULL,"
                "hour INTEGER NOT NULL, weekday INTEGER NOT NULL, timezone VARCHAR NOT NULL,"
                "enabled BOOLEAN NOT NULL, last_message_id INTEGER, last_success_at VARCHAR,"
                "next_run_at VARCHAR, created_at VARCHAR NOT NULL, updated_at VARCHAR NOT NULL)"
            )
            legacy.execute(
                "INSERT INTO export_tasks VALUES (1,'old',-1001,'Old chat','2026-01-01T00:00:00',"
                "'[\"json\"]','scheduled','daily',0,2,0,'Asia/Shanghai',1,NULL,NULL,NULL,"
                "'2026-01-01T00:00:00','2026-01-01T00:00:00')"
            )
            legacy.commit()
            legacy.close()

            store = ExportStore(db_path, export_root=temp_dir)
            task = store.get_task(1)
            self.assertEqual(task.kind, "messages")
            self.assertEqual(task.chat_title, "Old chat")

    def test_chat_list_task_ignores_the_chat_binding(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._service(temp_dir)
            task = service.save_task(
                name="Chat list",
                kind="chats",
                chat_id=None,
                chat_title=None,
                initial_start_at=None,
                formats=["json", "csv"],
                subdirectory="groups",
                schedule_type="daily",
                minute=0,
                hour=2,
                weekday=0,
            )
            self.assertEqual(task.kind, "chats")
            self.assertEqual(task.chat_id, 0)
            # No stored title: the console labels it from the kind, so the label
            # is not frozen into whichever language created the task.
            self.assertEqual(task.chat_title, "")
            # Reopening keeps the stored kind, which the API exposes to the UI.
            self.assertEqual(service.store.get_task(task.id).kind, "chats")
            service.shutdown()

    def test_message_task_still_stores_its_chat(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._service(temp_dir)
            task = service.save_task(
                name="Messages",
                chat_id=-1001,
                chat_title="Release Room",
                initial_start_at=None,
                formats=["json"],
                subdirectory="scheduled",
                schedule_type="daily",
                minute=0,
                hour=2,
                weekday=0,
            )
            self.assertEqual(task.kind, "messages")
            self.assertEqual(task.chat_id, -1001)
            self.assertEqual(task.chat_title, "Release Room")
            service.shutdown()

    def test_switching_kind_resets_the_message_cursor(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._service(temp_dir)
            task = service.save_task(
                name="Switch",
                chat_id=-1001,
                chat_title="Room",
                initial_start_at=None,
                formats=["json"],
                subdirectory="scheduled",
                schedule_type="daily",
                minute=0,
                hour=2,
                weekday=0,
            )
            service.store.update_task(task.id, last_message_id=777)
            switched = service.save_task(
                task_id=task.id,
                name="Switch",
                kind="chats",
                chat_id=None,
                chat_title=None,
                initial_start_at=None,
                formats=["json", "csv"],
                subdirectory="groups",
                schedule_type="daily",
                minute=0,
                hour=2,
                weekday=0,
            )
            self.assertEqual(switched.kind, "chats")
            self.assertIsNone(switched.last_message_id)
            service.shutdown()


class ChatListHtmlTests(unittest.TestCase):
    """The chat-list page is a searchable table, not one card per chat."""

    def _render(self, temp_dir, records):
        from backend.exporter.formatters import _HtmlWriter
        from backend.exporter.service import ExportService

        writer = _HtmlWriter(
            Path(temp_dir) / "chats",
            "chats",
            {"title": "Chats", "exported_at": "2026-01-01T00:00:00", "chat_count": len(records)},
            ExportService._html_labels(),
        )
        for record in records:
            writer.add(record)
        return writer.finalize().read_text(encoding="utf-8")

    @staticmethod
    def _record(chat_id=-1001, **overrides):
        record = {
            "chat_id": chat_id,
            "title": "Room",
            "kind": "supergroup",
            "created_at": "2024-01-02T03:04:05+00:00",
            "username": None,
            "public_link": None,
            "is_public": False,
            "member_count": 1234,
            "description": None,
            "export_warning": None,
            "status": "ok",
            "is_archived": False,
            "unread_count": 0,
            "joined_at": "2025-06-07T08:09:10+00:00",
            "last_message_id": 7,
            "last_message_at": "2026-01-01T00:00:00+00:00",
            "last_message_text": None,
            "message_count": 4321,
        }
        record.update(overrides)
        return record

    def test_table_has_search_toolbar_and_one_row_per_chat(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            html = self._render(temp_dir, [self._record(-1001), self._record(-1002)])
        self.assertIn('id="chats-search"', html)
        self.assertIn('id="chats-count"', html)
        self.assertEqual(html.count('class="chats-row"'), 2)
        self.assertNotIn('<article class="chat"', html)

    def test_status_and_counts_are_rendered_for_scanning(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            html = self._render(
                temp_dir,
                [self._record(-1001, status="left"), self._record(-1002, status="ok")],
            )
        self.assertIn('<span class="status status-bad">已退出</span>', html)
        self.assertIn('<span class="status status-ok">正常</span>', html)
        self.assertIn("1,234", html)
        self.assertIn("4,321", html)

    def test_details_are_inert_json_so_a_closing_tag_cannot_break_out(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            html = self._render(
                temp_dir,
                [
                    self._record(
                        -1001,
                        description='</script><script>alert("x")</script>',
                        export_warning="Group details unavailable",
                    )
                ],
            )
        self.assertIn('type="application/json"', html)
        # The payload may not contain a literal closing tag.
        payload_start = html.index('id="facts--1001"')
        payload = html[payload_start : html.index("</script>", payload_start)]
        self.assertNotIn("</script>", payload)
        self.assertIn("<\\/script>", payload)

    def test_free_text_facts_are_flagged_for_wrapping(self):
        import json as _json

        from backend.exporter.service import ExportService

        labels = ExportService._html_labels()
        with tempfile.TemporaryDirectory() as temp_dir:
            html = self._render(
                temp_dir,
                [self._record(-1001, description="很长的简介" * 40, export_warning="详情不可读")],
            )
            self.assertIn("chats-facts div.wide{grid-column:1/-1}", html)

        payload = html[html.index('id="facts--1001"') :]
        payload = payload[: payload.index("</script>")]
        facts = _json.loads(
            payload[payload.index(">", payload.index("id=")) + 1 :].replace("<\\/", "</")
        )
        wide = {row[0]: row[3] for row in facts}
        self.assertTrue(wide[labels["description"]])
        self.assertTrue(wide[labels["export_warning"]])
        self.assertFalse(wide[labels["chat_id"]])

    def test_search_blob_covers_name_username_and_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            html = self._render(
                temp_dir,
                [self._record(-1001, title="Alpha", username="alpha_handle")],
            )
        body = html[html.index("<tbody") :]
        row = body[body.index('class="chats-row"') : body.index("</tr>")]
        self.assertIn("alpha", row.lower())
        self.assertIn("alpha_handle", row)
        self.assertIn("-1001", row)

    def test_message_export_keeps_the_card_layout(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            from backend.exporter.formatters import _HtmlWriter
            from backend.exporter.service import ExportService

            writer = _HtmlWriter(
                Path(temp_dir) / "messages",
                "messages",
                {"title": "History", "exported_at": "2026-01-01T00:00:00"},
                ExportService._html_labels(),
            )
            writer.add({"message_id": 1, "date": "2026-01-01T00:00:00", "content": "hi"})
            html = writer.finalize().read_text(encoding="utf-8")
        self.assertIn('<article class="message"', html)
        # The chat-list table markup must not leak into a message export.
        self.assertNotIn('class="chats-table"', html)
        self.assertNotIn('id="chats-search"', html)


class ChatRecordSerializationTests(unittest.TestCase):
    def test_every_html_label_resolves_to_copy(self):
        """A label missing from the locale files degrades to its raw key."""
        from backend.exporter.service import ExportService

        labels = ExportService._html_labels()
        unresolved = sorted(
            key for key, value in labels.items() if value in (key, f"export.html.{key}")
        )
        self.assertEqual(unresolved, [])

    def test_to_dict_exposes_export_columns(self):
        record = ChatRecord(
            chat_id=1,
            title="T",
            kind="channel",
            created_at=None,
            username=None,
            public_link=None,
            is_public=False,
            member_count=None,
            description=None,
        )
        data = record.to_dict()
        for key in (
            "status",
            "joined_at",
            "last_message_at",
            "last_message_text",
            "message_count",
            "unread_count",
            "is_archived",
        ):
            self.assertIn(key, data)


if __name__ == "__main__":
    unittest.main()
