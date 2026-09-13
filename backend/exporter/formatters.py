"""Streaming JSON, CSV, and offline HTML export writers."""

import csv
import html
import json
import os
import zipfile
from array import array
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Sequence, Tuple

from . import html_viewer
from .html_viewer import (
    ArchiveReplyIndex,
    archive_chunk_entry,
    archive_manifest,
    chunk_script,
    compact_json,
    manifest_script,
    preview_fields,
    render_index_html,
)

CHAT_FIELDS = (
    "chat_id",
    "title",
    "kind",
    "status",
    "created_at",
    "joined_at",
    "username",
    "public_link",
    "is_public",
    "member_count",
    "message_count",
    "last_message_id",
    "last_message_at",
    "last_message_text",
    "unread_count",
    "is_archived",
    "description",
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
    "date_utc",
    "sender_type",
    "sender_first_name",
    "sender_last_name",
    "sender_is_bot",
    "sender_phone",
    "sender_is_verified",
    "sender_is_premium",
    "sender_is_scam",
    "sender_is_fake",
    "sender_is_contact",
    "sender_is_mutual_contact",
    "reply_to_top_id",
    "edited_at_utc",
    "forward_from_id",
    "forward_from_name",
    "forward_date",
    "forward_date_utc",
    "via_bot_id",
    "post_author",
    "views",
    "forwards",
    "replies_count",
    "media_id",
    "media_mime_type",
    "media_file_name",
    "media_size",
    "media_duration",
    "service_action",
    "is_outgoing",
    "is_mentioned",
    "is_media_unread",
    "is_silent",
    "is_post",
    "is_from_scheduled",
    "is_pinned",
    "is_forwarding_restricted",
    "entities",
    "reactions",
    "reply_markup",
    "restriction_reason",
)

HTML_MESSAGE_FIELDS = (
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
    "forward_from_id",
    "forward_from_name",
    "post_author",
    "views",
    "forwards",
    "replies_count",
)


# Records buffered in memory before the HTML archive spools them to disk.
_SPOOL_FRAGMENT_RECORDS = 500


def _message_id(value: Any) -> int:
    """Telegram message ids are integers; 0 marks a record without one."""
    return int(value) if isinstance(value, int) else 0


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
:root{color-scheme:light;--ink:#202124;--muted:#667085;--line:#e2e6ec;--paper:#fff;--wash:#f5f7fa;--accent:#1769aa;--ok:#0f7b4f;--warn:#a15c07;--bad:#b42318}
*{box-sizing:border-box}body{margin:0;background:var(--wash);color:var(--ink);font:13px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif}
main{width:min(1500px,calc(100% - 24px));margin:18px auto 48px}
/* The chat list is a dense table, so it reads better in a narrower column. */
main:has(.chats-table){width:min(1180px,calc(100% - 24px))}
header{border-bottom:3px solid var(--accent);padding:0 0 10px;margin-bottom:10px}
h1{font-size:20px;margin:0 0 3px;letter-spacing:0}.meta{color:var(--muted);margin:0;font-size:12px}
/* Message exports keep the card layout; chat lists use the compact table. */
.chat,.message{background:var(--paper);border:1px solid var(--line);border-radius:6px;padding:16px;margin:0 0 10px}
.chat h2,.message h2{margin:0 0 10px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:8px 18px}
dl{margin:0}dt{font-size:12px;color:var(--muted);font-weight:700}dd{margin:0 0 8px;overflow-wrap:anywhere}.warning{color:#9a3412}
.date{margin:22px 0 10px;color:var(--muted);font-size:13px}.sender{font-weight:700}.time{color:var(--muted);font-size:12px;margin-left:8px}
.content{white-space:pre-wrap;overflow-wrap:anywhere;margin-top:8px}.reply{font-size:12px}a{color:var(--accent)}
.chats-toolbar{position:sticky;top:0;z-index:3;display:flex;flex-wrap:wrap;gap:8px;align-items:center;background:var(--wash);padding:8px 0;border-bottom:1px solid var(--line)}
.chats-search{position:relative;flex:1 1 260px;max-width:420px}
.chats-search input{width:100%;height:30px;padding:0 26px 0 9px;font:inherit;background:var(--paper);border:1px solid var(--line);border-radius:5px}
.chats-search input:focus{outline:2px solid rgba(23,105,170,.25);border-color:var(--accent)}
.chats-search button{position:absolute;top:0;right:0;width:26px;height:30px;padding:0;border:0;background:none;color:var(--muted);cursor:pointer;font-size:15px;line-height:1}
.chats-count{margin-left:auto;color:var(--muted);font-size:12px;font-variant-numeric:tabular-nums}
.chats-table{width:100%;border-collapse:collapse;background:var(--paper);table-layout:fixed}
.chats-table th,.chats-table td{padding:4px 8px;text-align:left;border-bottom:1px solid var(--line);vertical-align:middle;overflow-wrap:anywhere}
/* Only the chat name flexes; every other column is sized to its own content
   so the name absorbs the leftover width instead of an unrelated column. */
.chats-table th:first-child,.chats-table td:first-child{width:auto}
.chats-table th:nth-child(2),.chats-table td:nth-child(2){width:86px}
.chats-table th:nth-child(3),.chats-table td:nth-child(3){width:82px}
.chats-table th:nth-child(4),.chats-table td:nth-child(4){width:88px}
.chats-table th:nth-child(5),.chats-table td:nth-child(5){width:92px}
.chats-table th:nth-child(6),.chats-table td:nth-child(6){width:132px}
.chats-table th:nth-child(7),.chats-table td:nth-child(7){width:150px}
.chats-table td{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.chats-table td.cell-last .preview{color:var(--muted)}
.chats-table thead th{position:sticky;top:47px;background:#eef1f5;font-size:11px;text-transform:uppercase;letter-spacing:.03em;color:var(--muted);cursor:pointer;user-select:none;white-space:nowrap;z-index:2}
.chats-table thead th[data-sort]:hover{color:var(--accent)}
.chats-table thead th .arrow{color:var(--accent);font-size:10px}
.chats-table tbody tr:hover{background:#f8fafc}
.chats-table tbody tr[hidden]{display:none}
.chats-table td.cell-title{font-weight:600}.chats-table td.cell-title a{color:var(--ink);text-decoration:none}
.chats-table td.cell-title a:hover{text-decoration:underline}
.chats-table td.num{text-align:right;font-variant-numeric:tabular-nums}
.chats-table td.cell-last{color:var(--muted)}
.chats-table .warn-cell::after{content:"\\26A0";margin-left:4px;color:var(--warn);cursor:help}
.status{display:inline-block;padding:1px 6px;border-radius:9px;font-size:11px;line-height:16px;white-space:nowrap;background:#eef1f5;color:var(--muted)}
.status-ok{background:#e6f5ec;color:var(--ok)}.status-warn{background:#fdf2e2;color:var(--warn)}.status-bad{background:#fde8e6;color:var(--bad)}
.chats-expand td{background:#f8fafc;padding:8px 10px 10px}
.chats-facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:6px 16px;margin:0}
.chats-facts div{min-width:0}.chats-facts dt{font-size:11px}.chats-facts dd{margin:0;font-size:12px}
/* Free text runs the full width and wraps instead of being clipped to a cell. */
.chats-facts div.wide{grid-column:1/-1}
.chats-facts div.wide dd{white-space:pre-wrap;overflow-wrap:anywhere;max-height:16em;overflow:auto}
.chats-none{padding:22px;text-align:center;color:var(--muted)}
@media(max-width:900px){.chats-table{table-layout:auto}.col-hide{display:none}}
@media(max-width:600px){main{width:calc(100% - 14px);margin-top:12px}.chat,.message{padding:12px}.chats-table thead th{top:0}}
""".strip()

# Compact chat-list shell: a searchable, sortable table whose rows expand into
# the per-chat facts on demand.
_CHAT_LIST_SCRIPT = """
(function () {
  var table = document.getElementById("chats");
  var body = document.getElementById("chats-body");
  if (!table || !body) { return; }
  var search = document.getElementById("chats-search");
  var clear = document.getElementById("chats-clear");
  var rows = Array.prototype.slice.call(body.querySelectorAll("tr.chats-row"));
  var total = rows.length;

  function applySearch() {
    var query = ((search && search.value) || "").trim().toLowerCase();
    var shown = 0;
    for (var i = 0; i < rows.length; i++) {
      var hit = !query || (rows[i].dataset.search || "").indexOf(query) !== -1;
      rows[i].hidden = !hit;
      var expand = rows[i].nextElementSibling;
      if (expand && expand.classList.contains("chats-expand")) {
        expand.hidden = true;
      }
      if (!hit) { rows[i].dataset.open = "0"; }
      if (hit) { shown++; }
    }
    var counter = document.getElementById("chats-count");
    if (counter) {
      counter.textContent = query
        ? counter.dataset.filtered.replace("{shown}", shown).replace("{total}", total)
        : counter.dataset.all.replace("{total}", total);
    }
    var none = document.getElementById("chats-none");
    if (none) { none.hidden = shown !== 0; }
  }

  function buildDetails(row) {
    var source = document.getElementById("facts-" + row.dataset.chatId);
    if (!source) { return null; }
    var facts = JSON.parse(source.textContent);
    var list = document.createElement("dl");
    list.className = "chats-facts";
    for (var i = 0; i < facts.length; i++) {
      var item = document.createElement("div");
      if (facts[i].length > 3 && facts[i][3]) { item.className = "wide"; }
      var term = document.createElement("dt");
      term.textContent = facts[i][0];
      var value = document.createElement("dd");
      if (facts[i][2]) {
        var link = document.createElement("a");
        link.href = facts[i][2];
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = facts[i][1];
        value.appendChild(link);
      } else {
        value.textContent = facts[i][1];
      }
      item.appendChild(term);
      item.appendChild(value);
      list.appendChild(item);
    }
    var cell = document.createElement("td");
    cell.colSpan = table.tHead.rows[0].cells.length;
    cell.appendChild(list);
    var expand = document.createElement("tr");
    expand.className = "chats-expand";
    expand.appendChild(cell);
    row.parentNode.insertBefore(expand, row.nextSibling);
    row.dataset.built = "1";
    return expand;
  }

  body.addEventListener("click", function (event) {
    var target = event.target;
    if (target.closest && target.closest("a")) { return; }
    var row = target.closest ? target.closest("tr.chats-row") : null;
    if (!row) { return; }
    var open = row.dataset.open === "1";
    var expand = row.nextElementSibling;
    if (!expand || !expand.classList.contains("chats-expand")) {
      expand = buildDetails(row);
    }
    if (!expand) { return; }
    row.dataset.open = open ? "0" : "1";
    expand.hidden = open;
    var arrow = row.querySelector(".arrow");
    if (arrow) { arrow.textContent = open ? "\u25B8" : "\u25BE"; }
  });

  var head = table.tHead;
  if (head) {
    var sort = { key: "", direction: 1 };
    head.style.cursor = "pointer";
    head.addEventListener("click", function (event) {
      var th = event.target.closest ? event.target.closest("th") : null;
      if (!th || !th.dataset.sort) { return; }
      var key = th.dataset.sort;
      sort.direction = sort.key === key ? -sort.direction : 1;
      sort.key = key;
      var numeric = th.dataset.type === "number" || th.dataset.type === "date";
      rows.sort(function (a, b) {
        var left = a.dataset[key] || "";
        var right = b.dataset[key] || "";
        if (numeric) {
          return ((Number(left) || 0) - (Number(right) || 0)) * sort.direction;
        }
        return left.localeCompare(right) * sort.direction;
      });
      rows.forEach(function (row) {
        var expand = row.nextElementSibling;
        if (expand && expand.classList.contains("chats-expand")) {
          body.appendChild(expand);
        }
        body.appendChild(row);
      });
      Array.prototype.forEach.call(head.querySelectorAll("th .arrow"), function (node) {
        node.textContent = "";
      });
      var arrow = th.querySelector(".arrow");
      if (arrow) { arrow.textContent = sort.direction > 0 ? "\u25B4" : "\u25BE"; }
      applySearch();
    });
  }

  if (search) {
    search.addEventListener("input", applySearch);
    search.addEventListener("keydown", function (event) {
      if (event.key === "Escape") { search.value = ""; applySearch(); }
    });
  }
  if (clear) {
    clear.addEventListener("click", function () {
      if (search) { search.value = ""; applySearch(); search.focus(); }
    });
  }
  applySearch();
})();
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

    # -- chat list --

    def _chat_head(self) -> None:
        columns = (
            ("title", "text", ""),
            ("kind", "text", "col-hide"),
            ("status", "text", ""),
            ("member_count", "number", "num col-hide"),
            ("message_count", "number", "num"),
            ("joined_at", "date", "col-hide"),
            ("last_message_at", "date", ""),
        )
        labels = self._labels
        total = labels.get("chats_total", "{total}")
        filtered = labels.get("chats_filtered_count", "{shown}/{total}")
        self._file.write('<section class="chats-toolbar">')
        self._file.write(
            '<span class="chats-search">'
            f'<input id="chats-search" type="search" autocomplete="off" '
            f'placeholder="{html.escape(labels.get("chats_search_placeholder", "Search"))}">'
            f'<button id="chats-clear" type="button" title="{html.escape(labels.get("reset_filters", "Reset"))}">&times;</button>'
            "</span>"
        )
        self._file.write(
            f'<span class="chats-count" id="chats-count" data-all="{html.escape(total)}"'
            f' data-filtered="{html.escape(filtered)}"></span>'
        )
        self._file.write("</section>")
        self._file.write('<table class="chats-table" id="chats"><thead><tr>')
        for key, sort_type, extra in columns:
            css = f' class="{extra}"' if extra else ""
            self._file.write(
                f'<th{css} data-sort="{key}" data-type="{sort_type}" '
                f'title="{html.escape(labels.get("chats_sort_hint", "Sort"))}">'
                f'{self._label(key)} <span class="arrow"></span></th>'
            )
        self._file.write("</tr></thead><tbody id=\"chats-body\">")
        self._head_written = True

    @staticmethod
    def _status_tone(status: str) -> str:
        if status == "ok":
            return "status-ok"
        if status in ("readonly",):
            return "status-warn"
        return "status-bad"

    @staticmethod
    def _short_date(value: Any) -> str:
        text = str(value or "")
        return text[:16].replace("T", " ") if text else "-"

    @staticmethod
    def _number(value: Any) -> str:
        return "-" if value in (None, "") else f"{int(value):,}"

    def _status_label(self, status: Any) -> tuple[str, str]:
        raw = str(status or "unknown")
        return self._labels.get(f"status_{raw}", raw), self._status_tone(raw)

    def _add_chat(self, record: Mapping[str, Any]) -> None:
        if not getattr(self, "_head_written", False):
            self._chat_head()
        chat_id = self._value(record.get("chat_id"))
        title = self._value(record.get("title"))
        link = record.get("public_link")
        title_html = (
            f'<a href="{html.escape(str(link), quote=True)}" target="_blank" rel="noopener noreferrer">{title}</a>'
            if link
            else title
        )
        status_text, status_tone = self._status_label(record.get("status"))
        status_cell = f'<span class="status {status_tone}">{html.escape(status_text)}</span>'
        last_at = self._short_date(record.get("last_message_at"))
        preview = str(record.get("last_message_text") or "")
        if preview:
            preview = preview.replace("\n", " ")
            preview = preview[:60] + ("…" if len(preview) > 60 else "")
            last_cell = f'{html.escape(last_at)} <span class="preview">{html.escape(preview)}</span>'
        else:
            last_cell = html.escape(last_at)
        warning = record.get("export_warning")
        warn_class = ' class="cell-last warn-cell"' if warning else ' class="cell-last"'
        warn_title = (
            f' title="{html.escape(str(warning), quote=True)}"' if warning else ""
        )
        search_blob = " ".join(
            str(record.get(field) or "")
            for field in ("title", "username", "chat_id", "kind", "status")
        ).lower()
        self._file.write(
            f'<tr class="chats-row" id="chat-{chat_id}" data-chat-id="{chat_id}"'
            f' data-search="{html.escape(search_blob, quote=True)}"'
            f' data-title="{html.escape(str(record.get("title") or ""), quote=True)}"'
            f' data-status="{html.escape(status_text, quote=True)}"'
            f' data-kind="{html.escape(str(record.get("kind") or ""), quote=True)}"'
            f' data-member_count="{record.get("member_count") or 0}"'
            f' data-message_count="{record.get("message_count") or 0}"'
            f' data-joined_at="{html.escape(str(record.get("joined_at") or ""), quote=True)}"'
            f' data-last_message_at="{html.escape(str(record.get("last_message_at") or ""), quote=True)}">'
            f'<td class="cell-title"><span class="arrow">&#9656;</span> {title_html}</td>'
            f'<td class="col-hide">{self._value(record.get("kind"))}</td>'
            f"<td>{status_cell}</td>"
            f'<td class="num col-hide">{self._number(record.get("member_count"))}</td>'
            f'<td class="num">{self._number(record.get("message_count"))}</td>'
            f'<td class="col-hide" title="{html.escape(str(record.get("joined_at") or ""), quote=True)}">'
            f'{html.escape(self._short_date(record.get("joined_at")))}</td>'
            f'<td{warn_class}{warn_title} title="{html.escape(str(record.get("last_message_at") or ""), quote=True)}">'
            f"{last_cell}</td>"
            "</tr>"
        )
        self._write_chat_facts(record, chat_id)

    def _fact_text(self, value: Any) -> str:
        """Render a detail value for a human, not for a repr."""
        if value is None:
            return "-"
        if isinstance(value, bool):
            return self._labels.get("yes" if value else "no", "yes" if value else "no")
        return str(value)

    def _write_chat_facts(self, record: Mapping[str, Any], chat_id: str) -> None:
        """Emit the per-chat details as data the row expands into on demand.

        Writing them as inert JSON instead of a hidden table row keeps the
        served page close to the size of the row set itself.
        """
        facts = []
        for key, value, link, wide in (
            ("chat_id", record.get("chat_id"), None, False),
            ("kind", record.get("kind"), None, False),
            ("username", record.get("username"), None, False),
            ("public_link", record.get("public_link"), record.get("public_link"), False),
            ("created_at", self._short_date(record.get("created_at")), None, False),
            ("joined_at", self._short_date(record.get("joined_at")), None, False),
            ("unread_count", record.get("unread_count"), None, False),
            ("is_archived", record.get("is_archived"), None, False),
            # Free text gets the full width so it can wrap.
            ("description", record.get("description"), None, True),
            ("export_warning", record.get("export_warning"), None, True),
        ):
            if value in (None, ""):
                continue
            facts.append(
                [
                    self._labels.get(key, key),
                    self._fact_text(value),
                    str(link) if link else "",
                    wide,
                ]
            )
        payload = json.dumps(facts, ensure_ascii=False, separators=(",", ":"))
        # A literal closing tag inside the data would end this block early.
        payload = payload.replace("</", "<\\/")
        self._file.write(
            f'<script type="application/json" id="facts-{chat_id}">{payload}</script>'
        )

    # -- message history --

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
        if self._kind == "chats":
            if not getattr(self, "_head_written", False):
                self._chat_head()
            self._file.write("</tbody></table>")
            self._file.write(
                f'<p class="chats-none" id="chats-none" hidden>'
                f'{html.escape(self._labels.get("chats_no_results", "No results"))}</p>'
            )
            self._file.write(f"<script>{_CHAT_LIST_SCRIPT}</script>")
        self._file.write("</main></body></html>\n")


class _HtmlArchiveWriter:
    """Stream message records into a paginated, offline ZIP archive.

    Records are spooled to a private temporary file as they arrive, so an
    archive of any size is written with bounded memory.
    """

    def __init__(
        self,
        target_base: Path,
        metadata: Mapping[str, Any],
        labels: Mapping[str, str],
    ):
        self.final_path = Path(str(target_base) + ".html.zip")
        self.part_path = Path(str(self.final_path) + ".part")
        self.spool_path = Path(str(self.part_path) + ".records")
        self._metadata = dict(metadata)
        self._labels = dict(labels)
        self._message_ids = array("q")
        self._reply_ids = array("q")
        self._fragment: List[Dict[str, Any]] = []
        self._closed = False
        self._spool = _open_private_text(
            self.spool_path,
            encoding="utf-8",
            newline="",
        )

    def add(self, record: Mapping[str, Any]) -> None:
        filtered = {
            field: record.get(field) for field in HTML_MESSAGE_FIELDS if field in record
        }
        self._fragment.append(filtered)
        self._message_ids.append(_message_id(filtered.get("message_id")))
        self._reply_ids.append(_message_id(filtered.get("reply_to_message_id")))
        if len(self._fragment) >= _SPOOL_FRAGMENT_RECORDS:
            self._spool_fragment()

    def finalize(self) -> Path:
        if self._closed:
            return self.final_path
        try:
            self._spool_fragment()
            self._close_spool()
            self._write_archive()
        except Exception:
            self.part_path.unlink(missing_ok=True)
            raise
        finally:
            self._close_spool()
            self.spool_path.unlink(missing_ok=True)
            self._fragment = []
        self._closed = True
        return self.final_path

    def abort(self) -> None:
        if self._closed:
            return
        self._close_spool()
        self.spool_path.unlink(missing_ok=True)
        self.part_path.unlink(missing_ok=True)
        self._fragment = []
        self._closed = True

    def _spool_fragment(self) -> None:
        if not self._fragment:
            return
        self._spool.write(compact_json(self._fragment))
        self._spool.write("\n")
        self._fragment = []

    def _close_spool(self) -> None:
        if not self._spool.closed:
            self._spool.close()

    def _iter_spooled_records(self) -> Iterator[Dict[str, Any]]:
        with self.spool_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                yield from json.loads(line)

    def _collect_previews(
        self, wanted: frozenset[int]
    ) -> Dict[int, Tuple[Any, Any, Any, Any]]:
        previews: Dict[int, Tuple[Any, Any, Any, Any]] = {}
        if not wanted:
            return previews
        for index, record in enumerate(self._iter_spooled_records()):
            if index in wanted:
                previews[index] = preview_fields(record)
                if len(previews) == len(wanted):
                    break
        return previews

    def _write_archive(self) -> None:
        index = ArchiveReplyIndex(
            self._message_ids,
            self._reply_ids,
            self._labels.get("unknown_sender", "Unknown sender"),
        )
        previews = self._collect_previews(index.preview_indices)
        archive_root = self.final_path.name.removesuffix(".html.zip")
        index_labels = dict(self._labels)
        index_labels["title"] = str(
            self._metadata.get("title")
            or index_labels.get("title", "Message archive")
        )
        self.part_path.unlink(missing_ok=True)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(self.part_path, flags, 0o600)
        os.close(fd)
        with zipfile.ZipFile(
            self.part_path,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=6,
        ) as archive:
            chunks, total = self._write_chunks(archive, archive_root, index, previews)
            archive.writestr(
                f"{archive_root}/index.html",
                render_index_html(index_labels, variant="ledger"),
            )
            archive.writestr(
                f"{archive_root}/manifest.js",
                manifest_script(
                    archive_manifest(
                        self._metadata, self._labels, chunks, total
                    )
                ),
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

    def _write_chunks(
        self,
        archive: zipfile.ZipFile,
        archive_root: str,
        index: ArchiveReplyIndex,
        previews: Mapping[int, Tuple[Any, Any, Any, Any]],
    ) -> Tuple[List[Dict[str, Any]], int]:
        chunks: List[Dict[str, Any]] = []
        buffer: List[Dict[str, Any]] = []
        buffer_bytes = 2
        start_index = 0
        total = 0
        min_date = None
        max_date = None
        for record_index, record in enumerate(self._iter_spooled_records()):
            annotated = dict(record)
            annotated["_archive"] = index.annotation(record_index, record, previews)
            size = len(compact_json(annotated).encode("utf-8")) + (1 if buffer else 0)
            if buffer and (
                len(buffer) >= html_viewer.ARCHIVE_MAX_RECORDS
                or buffer_bytes + size > html_viewer.ARCHIVE_MAX_BYTES
            ):
                entry = archive_chunk_entry(
                    len(chunks), len(buffer), start_index, min_date, max_date
                )
                archive.writestr(
                    f"{archive_root}/{entry['file']}",
                    chunk_script(len(chunks), buffer),
                )
                chunks.append(entry)
                start_index += len(buffer)
                buffer, buffer_bytes, min_date, max_date = [], 2, None, None
            buffer.append(annotated)
            buffer_bytes += size
            date = str(record.get("date")) if record.get("date") else None
            if date:
                min_date = date if min_date is None or date < min_date else min_date
                max_date = date if max_date is None or date > max_date else max_date
            total += 1
        if buffer:
            entry = archive_chunk_entry(
                len(chunks), len(buffer), start_index, min_date, max_date
            )
            archive.writestr(
                f"{archive_root}/{entry['file']}",
                chunk_script(len(chunks), buffer),
            )
            chunks.append(entry)
        return chunks, total


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
