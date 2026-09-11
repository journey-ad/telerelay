"""The streamed HTML archive keeps the published archive contract intact.

`_legacy_entries` is the previous whole-list implementation, kept verbatim here
as the reference the streamed writer has to reproduce exactly.
"""

import json
import tempfile
import tracemalloc
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Mapping, Sequence

from backend.exporter import html_viewer
from backend.exporter import service as service_module
from backend.exporter.formatters import create_writer_set
from backend.exporter.message_store import MessageArchiveStore
from backend.exporter.service import ExportService
from backend.exporter.store import ExportStore

LABELS = {
    "title": "Message archive",
    "unknown_sender": "Unknown sender",
    "archive_readme": "Extract the archive, then open index.html in a browser.\n",
}

METADATA = {
    "title": "Archive of News",
    "exported_at": "2024-05-05T10:00:00+00:00",
    "chat_title": "News",
    "range_start": "2024-05-01T00:00:00+00:00",
    "range_end": "2024-05-05T10:00:00+00:00",
    "timezone": "Asia/Shanghai",
}

ARCHIVE_ROOT = "archive"


def _legacy_script_json(value: Any) -> str:
    """Previous inline-script serializer, before the single-pass escape."""
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _legacy_entries(
    records: Sequence[Mapping[str, Any]],
    *,
    max_records: int,
    max_bytes: int,
) -> Dict[str, bytes]:
    """Previous implementation, preserved verbatim as the output reference."""
    copied = [dict(record) for record in records]
    locations = {
        str(record.get("message_id")): index
        for index, record in enumerate(copied)
        if record.get("message_id") is not None
    }
    children: Dict[int, List[int]] = {}
    parents: Dict[int, int] = {}
    for child_index, record in enumerate(copied):
        reply_id = record.get("reply_to_message_id")
        if reply_id is not None:
            parent_index = locations.get(str(reply_id))
            if parent_index is not None and parent_index != child_index:
                children.setdefault(parent_index, []).append(child_index)
                parents[child_index] = parent_index

    descendant_counts = [0] * len(copied)
    remaining_children = [len(children.get(index, [])) for index in range(len(copied))]
    ready = [index for index, count in enumerate(remaining_children) if count == 0]
    cursor = 0
    while cursor < len(ready):
        index = ready[cursor]
        cursor += 1
        parent_index = parents.get(index)
        if parent_index is None:
            continue
        descendant_counts[parent_index] += 1 + descendant_counts[index]
        remaining_children[parent_index] -= 1
        if remaining_children[parent_index] == 0:
            ready.append(parent_index)

    for index, remaining in enumerate(remaining_children):
        if remaining:
            descendant_counts[index] = max(
                descendant_counts[index],
                len(children.get(index, [])),
            )

    unknown = LABELS.get("unknown_sender", "Unknown sender")
    for index, record in enumerate(copied):
        archive_data: Dict[str, Any] = {
            "index": index,
            "reply_count": descendant_counts[index],
        }
        child_indices = children.get(index, [])
        if child_indices:
            archive_data["children"] = child_indices
        reply_id = record.get("reply_to_message_id")
        if reply_id is not None:
            target_index = locations.get(str(reply_id))
            target = copied[target_index] if target_index is not None else None
            archive_data["reply"] = {
                "message_id": reply_id,
                "target_index": target_index,
                "sender": (
                    str(target.get("sender_name") or target.get("sender_id") or unknown)
                    if target
                    else None
                ),
                "date": str(target.get("date") or "") if target else None,
                "content": str(target.get("content") or "")[:240] if target else None,
            }
        record["_archive"] = archive_data

    chunks: List[List[Dict[str, Any]]] = []
    current: List[Dict[str, Any]] = []
    current_bytes = 2
    for record in copied:
        size = len(
            json.dumps(record, ensure_ascii=False, separators=(",", ":"), default=str)
            .encode("utf-8")
        ) + (1 if current else 0)
        if current and (len(current) >= max_records or current_bytes + size > max_bytes):
            chunks.append(current)
            current = []
            current_bytes = 2
        current.append(record)
        current_bytes += size
    if current:
        chunks.append(current)

    chunk_manifest = []
    start_index = 0
    for chunk_id, chunk in enumerate(chunks):
        dates = [str(row.get("date")) for row in chunk if row.get("date")]
        chunk_manifest.append(
            {
                "id": chunk_id,
                "file": f"data/chunk-{chunk_id + 1:06d}.js",
                "count": len(chunk),
                "start_index": start_index,
                "min_date": min(dates)[:10] if dates else None,
                "max_date": max(dates)[:10] if dates else None,
            }
        )
        start_index += len(chunk)

    manifest = {
        "schema_version": 1,
        "title": str(METADATA.get("title") or LABELS.get("title", "Message archive")),
        "exported_at": str(METADATA.get("exported_at") or ""),
        "chat_title": str(METADATA.get("chat_title") or ""),
        "range_start": str(METADATA.get("range_start") or ""),
        "range_end": str(METADATA.get("range_end") or ""),
        "timezone": str(METADATA.get("timezone") or ""),
        "total": len(copied),
        "default_page_size": 100,
        "page_sizes": [100, 500, 1000, 2000],
        "cache_chunks": 3,
        "chunks": chunk_manifest,
        "labels": dict(LABELS),
    }
    index_labels = dict(LABELS)
    index_labels["title"] = str(METADATA["title"])
    entries: Dict[str, bytes] = {
        f"{ARCHIVE_ROOT}/index.html": html_viewer.render_index_html(
            index_labels, variant="ledger"
        ).encode("utf-8"),
        f"{ARCHIVE_ROOT}/manifest.js": (
            f"window.TELE_RELAY_MANIFEST={_legacy_script_json(manifest)};\n"
        ).encode("utf-8"),
        f"{ARCHIVE_ROOT}/README.txt": LABELS["archive_readme"].encode("utf-8"),
    }
    for chunk_id, chunk in enumerate(chunks):
        entries[f"{ARCHIVE_ROOT}/data/chunk-{chunk_id + 1:06d}.js"] = (
            f"window.TeleRelayArchive.receiveChunk({chunk_id},"
            f"{_legacy_script_json(chunk)});\n"
        ).encode("utf-8")
    return entries


def message(index: int, **overrides) -> Dict[str, Any]:
    record = {
        "message_id": index,
        "chat_id": -1001,
        "chat_title": "News",
        "date": f"2024-05-05T10:{index:02d}:00+08:00",
        "sender_id": 500 + index,
        "sender_name": f"User{index}",
        "sender_username": f"user{index}",
        "text": f"text {index}",
        "media_type": "text",
        "content": f"content {index} " + "x" * 20,
        "reply_to_message_id": None,
        "edited_at": None,
        "grouped_id": None,
        "forward_from_id": None,
        "forward_from_name": None,
        "post_author": None,
        "views": index,
        "forwards": 0,
        "replies_count": 0,
    }
    record.update(overrides)
    return record


def conversation() -> List[Dict[str, Any]]:
    """Reply shapes the viewer has to render, including its edge cases."""
    records = [message(index) for index in range(1, 13)]
    records[1]["reply_to_message_id"] = 1  # child of 1
    records[2]["reply_to_message_id"] = 1  # second child of the same parent
    records[3]["reply_to_message_id"] = 2  # depth two under 1
    records[4]["reply_to_message_id"] = 5  # self reply
    records[5]["reply_to_message_id"] = 9  # parent later in the stream, empty content
    records[6]["reply_to_message_id"] = 10  # parent without a sender name
    records[7]["reply_to_message_id"] = 999  # parent outside the archive
    records[8]["content"] = None
    records[9]["sender_name"] = None
    records[10]["reply_to_message_id"] = 11  # self reply whose sender is unknown
    records[10]["sender_name"] = None
    records[10]["sender_id"] = None
    return records


def archive_entries(records) -> Dict[str, bytes]:
    with tempfile.TemporaryDirectory() as directory:
        writers = create_writer_set(
            Path(directory) / ARCHIVE_ROOT,
            "messages",
            ("html",),
            METADATA,
            LABELS,
        )
        for record in records:
            writers.add(record)
        with zipfile.ZipFile(writers.finalize()[0]) as archive:
            return {name: archive.read(name) for name in archive.namelist()}


class HtmlArchiveContractTests(unittest.TestCase):
    def assert_matches_legacy(self, records, *, max_records=None, max_bytes=None):
        options = {
            "max_records": max_records or html_viewer.ARCHIVE_MAX_RECORDS,
            "max_bytes": max_bytes or html_viewer.ARCHIVE_MAX_BYTES,
        }
        original = (html_viewer.ARCHIVE_MAX_RECORDS, html_viewer.ARCHIVE_MAX_BYTES)
        html_viewer.ARCHIVE_MAX_RECORDS = options["max_records"]
        html_viewer.ARCHIVE_MAX_BYTES = options["max_bytes"]
        try:
            expected = _legacy_entries(records, **options)
            actual = archive_entries(records)
        finally:
            html_viewer.ARCHIVE_MAX_RECORDS, html_viewer.ARCHIVE_MAX_BYTES = original

        self.assertEqual(sorted(actual), sorted(expected))
        for name in sorted(expected):
            self.assertEqual(actual[name], expected[name], name)
        return actual

    def test_conversation_archive_matches_legacy_output(self):
        self.assert_matches_legacy(conversation())

    def test_empty_archive_matches_legacy_output(self):
        self.assert_matches_legacy([])

    def test_multi_chunk_archive_matches_legacy_output(self):
        records = [message(index) for index in range(1, 41)]
        for index in range(1, 40, 3):
            records[index]["reply_to_message_id"] = records[index - 1]["message_id"]

        actual = self.assert_matches_legacy(records, max_records=7)

        manifest = json.loads(
            actual[f"{ARCHIVE_ROOT}/manifest.js"]
            .decode("utf-8")
            .removeprefix("window.TELE_RELAY_MANIFEST=")
            .rstrip(";\n")
        )
        self.assertEqual(
            [chunk["start_index"] for chunk in manifest["chunks"]],
            [0, 7, 14, 21, 28, 35],
        )
        self.assertEqual(sum(chunk["count"] for chunk in manifest["chunks"]), 40)
        self.assertEqual(manifest["total"], 40)

    def test_byte_limit_splits_chunks_like_legacy(self):
        records = [message(index, content="y" * 400) for index in range(1, 21)]

        self.assert_matches_legacy(records, max_bytes=1200)

    def test_reply_metadata_matches_legacy_for_edge_shapes(self):
        actual = self.assert_matches_legacy(conversation())

        chunk = actual[f"{ARCHIVE_ROOT}/data/chunk-000001.js"].decode("utf-8")
        payload = json.loads(chunk.split(",", 1)[1].rstrip(");\n"))
        by_id = {row["message_id"]: row["_archive"] for row in payload}

        self.assertEqual(by_id[1]["children"], [1, 2])
        self.assertEqual(by_id[1]["reply_count"], 3)
        self.assertEqual(by_id[5]["reply"]["target_index"], 4)
        self.assertEqual(by_id[6]["reply"]["target_index"], 8)
        self.assertEqual(by_id[6]["reply"]["content"], "")
        self.assertEqual(by_id[7]["reply"]["target_index"], 9)
        self.assertEqual(by_id[7]["reply"]["sender"], "510")
        self.assertIsNone(by_id[8]["reply"]["target_index"])
        self.assertIsNone(by_id[8]["reply"]["sender"])
        self.assertEqual(by_id[11]["reply"]["sender"], "Unknown sender")

    def test_spool_file_is_removed_when_the_archive_is_published(self):
        with tempfile.TemporaryDirectory() as directory:
            writers = create_writer_set(
                Path(directory) / ARCHIVE_ROOT, "messages", ("html",), METADATA, LABELS
            )
            writer = writers._writers[0]
            for record in conversation():
                writers.add(record)
            self.assertTrue(writer.spool_path.exists())

            with zipfile.ZipFile(writers.finalize()[0]):
                pass

            self.assertFalse(writer.spool_path.exists())
            self.assertFalse(writer.part_path.exists())

    def test_spool_file_is_removed_when_the_archive_is_aborted(self):
        with tempfile.TemporaryDirectory() as directory:
            writers = create_writer_set(
                Path(directory) / ARCHIVE_ROOT, "messages", ("html",), METADATA, LABELS
            )
            writer = writers._writers[0]
            for record in conversation():
                writers.add(record)

            writers.abort()

            self.assertFalse(writer.spool_path.exists())
            self.assertFalse(writer.part_path.exists())
            self.assertFalse(writer.final_path.exists())

    def test_records_are_spooled_instead_of_retained(self):
        with tempfile.TemporaryDirectory() as directory:
            writers = create_writer_set(
                Path(directory) / ARCHIVE_ROOT, "messages", ("html",), METADATA, LABELS
            )
            tracemalloc.start()
            try:
                for index in range(1, 5001):
                    writers.add(message(index, content="z" * 1024))
                peak = tracemalloc.get_traced_memory()[1]
            finally:
                tracemalloc.stop()
                writers.abort()

        # 5,000 records of ~1 KB each stay far below their own size.
        self.assertLess(peak, 4 * 1024 * 1024)

    def test_streamed_archive_serves_every_online_preview_entry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            exports = ExportService(
                SimpleNamespace(
                    export_root_dir=str(root),
                    export_message_db_dir=str(root / "db"),
                    export_concurrency=1,
                ),
                bot_manager=None,
                source=SimpleNamespace(),
                store=SimpleNamespace(),
            )
            self.addCleanup(exports.shutdown)
            writers = create_writer_set(
                root / ARCHIVE_ROOT, "messages", ("html",), METADATA, LABELS
            )
            for record in conversation():
                writers.add(record)
            path = writers.finalize()[0]

            token = exports.create_preview_token(path)
            self.assertEqual(exports.resolve_preview_token(token), path.resolve())
            # The viewer requests every entry by its archive-rooted path.
            for entry in (
                f"{ARCHIVE_ROOT}/index.html",
                f"{ARCHIVE_ROOT}/manifest.js",
                f"{ARCHIVE_ROOT}/data/chunk-000001.js",
                f"{ARCHIVE_ROOT}/README.txt",
            ):
                self.assertIsNotNone(
                    exports.read_archive_file(path, entry), entry
                )


class MessageStoreCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)

    def test_close_releases_connections_and_keeps_the_store_usable(self):
        store = MessageArchiveStore(self.root / "db", -1001)
        store.upsert([message(1)])

        store.close()
        store.close()

        self.assertEqual(store.count(), 1)
        store.upsert([message(2)])
        self.assertEqual(store.count(), 2)

    def test_evicted_stores_are_dropped_and_rebuilt_on_demand(self):
        config = SimpleNamespace(
            export_root_dir=str(self.root / "exports"),
            export_message_db_dir=str(self.root / "db"),
            export_concurrency=1,
            export_timezone="Asia/Shanghai",
        )
        exports = ExportService(
            config,
            bot_manager=None,
            source=SimpleNamespace(),
            store=ExportStore(
                self.root / "exports.db", export_root=self.root / "exports"
            ),
        )
        self.addCleanup(exports.shutdown)
        original_limit = service_module.MESSAGE_STORE_CACHE_LIMIT
        self.addCleanup(
            setattr, service_module, "MESSAGE_STORE_CACHE_LIMIT", original_limit
        )
        service_module.MESSAGE_STORE_CACHE_LIMIT = 2

        first = exports._message_store(-1001)
        exports._message_store(-1002)
        exports._message_store(-1003)

        self.assertEqual(list(exports._message_stores), [-1002, -1003])
        rebuilt = exports._message_store(-1001)
        self.assertIsNot(rebuilt, first)
        self.assertEqual(len(exports._message_stores), 2)
        # A caller still holding the evicted store keeps working.
        self.assertEqual(first.count(), 0)


if __name__ == "__main__":
    unittest.main()
