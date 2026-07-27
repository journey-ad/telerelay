"""Streaming JSON, CSV, and offline HTML export writers."""

import csv
import html
import json
import os
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence

from .html_viewer import (
    chunk_script,
    manifest_script,
    prepare_archive,
    render_index_html,
)

CHAT_FIELDS = (
    "chat_id",
    "title",
    "kind",
    "created_at",
    "username",
    "public_link",
    "is_public",
    "member_count",
    "description",
    "administrators",
    "export_warning",
)

MESSAGE_FIELDS = (
    "message_id",
    "chat_id",
    "chat_title",
    "date",
    "sender_id",
    "sender_name",
    "sender_username",
    "text",
    "media_type",
    "content",
    "reply_to_message_id",
    "edited_at",
    "grouped_id",
)


def _spreadsheet_safe(value: Any) -> Any:
    """Prevent untrusted chat content from becoming a spreadsheet formula."""
    if not isinstance(value, str):
        return value
    stripped = value.lstrip()
    if stripped.startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def _json_default(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _open_private_text(path: Path, *, encoding: str, newline: str):
    """Create a private temporary file without following a pre-existing symlink."""
    path.unlink(missing_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    return os.fdopen(fd, "w", encoding=encoding, newline=newline)


class _AtomicWriter:
    """Base writer that publishes a file only after it is complete."""

    extension = ""

    def __init__(self, target_base: Path):
        self.final_path = target_base.with_suffix(self.extension)
        self.part_path = Path(str(self.final_path) + ".part")
        self._closed = False

    def add(self, record: Mapping[str, Any]) -> None:
        raise NotImplementedError

    def finalize(self) -> Path:
        if self._closed:
            return self.final_path
        self._close_document()
        self._file.flush()
        os.fsync(self._file.fileno())
        self._file.close()
        os.replace(self.part_path, self.final_path)
        os.chmod(self.final_path, 0o600)
        self._closed = True
        return self.final_path

    def abort(self) -> None:
        if not self._closed:
            try:
                self._file.close()
            finally:
                self.part_path.unlink(missing_ok=True)
                self._closed = True

    def _close_document(self) -> None:
        return None


class _JsonWriter(_AtomicWriter):
    extension = ".json"

    def __init__(
        self,
        target_base: Path,
        collection_name: str,
        metadata: Mapping[str, Any],
    ):
        super().__init__(target_base)
        self._file = _open_private_text(
            self.part_path,
            encoding="utf-8",
            newline="",
        )
        prefix = dict(metadata)
        prefix["schema_version"] = 1
        serialized = json.dumps(prefix, ensure_ascii=False, indent=2, default=_json_default)
        self._file.write(serialized[:-2])
        self._file.write(f',\n  "{collection_name}": [')
        self._first = True

    def add(self, record: Mapping[str, Any]) -> None:
        if not self._first:
            self._file.write(",")
        self._file.write("\n")
        payload = json.dumps(record, ensure_ascii=False, indent=2, default=_json_default)
        self._file.write("    " + payload.replace("\n", "\n    "))
        self._first = False

    def _close_document(self) -> None:
        if not self._first:
            self._file.write("\n")
        self._file.write("  ]\n}\n")


class _CsvWriter(_AtomicWriter):
    extension = ".csv"

    def __init__(self, target_base: Path, fields: Sequence[str]):
        super().__init__(target_base)
        self._fields = fields
        self._file = _open_private_text(
            self.part_path,
            encoding="utf-8-sig",
            newline="",
        )
        self._writer = csv.DictWriter(self._file, fieldnames=fields, extrasaction="ignore")
        self._writer.writeheader()

    def add(self, record: Mapping[str, Any]) -> None:
        row: Dict[str, Any] = {}
        for field in self._fields:
            value = record.get(field)
            if isinstance(value, (list, dict)):
                value = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            row[field] = _spreadsheet_safe(value)
        self._writer.writerow(row)


_HTML_STYLE = """
:root{color-scheme:light;--ink:#202124;--muted:#667085;--line:#d9dee7;--paper:#fff;--wash:#f5f7fa;--accent:#1769aa}
*{box-sizing:border-box}body{margin:0;background:var(--wash);color:var(--ink);font:14px/1.55 sans-serif}
main{width:min(1120px,calc(100% - 32px));margin:32px auto 64px}header{border-bottom:3px solid var(--accent);padding:0 0 18px;margin-bottom:20px}
h1{font-size:26px;margin:0 0 6px;letter-spacing:0}h2{font-size:17px;letter-spacing:0}.meta{color:var(--muted);margin:0}
.chat,.message{background:var(--paper);border:1px solid var(--line);border-radius:6px;padding:16px;margin:0 0 10px}
.chat h2,.message h2{margin:0 0 10px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:8px 18px}
dl{margin:0}dt{font-size:12px;color:var(--muted);font-weight:700}dd{margin:0 0 8px;overflow-wrap:anywhere}.warning{color:#9a3412}
.admins{margin:10px 0 0;padding-left:20px}.date{margin:22px 0 10px;color:var(--muted);font-size:13px}.sender{font-weight:700}.time{color:var(--muted);font-size:12px;margin-left:8px}
.content{white-space:pre-wrap;overflow-wrap:anywhere;margin-top:8px}.reply{font-size:12px}a{color:var(--accent)}
@media(max-width:600px){main{width:min(100% - 20px,1120px);margin-top:18px}.chat,.message{padding:12px}}
""".strip()


class _HtmlWriter(_AtomicWriter):
    extension = ".html"

    def __init__(
        self,
        target_base: Path,
        kind: str,
        metadata: Mapping[str, Any],
        labels: Mapping[str, str],
    ):
        super().__init__(target_base)
        self._kind = kind
        self._labels = labels
        self._last_date = None
        self._file = _open_private_text(
            self.part_path,
            encoding="utf-8",
            newline="",
        )
        title = html.escape(str(metadata.get("title") or labels.get("title", "Export")))
        exported_at = html.escape(str(metadata.get("exported_at") or ""))
        self._file.write("<!doctype html><html><head><meta charset=\"utf-8\">")
        self._file.write('<meta name="viewport" content="width=device-width,initial-scale=1">')
        self._file.write(f"<title>{title}</title><style>{_HTML_STYLE}</style></head><body><main>")
        self._file.write(f"<header><h1>{title}</h1><p class=\"meta\">{exported_at}</p></header>")

    def add(self, record: Mapping[str, Any]) -> None:
        if self._kind == "chats":
            self._add_chat(record)
        else:
            self._add_message(record)

    def _label(self, key: str) -> str:
        return html.escape(self._labels.get(key, key))

    @staticmethod
    def _value(value: Any) -> str:
        if value is None or value == "":
            return "-"
        return html.escape(str(value))

    def _add_chat(self, record: Mapping[str, Any]) -> None:
        chat_id = self._value(record.get("chat_id"))
        title = self._value(record.get("title"))
        link = record.get("public_link")
        title_html = f'<a href="{html.escape(str(link), quote=True)}">{title}</a>' if link else title
        self._file.write(f'<article class="chat" id="chat-{chat_id}"><h2>{title_html}</h2><div class="grid">')
        for key in ("chat_id", "kind", "created_at", "username", "member_count", "description"):
            self._file.write(f"<dl><dt>{self._label(key)}</dt><dd>{self._value(record.get(key))}</dd></dl>")
        self._file.write("</div>")
        admins = record.get("administrators") or []
        self._file.write(f"<h3>{self._label('administrators')} ({len(admins)})</h3>")
        if admins:
            self._file.write('<ul class="admins">')
            for admin in admins:
                username = f" @{admin.get('username')}" if admin.get("username") else ""
                bot = f" {self._labels.get('bot', 'bot')}" if admin.get("is_bot") else ""
                text = f"{admin.get('name') or admin.get('user_id')} ({admin.get('role')}){username}{bot} [{admin.get('user_id')}]"
                self._file.write(f"<li>{html.escape(text)}</li>")
            self._file.write("</ul>")
        else:
            self._file.write(f"<p>{self._label('none')}</p>")
        if record.get("export_warning"):
            self._file.write(f'<p class="warning">{self._value(record.get("export_warning"))}</p>')
        self._file.write("</article>")

    def _add_message(self, record: Mapping[str, Any]) -> None:
        date = str(record.get("date") or "")
        day = date[:10]
        if day and day != self._last_date:
            self._file.write(f'<h2 class="date">{html.escape(day)}</h2>')
            self._last_date = day
        message_id = self._value(record.get("message_id"))
        sender = self._value(record.get("sender_name") or record.get("sender_id"))
        time_text = self._value(date[11:19] if len(date) >= 19 else date)
        self._file.write(f'<article class="message" id="message-{message_id}">')
        self._file.write(f'<span class="sender">{sender}</span><span class="time">{time_text}</span>')
        reply_id = record.get("reply_to_message_id")
        if reply_id:
            self._file.write(f' <a class="reply" href="#message-{int(reply_id)}">{self._label("reply_to")} #{int(reply_id)}</a>')
        self._file.write(f'<div class="content">{self._value(record.get("content"))}</div></article>')

    def _close_document(self) -> None:
        self._file.write("</main></body></html>\n")


class _HtmlArchiveWriter:
    """Collect message records into a paginated, offline ZIP archive."""

    def __init__(
        self,
        target_base: Path,
        metadata: Mapping[str, Any],
        labels: Mapping[str, str],
    ):
        self.final_path = Path(str(target_base) + ".html.zip")
        self.part_path = Path(str(self.final_path) + ".part")
        self._metadata = dict(metadata)
        self._labels = dict(labels)
        self._records: List[Dict[str, Any]] = []
        self._closed = False

    def add(self, record: Mapping[str, Any]) -> None:
        self._records.append(dict(record))

    def finalize(self) -> Path:
        if self._closed:
            return self.final_path
        manifest, chunks = prepare_archive(self._records, self._metadata, self._labels)
        archive_root = self.final_path.name.removesuffix(".html.zip")
        index_labels = dict(self._labels)
        index_labels["title"] = str(self._metadata.get("title") or index_labels.get("title", "Message archive"))
        self.part_path.unlink(missing_ok=True)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(self.part_path, flags, 0o600)
        os.close(fd)
        try:
            with zipfile.ZipFile(
                self.part_path,
                "w",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=6,
            ) as archive:
                archive.writestr(
                    f"{archive_root}/index.html",
                    render_index_html(index_labels, variant="ledger"),
                )
                archive.writestr(
                    f"{archive_root}/manifest.js",
                    manifest_script(manifest),
                )
                for chunk_id, records in enumerate(chunks):
                    archive.writestr(
                        f"{archive_root}/data/chunk-{chunk_id + 1:06d}.js",
                        chunk_script(chunk_id, records),
                    )
                archive.writestr(
                    f"{archive_root}/README.txt",
                    self._labels.get(
                        "archive_readme",
                        "Extract the archive, then open index.html in a browser.\n",
                    ),
                )
            with self.part_path.open("rb") as handle:
                os.fsync(handle.fileno())
            os.replace(self.part_path, self.final_path)
            os.chmod(self.final_path, 0o600)
            self._closed = True
            self._records.clear()
            return self.final_path
        except Exception:
            self.part_path.unlink(missing_ok=True)
            raise

    def abort(self) -> None:
        if not self._closed:
            self.part_path.unlink(missing_ok=True)
            self._records.clear()
            self._closed = True


class ExportWriterSet:
    """Fan records out to all selected formats with all-or-nothing publishing."""

    def __init__(self, writers: Iterable[_AtomicWriter]):
        self._writers = list(writers)

    def add(self, record: Mapping[str, Any]) -> None:
        for writer in self._writers:
            writer.add(record)

    def finalize(self) -> List[Path]:
        finalized: List[Path] = []
        try:
            for writer in self._writers:
                finalized.append(writer.finalize())
            return finalized
        except Exception:
            for path in finalized:
                path.unlink(missing_ok=True)
            self.abort()
            raise

    def abort(self) -> None:
        for writer in self._writers:
            writer.abort()


def create_writer_set(
    target_base: Path,
    kind: str,
    formats: Sequence[str],
    metadata: Mapping[str, Any],
    labels: Mapping[str, str],
) -> ExportWriterSet:
    collection_name = "chats" if kind == "chats" else "messages"
    fields = CHAT_FIELDS if kind == "chats" else MESSAGE_FIELDS
    writers: List[_AtomicWriter] = []
    try:
        for fmt in formats:
            if fmt == "json":
                writers.append(_JsonWriter(target_base, collection_name, metadata))
            elif fmt == "csv":
                writers.append(_CsvWriter(target_base, fields))
            elif fmt == "html":
                if kind == "messages":
                    writers.append(_HtmlArchiveWriter(target_base, metadata, labels))
                else:
                    writers.append(_HtmlWriter(target_base, kind, metadata, labels))
            else:
                raise ValueError(f"Unsupported export format: {fmt}")
    except Exception:
        for writer in writers:
            writer.abort()
        raise
    return ExportWriterSet(writers)
