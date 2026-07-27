"""Build the lightweight, offline viewer used by message HTML archives."""

from __future__ import annotations

import html
import json
from typing import Any, Dict, List, Mapping, Sequence, Tuple

ARCHIVE_MAX_RECORDS = 2000
ARCHIVE_MAX_BYTES = 8 * 1024 * 1024
ARCHIVE_CACHE_CHUNKS = 3


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _script_json(value: Any) -> str:
    """Serialize data for an inline script without allowing a script end tag."""
    return (
        _json_text(value)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def prepare_archive(
    records: Sequence[Mapping[str, Any]],
    metadata: Mapping[str, Any],
    labels: Mapping[str, str],
    *,
    max_records: int = ARCHIVE_MAX_RECORDS,
    max_bytes: int = ARCHIVE_MAX_BYTES,
) -> Tuple[Dict[str, Any], List[List[Dict[str, Any]]]]:
    """Add reply metadata and split records without changing the canonical export data."""
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

    # Telegram replies are acyclic. For malformed cycles, expose direct children
    # without allowing a corrupt record to block archive creation.
    for index, remaining in enumerate(remaining_children):
        if remaining:
            descendant_counts[index] = max(
                descendant_counts[index],
                len(children.get(index, [])),
            )

    unknown = labels.get("unknown_sender", "Unknown sender")
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
        record_bytes = len(_json_text(record).encode("utf-8")) + (1 if current else 0)
        if current and (len(current) >= max_records or current_bytes + record_bytes > max_bytes):
            chunks.append(current)
            current = []
            current_bytes = 2
        current.append(record)
        current_bytes += record_bytes
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
        "title": str(metadata.get("title") or labels.get("title", "Message archive")),
        "exported_at": str(metadata.get("exported_at") or ""),
        "chat_title": str(metadata.get("chat_title") or ""),
        "range_start": str(metadata.get("range_start") or ""),
        "range_end": str(metadata.get("range_end") or ""),
        "timezone": str(metadata.get("timezone") or ""),
        "total": len(copied),
        "default_page_size": 100,
        "page_sizes": [100, 500, 1000, 2000],
        "cache_chunks": ARCHIVE_CACHE_CHUNKS,
        "chunks": chunk_manifest,
        "labels": dict(labels),
    }
    return manifest, chunks


def manifest_script(manifest: Mapping[str, Any]) -> str:
    return f"window.TELE_RELAY_MANIFEST={_script_json(manifest)};\n"


def chunk_script(chunk_id: int, records: Sequence[Mapping[str, Any]]) -> str:
    return f"window.TeleRelayArchive.receiveChunk({chunk_id},{_script_json(records)});\n"


_VIEWER_STYLE = r"""
:root{color-scheme:light;--bg:#f4f5f7;--paper:#fff;--ink:#20242a;--muted:#68707c;--line:#d9dde3;--accent:#1769aa;--reply:#eef5fb;--danger:#9b2c2c;--radius:4px;--font:ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
*{box-sizing:border-box}html{scroll-behavior:auto}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 var(--font);letter-spacing:0}
button,input,select{font:inherit;color:inherit}button,input,select{border:1px solid var(--line);border-radius:var(--radius);background:var(--paper)}button{cursor:pointer}button:disabled{cursor:not-allowed;opacity:.45}
.shell{width:min(1080px,calc(100% - 24px));margin:20px auto 48px}.archive-header{display:flex;align-items:flex-end;justify-content:space-between;gap:24px;padding:0 0 14px;border-bottom:2px solid var(--ink)}
h1{margin:0;font-size:22px;line-height:1.2;letter-spacing:0}.meta,.summary,.status{margin:4px 0 0;color:var(--muted);font-size:12px}.summary{text-align:right}
.filters{display:grid;grid-template-columns:minmax(220px,2fr) repeat(2,minmax(140px,1fr)) auto auto;gap:8px;align-items:end;padding:14px 0;border-bottom:1px solid var(--line)}
.field{display:grid;gap:4px;min-width:0}.field>span{color:var(--muted);font-size:11px;font-weight:700}.field input,.field select{width:100%;height:34px;padding:5px 8px;min-width:0}.command{height:34px;padding:5px 12px;font-weight:700}.command.primary{background:var(--accent);border-color:var(--accent);color:#fff}
.scan{display:none;grid-template-columns:1fr auto;align-items:center;gap:10px;padding:8px 0;color:var(--muted);font-size:12px}.scan.active{display:grid}.scan progress{width:100%;height:6px;accent-color:var(--accent)}
.thread-bar{display:none;align-items:center;justify-content:space-between;gap:16px;padding:10px 0;border-bottom:1px solid var(--line)}.thread-bar.active{display:flex}.thread-title{font-weight:700}.thread-summary{margin-left:8px;color:var(--muted);font-size:12px}.thread-active .filters{display:none}
body.thread-active .message{padding-left:12px;padding-right:12px}
.toolbar{display:flex;align-items:center;justify-content:space-between;gap:12px;min-height:48px}.pager{display:flex;align-items:center;gap:7px;white-space:nowrap}.pager .field{display:flex;align-items:center;gap:6px}.pager select{height:30px;padding:3px 6px}.icon-button{width:32px;height:30px;padding:0;font-size:18px;line-height:1}.page-status{min-width:74px;text-align:center;font-variant-numeric:tabular-nums}
.bottom-toolbar{margin-top:14px;border-top:1px solid var(--line)}
.date-heading{position:sticky;top:0;z-index:1;margin:14px 0 6px;padding:5px 0;background:var(--bg);color:var(--muted);font-size:12px;font-weight:700;border-bottom:1px solid var(--line)}
.message{scroll-margin-top:34px;background:var(--paper);border:1px solid var(--line);border-radius:var(--radius);padding:10px 12px;margin:0 0 6px}.message.flash{outline:2px solid var(--accent);outline-offset:1px}
.message-head{display:flex;align-items:baseline;flex-wrap:wrap;gap:5px 9px}.sender{font-weight:700}.time,.message-link,.detail,.reply-count{color:var(--muted);font-size:12px}.message-link{text-decoration:none}.message-link:hover{text-decoration:underline}.detail{border:1px solid var(--line);border-radius:3px;padding:0 4px}
.content{margin:6px 0 0;white-space:pre-wrap;overflow-wrap:anywhere}.content a{color:var(--accent)}.reply{display:block;width:100%;margin:7px 0 2px;padding:6px 8px;text-align:left;background:var(--reply);border:0;border-left:3px solid var(--accent);border-radius:0}.reply:hover{filter:brightness(.98)}.reply.missing{cursor:default;border-left-color:var(--muted)}
.reply-title{display:block;color:var(--accent);font-size:12px;font-weight:700}.reply-preview{display:block;margin-top:2px;color:var(--muted);font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.reply-count{display:inline-block;margin-top:6px;color:var(--muted);font-size:12px}.thread-link{padding:0;border:0;background:transparent;color:var(--accent);font-weight:700;text-decoration:underline;text-underline-offset:2px}.empty{padding:42px 12px;text-align:center;color:var(--muted);border-top:1px solid var(--line)}.error{color:var(--danger)}
body.theme-telegram{--bg:#e8edf1;--paper:#fff;--ink:#1e2a32;--muted:#6c7b85;--line:#d4dde3;--accent:#168acd;--reply:#edf8fe;--radius:7px}.theme-telegram .message{max-width:860px}
body.theme-ledger{--bg:#fff;--paper:#fff;--ink:#161616;--muted:#666;--line:#bdbdbd;--accent:#14532d;--reply:#f2f7f3;--radius:0}.theme-ledger .message{border-width:0 0 1px;padding-left:2px;padding-right:2px}
body.theme-paper{--bg:#f3efe5;--paper:#fffdf7;--ink:#27241f;--muted:#766f62;--line:#d7cdbd;--accent:#8b3f2f;--reply:#f7eee7;--radius:3px;--font:Georgia,"Times New Roman",serif}
body.theme-midnight{color-scheme:dark;--bg:#16181b;--paper:#202328;--ink:#eef0f3;--muted:#a1a8b2;--line:#393e45;--accent:#63b3ed;--reply:#202f3a;--danger:#ff9b9b;--radius:4px}
body.theme-timeline{--bg:#f6f6f4;--paper:#fff;--ink:#222;--muted:#727272;--line:#dcdcd7;--accent:#b4492d;--reply:#fbf1ed;--radius:2px}.theme-timeline #messages{border-left:2px solid var(--line);padding-left:14px}.theme-timeline .message{position:relative}.theme-timeline .message:before{content:"";position:absolute;width:8px;height:8px;border-radius:50%;background:var(--accent);left:-20px;top:15px}
body.theme-contrast{--bg:#fff;--paper:#fff;--ink:#000;--muted:#333;--line:#000;--accent:#005fcc;--reply:#eaf3ff;--radius:0}.theme-contrast .message{border-width:2px}.theme-contrast .archive-header{border-width:4px}
body.theme-soft{--bg:#eef0f2;--paper:#fafbfc;--ink:#283038;--muted:#717b84;--line:#dfe3e7;--accent:#24746b;--reply:#eaf4f2;--radius:6px}.theme-soft .message{box-shadow:0 1px 2px rgba(20,30,40,.04)}
body.theme-terminal{color-scheme:dark;--bg:#111512;--paper:#151b17;--ink:#d7e7da;--muted:#839a87;--line:#314236;--accent:#65c477;--reply:#19261c;--danger:#ff8d8d;--radius:0;--font:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
body.theme-editorial{--bg:#f7f7f5;--paper:#fff;--ink:#1c1c1b;--muted:#777773;--line:#d8d8d2;--accent:#304f75;--reply:#eef2f6;--radius:1px;--font:Georgia,"Times New Roman",serif}.theme-editorial h1{font-size:26px}.theme-editorial .message{padding-top:13px;padding-bottom:13px}
@media(max-width:820px){.archive-header{align-items:flex-start;flex-direction:column;gap:7px}.summary{text-align:left}.filters{grid-template-columns:1fr 1fr}.filters .search-field{grid-column:1/-1}.toolbar{align-items:flex-start;flex-direction:column;padding:10px 0}.pager{width:100%;justify-content:flex-end}}
@media(max-width:520px){.shell{width:calc(100% - 14px);margin-top:10px}.filters{grid-template-columns:1fr}.filters .search-field{grid-column:auto}.message{padding:9px}.pager{justify-content:space-between}.pager .field>span{display:none}.date-heading{top:0}.thread-bar{align-items:flex-start;flex-direction:column;gap:8px}.thread-bar .command{width:100%}}
""".strip()


_VIEWER_SCRIPT = r"""
(() => {
  "use strict";
  const manifest = window.TELE_RELAY_MANIFEST;
  if (!manifest) return;
  const labels = manifest.labels || {};
  const cache = new Map();
  const pending = new Map();
  let matches = null;
  let currentPage = 1;
  let filterToken = 0;
  let renderToken = 0;
  let threadToken = 0;
  let threadState = null;

  const byId = (id) => document.getElementById(id);
  const text = (key, fallback) => labels[key] || fallback;
  const format = (template, values) => Object.entries(values).reduce(
    (result, [key, value]) => result.replaceAll(`{${key}}`, String(value)), template
  );
  const make = (tag, className, value) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (value !== undefined && value !== null) node.textContent = String(value);
    return node;
  };
  const dayOf = (record) => String(record.date || "").slice(0, 10);
  const timeOf = (value) => {
    const raw = String(value || "");
    return raw.length >= 19 ? raw.slice(11, 19) : raw;
  };

  function renderContent(value) {
    const content = make("div", "content");
    const raw = String(value || "");
    if (!window.linkify || typeof window.linkify.find !== "function") {
      content.textContent = raw;
      return content;
    }
    try {
      let cursor = 0;
      for (const match of window.linkify.find(raw)) {
        if (!match.isLink || match.start < cursor || match.end <= match.start) continue;
        content.appendChild(document.createTextNode(raw.slice(cursor, match.start)));
        const anchor = make("a", "", match.value);
        anchor.href = match.href;
        anchor.target = "_blank";
        anchor.rel = "noopener noreferrer";
        content.appendChild(anchor);
        cursor = match.end;
      }
      content.appendChild(document.createTextNode(raw.slice(cursor)));
    } catch (error) {
      content.textContent = raw;
    }
    return content;
  }

  function cacheChunk(id, records) {
    cache.delete(id);
    cache.set(id, records);
    while (cache.size > (manifest.cache_chunks || 3)) {
      cache.delete(cache.keys().next().value);
    }
  }

  window.TeleRelayArchive = {
    receiveChunk(id, records) {
      cacheChunk(id, records);
      const waiter = pending.get(id);
      if (waiter) {
        pending.delete(id);
        waiter.resolve(records);
      }
    }
  };

  function loadChunk(id) {
    if (cache.has(id)) {
      const records = cache.get(id);
      cacheChunk(id, records);
      return Promise.resolve(records);
    }
    if (window.TELE_RELAY_INLINE_CHUNKS && window.TELE_RELAY_INLINE_CHUNKS[id]) {
      const records = window.TELE_RELAY_INLINE_CHUNKS[id];
      cacheChunk(id, records);
      return Promise.resolve(records);
    }
    if (pending.has(id)) return pending.get(id).promise;
    const descriptor = manifest.chunks.find((chunk) => chunk.id === id);
    let resolvePromise;
    let rejectPromise;
    const promise = new Promise((resolve, reject) => {
      resolvePromise = resolve;
      rejectPromise = reject;
    });
    pending.set(id, {promise, resolve: resolvePromise, reject: rejectPromise});
    const script = document.createElement("script");
    script.src = descriptor.file;
    script.async = true;
    script.onerror = () => {
      pending.delete(id);
      script.remove();
      rejectPromise(new Error(format(text("load_error", "Unable to load {file}"), {file: descriptor.file})));
    };
    script.onload = () => {
      script.remove();
      if (!cache.has(id)) {
        pending.delete(id);
        rejectPromise(new Error(format(text("load_error", "Unable to load {file}"), {file: descriptor.file})));
      }
    };
    document.head.appendChild(script);
    return promise;
  }

  function descriptorFor(index) {
    let low = 0;
    let high = manifest.chunks.length - 1;
    while (low <= high) {
      const mid = (low + high) >> 1;
      const chunk = manifest.chunks[mid];
      if (index < chunk.start_index) high = mid - 1;
      else if (index >= chunk.start_index + chunk.count) low = mid + 1;
      else return chunk;
    }
    return null;
  }

  async function recordsAt(indices) {
    const descriptors = new Map();
    for (const index of indices) {
      const descriptor = descriptorFor(index);
      if (descriptor) descriptors.set(descriptor.id, descriptor);
    }
    const loaded = new Map();
    await Promise.all([...descriptors.keys()].map(async (id) => loaded.set(id, await loadChunk(id))));
    return indices.map((index) => {
      const descriptor = descriptorFor(index);
      return loaded.get(descriptor.id)[index - descriptor.start_index];
    });
  }

  function pageSize() {
    return Math.min(2000, Math.max(1, Number(byId("page-size").value) || 100));
  }
  function resultCount() {
    return matches === null ? manifest.total : matches.length;
  }
  function pageCount() {
    return Math.max(1, Math.ceil(resultCount() / pageSize()));
  }
  function pageIndices() {
    const start = (currentPage - 1) * pageSize();
    const end = Math.min(start + pageSize(), resultCount());
    if (matches === null) return Array.from({length: end - start}, (_, offset) => start + offset);
    return matches.slice(start, end);
  }

  function renderReply(record) {
    const info = record._archive && record._archive.reply;
    if (!info) return null;
    const available = Number.isInteger(info.target_index);
    const root = make(available ? "button" : "div", `reply${available ? "" : " missing"}`);
    if (available) {
      root.type = "button";
      root.dataset.replyIndex = String(info.target_index);
      root.title = text("open_reply", "Open original message");
    }
    const title = available
      ? format(text("reply_summary", "Reply to {sender} · {time} · #{id}"), {
          sender: info.sender || text("unknown_sender", "Unknown sender"),
          time: timeOf(info.date),
          id: info.message_id
        })
      : format(text("reply_missing", "Reply to #{id} · outside this export"), {id: info.message_id});
    root.appendChild(make("span", "reply-title", title));
    if (info.content) root.appendChild(make("span", "reply-preview", info.content));
    return root;
  }

  function renderMessage(record) {
    const article = make("article", "message");
    article.id = `message-${record.message_id}`;
    article.dataset.globalIndex = String(record._archive.index);
    const head = make("div", "message-head");
    head.appendChild(make("span", "sender", record.sender_name || record.sender_id || text("unknown_sender", "Unknown sender")));
    const timestampText = threadState
      ? String(record.date || "").slice(0, 19).replace("T", " ")
      : timeOf(record.date);
    const timestamp = make("time", "time", timestampText);
    timestamp.dateTime = record.date || "";
    head.appendChild(timestamp);
    const link = make("a", "message-link", `#${record.message_id}`);
    link.href = `#message-${record.message_id}`;
    head.appendChild(link);
    if (record.media_type && record.media_type !== "text") head.appendChild(make("span", "detail", record.media_type));
    if (record.edited_at) head.appendChild(make("span", "detail", text("edited", "edited")));
    article.appendChild(head);
    const reply = renderReply(record);
    if (reply) article.appendChild(reply);
    article.appendChild(renderContent(record.content));
    if (record._archive.reply_count) {
      const countText = format(text("reply_count", "{count} replies"), {count: record._archive.reply_count});
      if (threadState) {
        article.appendChild(make("span", "reply-count", countText));
      } else {
        const threadLink = make("button", "reply-count thread-link", countText);
        threadLink.type = "button";
        threadLink.dataset.threadIndex = String(record._archive.index);
        threadLink.title = text("open_thread", "Open reply list");
        article.appendChild(threadLink);
      }
    }
    return article;
  }

  async function renderPage(focusIndex) {
    const token = ++renderToken;
    currentPage = Math.min(Math.max(1, currentPage), pageCount());
    const indices = pageIndices();
    const container = byId("messages");
    container.replaceChildren(make("div", "empty", text("loading", "Loading...")));
    try {
      const records = await recordsAt(indices);
      if (token !== renderToken) return;
      const fragment = document.createDocumentFragment();
      let previousDay = null;
      for (const record of records) {
        const day = dayOf(record);
        if (!threadState && day && day !== previousDay) {
          fragment.appendChild(make("div", "date-heading", day));
          previousDay = day;
        }
        fragment.appendChild(renderMessage(record));
      }
      if (!records.length) fragment.appendChild(make("div", "empty", text("no_results", "No matching messages")));
      container.replaceChildren(fragment);
      updateToolbar();
      if (Number.isInteger(focusIndex)) {
        const target = container.querySelector(`[data-global-index="${focusIndex}"]`);
        if (target) {
          target.classList.add("flash");
          target.scrollIntoView({block: "center"});
          window.setTimeout(() => target.classList.remove("flash"), 1800);
        }
      }
    } catch (error) {
      if (token !== renderToken) return;
      const node = make("div", "empty error", error.message || String(error));
      container.replaceChildren(node);
    }
  }

  function updateToolbar() {
    const total = resultCount();
    const start = total ? (currentPage - 1) * pageSize() + 1 : 0;
    const end = Math.min(currentPage * pageSize(), total);
    const resultText = format(text("result_status", "{start}-{end} of {total}"), {start, end, total});
    const pageText = format(text("page_status", "{page} / {pages}"), {page: currentPage, pages: pageCount()});
    byId("status").textContent = resultText;
    byId("status-bottom").textContent = resultText;
    byId("page-status").textContent = pageText;
    byId("page-status-bottom").textContent = pageText;
    for (const id of ["previous-page", "previous-page-bottom"]) byId(id).disabled = currentPage <= 1;
    for (const id of ["next-page", "next-page-bottom"]) byId(id).disabled = currentPage >= pageCount();
  }

  function rowMatches(record, query, from, to) {
    const day = dayOf(record);
    if (from && (!day || day < from)) return false;
    if (to && (!day || day > to)) return false;
    if (!query) return true;
    const haystack = [record.content, record.text, record.sender_name, record.sender_username, record.sender_id, record.message_id]
      .filter((value) => value !== null && value !== undefined)
      .join("\n")
      .toLocaleLowerCase();
    return haystack.includes(query);
  }

  async function applyFilters() {
    if (threadState) return;
    const query = byId("search").value.trim().toLocaleLowerCase();
    const from = byId("date-from").value;
    const to = byId("date-to").value;
    const token = ++filterToken;
    if (!query && !from && !to) {
      matches = null;
      currentPage = 1;
      byId("scan").classList.remove("active");
      await renderPage();
      return;
    }
    const candidates = manifest.chunks.filter((chunk) => {
      if (from && chunk.max_date && chunk.max_date < from) return false;
      if (to && chunk.min_date && chunk.min_date > to) return false;
      return true;
    });
    const found = [];
    const scan = byId("scan");
    const progress = byId("scan-progress");
    scan.classList.add("active");
    progress.max = Math.max(1, candidates.length);
    progress.value = 0;
    try {
      for (let position = 0; position < candidates.length; position += 1) {
        if (token !== filterToken) return;
        const chunk = candidates[position];
        const records = await loadChunk(chunk.id);
        for (let offset = 0; offset < records.length; offset += 1) {
          if (rowMatches(records[offset], query, from, to)) found.push(chunk.start_index + offset);
        }
        progress.value = position + 1;
        byId("scan-label").textContent = format(text("filter_progress", "Filtering {current}/{total}"), {current: position + 1, total: candidates.length});
        await new Promise((resolve) => window.setTimeout(resolve, 0));
      }
    } catch (error) {
      if (token !== filterToken) return;
      scan.classList.remove("active");
      byId("messages").replaceChildren(make("div", "empty error", error.message || String(error)));
      return;
    }
    if (token !== filterToken) return;
    matches = found;
    currentPage = 1;
    scan.classList.remove("active");
    await renderPage();
  }

  async function openThread(rootIndex) {
    if (threadState) return;
    const token = ++threadToken;
    filterToken += 1;
    threadState = {
      matches,
      currentPage,
      pageSize: byId("page-size").value,
      scrollY: window.scrollY
    };
    document.body.classList.add("thread-active");
    byId("thread-bar").classList.add("active");
    byId("thread-title").textContent = text("thread_loading_title", "Reply list");
    byId("thread-summary").textContent = format(text("thread_loading", "Loading replies · {count} found"), {count: 0});
    byId("messages").replaceChildren(make("div", "empty", text("loading", "Loading...")));
    try {
      const discovered = new Map();
      const seen = new Set([rootIndex]);
      let frontier = [rootIndex];
      while (frontier.length) {
        if (token !== threadToken) return;
        const records = await recordsAt(frontier);
        const next = [];
        for (let position = 0; position < records.length; position += 1) {
          const index = frontier[position];
          const record = records[position];
          discovered.set(index, record);
          for (const childIndex of record._archive.children || []) {
            if (seen.has(childIndex)) continue;
            seen.add(childIndex);
            next.push(childIndex);
          }
        }
        frontier = next;
        byId("thread-summary").textContent = format(
          text("thread_loading", "Loading replies · {count} found"),
          {count: seen.size}
        );
        await new Promise((resolve) => window.setTimeout(resolve, 0));
      }
      if (token !== threadToken) return;
      const ordered = [];
      const visited = new Set();
      const visit = (index) => {
        if (visited.has(index)) return;
        visited.add(index);
        ordered.push(index);
        const record = discovered.get(index);
        for (const childIndex of (record && record._archive.children) || []) visit(childIndex);
      };
      visit(rootIndex);
      const root = discovered.get(rootIndex);
      matches = ordered;
      currentPage = 1;
      byId("thread-title").textContent = format(
        text("thread_title", "Reply list for #{id}"),
        {id: root.message_id}
      );
      byId("thread-summary").textContent = format(
        text("thread_summary", "{count} messages"),
        {count: ordered.length}
      );
      await renderPage();
      window.scrollTo(0, 0);
    } catch (error) {
      if (token !== threadToken) return;
      byId("messages").replaceChildren(make("div", "empty error", error.message || String(error)));
    }
  }

  async function closeThread() {
    if (!threadState) return;
    const previous = threadState;
    threadToken += 1;
    threadState = null;
    document.body.classList.remove("thread-active");
    byId("thread-bar").classList.remove("active");
    byId("page-size").value = previous.pageSize;
    matches = previous.matches;
    currentPage = previous.currentPage;
    await renderPage();
    window.requestAnimationFrame(() => window.scrollTo(0, previous.scrollY));
  }

  async function jumpTo(index) {
    if (threadState) {
      const position = matches.indexOf(index);
      if (position >= 0) {
        currentPage = Math.floor(position / pageSize()) + 1;
        await renderPage(index);
      }
      return;
    }
    filterToken += 1;
    matches = null;
    byId("search").value = "";
    byId("date-from").value = "";
    byId("date-to").value = "";
    byId("scan").classList.remove("active");
    currentPage = Math.floor(index / pageSize()) + 1;
    await renderPage(index);
  }

  function initialize() {
    document.title = manifest.title;
    byId("title").textContent = manifest.title;
    byId("meta").textContent = [manifest.range_start && `${text("range", "Range")}: ${manifest.range_start} - ${manifest.range_end}`, manifest.timezone].filter(Boolean).join(" · ");
    byId("summary").textContent = format(text("archive_summary", "{total} messages · exported {exported_at}"), {total: manifest.total, exported_at: manifest.exported_at});
    byId("search-label").textContent = text("search", "Search");
    byId("search").placeholder = text("search_placeholder", "Content, sender, or message ID");
    byId("date-from-label").textContent = text("date_from", "From");
    byId("date-to-label").textContent = text("date_to", "To");
    byId("apply-filters").textContent = text("apply_filters", "Apply");
    byId("reset-filters").textContent = text("reset_filters", "Reset");
    byId("close-thread").textContent = text("back_to_messages", "Back to messages");
    byId("page-size-label").textContent = text("page_size", "Per page");
    for (const id of ["previous-page", "previous-page-bottom"]) {
      byId(id).title = byId(id).ariaLabel = text("previous_page", "Previous page");
    }
    for (const id of ["next-page", "next-page-bottom"]) {
      byId(id).title = byId(id).ariaLabel = text("next_page", "Next page");
    }
    const size = byId("page-size");
    for (const value of manifest.page_sizes) size.appendChild(new Option(String(value), String(value), false, value === manifest.default_page_size));
    byId("apply-filters").addEventListener("click", applyFilters);
    byId("reset-filters").addEventListener("click", () => {
      byId("search").value = "";
      byId("date-from").value = "";
      byId("date-to").value = "";
      applyFilters();
    });
    byId("search").addEventListener("keydown", (event) => { if (event.key === "Enter") applyFilters(); });
    size.addEventListener("change", () => { currentPage = 1; renderPage(); });
    const previousPage = () => { if (currentPage > 1) { currentPage -= 1; renderPage(); window.scrollTo(0, 0); } };
    const nextPage = () => { if (currentPage < pageCount()) { currentPage += 1; renderPage(); window.scrollTo(0, 0); } };
    for (const id of ["previous-page", "previous-page-bottom"]) byId(id).addEventListener("click", previousPage);
    for (const id of ["next-page", "next-page-bottom"]) byId(id).addEventListener("click", nextPage);
    byId("close-thread").addEventListener("click", closeThread);
    byId("messages").addEventListener("click", (event) => {
      const thread = event.target.closest("[data-thread-index]");
      if (thread) {
        openThread(Number(thread.dataset.threadIndex));
        return;
      }
      const reply = event.target.closest("[data-reply-index]");
      if (reply) jumpTo(Number(reply.dataset.replyIndex));
    });
    renderPage();
  }
  initialize();
})();
""".strip()


def render_index_html(
    labels: Mapping[str, str],
    *,
    variant: str = "compact",
    inline_manifest: Mapping[str, Any] | None = None,
    inline_chunks: Sequence[Sequence[Mapping[str, Any]]] | None = None,
) -> str:
    """Render the viewer shell; demos may embed their manifest and chunks."""
    language = html.escape(labels.get("language", "en"), quote=True)
    title = html.escape(labels.get("title", "Message archive"))
    theme = html.escape(variant, quote=True)
    if inline_manifest is None:
        bootstrap = '<script src="manifest.js"></script>'
    else:
        inline = {str(index): chunk for index, chunk in enumerate(inline_chunks or [])}
        bootstrap = (
            "<script>window.TELE_RELAY_MANIFEST="
            + _script_json(inline_manifest)
            + ";window.TELE_RELAY_INLINE_CHUNKS="
            + _script_json(inline)
            + ";</script>"
        )
    return f"""<!doctype html>
<html lang="{language}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>{_VIEWER_STYLE}</style>
</head>
<body class="theme-{theme}">
<div class="shell">
  <header class="archive-header">
    <div><h1 id="title">{title}</h1><p class="meta" id="meta"></p></div>
    <p class="summary" id="summary"></p>
  </header>
  <section class="filters" aria-label="Filters">
    <label class="field search-field"><span id="search-label"></span><input id="search" type="search"></label>
    <label class="field"><span id="date-from-label"></span><input id="date-from" type="date"></label>
    <label class="field"><span id="date-to-label"></span><input id="date-to" type="date"></label>
    <button class="command primary" id="apply-filters" type="button"></button>
    <button class="command" id="reset-filters" type="button"></button>
  </section>
  <div class="scan" id="scan"><progress id="scan-progress"></progress><span id="scan-label"></span></div>
  <section class="thread-bar" id="thread-bar">
    <div><span class="thread-title" id="thread-title"></span><span class="thread-summary" id="thread-summary"></span></div>
    <button class="command" id="close-thread" type="button"></button>
  </section>
  <nav class="toolbar" aria-label="Pagination">
    <p class="status" id="status"></p>
    <div class="pager">
      <label class="field"><span id="page-size-label"></span><select id="page-size"></select></label>
      <button class="icon-button" id="previous-page" type="button">&#8249;</button>
      <span class="page-status" id="page-status"></span>
      <button class="icon-button" id="next-page" type="button">&#8250;</button>
    </div>
  </nav>
  <main id="messages" aria-live="polite"></main>
  <nav class="toolbar bottom-toolbar" aria-label="Pagination">
    <p class="status" id="status-bottom"></p>
    <div class="pager">
      <button class="icon-button" id="previous-page-bottom" type="button">&#8249;</button>
      <span class="page-status" id="page-status-bottom"></span>
      <button class="icon-button" id="next-page-bottom" type="button">&#8250;</button>
    </div>
  </nav>
</div>
<script src="https://unpkg.com/linkifyjs@4.3.3/dist/linkify.min.js"></script>
{bootstrap}
<script>{_VIEWER_SCRIPT}</script>
</body>
</html>
"""
