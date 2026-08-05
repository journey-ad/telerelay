# CLAUDE.md

This file provides repository guidance for coding agents.

## Current Project

TeleRelay is a self-hosted Telegram relay, chat preview and text messaging, automation, and archive service.

- Backend: Python 3.11+, FastAPI, Telethon, APScheduler, and SQLite.
- Frontend: React 19, React Router 7, TanStack Query 5, Recharts, Tailwind CSS 4, i18next, and Vite 7.
- Deployment: one repository, one container, one process, and one Uvicorn worker.
- Transport: REST for commands and CRUD, SSE for one-way runtime events.

The old Gradio and Vue implementations are gone. Do not add compatibility code for them or refer to `src/webui`, Vue Router, Pinia, vue-i18n, or ECharts.

## Setup and Commands

Run Python commands from the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env

python -m backend.main
```

Install and build the frontend:

```bash
corepack enable
cd frontend
pnpm install --frozen-lockfile
pnpm run build
```

For frontend development, run the API and Vite in separate terminals:

```bash
python -m backend.main
```

```bash
cd frontend
pnpm run dev
```

Vite serves port 5173 and proxies `/api` to `http://127.0.0.1:8080`.

Use these checks before handing off changes:

```bash
PYTHONPYCACHEPREFIX=/tmp/telerelay-pyc .venv/bin/python -m compileall -q backend tests
.venv/bin/python -m unittest discover -s tests -v

cd frontend
pnpm run typecheck
pnpm run format:check
pnpm run build

git diff --check
```

The backend suite uses `unittest`, not pytest. Run focused modules while developing, then full discovery for shared behavior.

## Repository Map

```text
backend/
  main.py                 FastAPI app, lifespan, static frontend hosting
  application.py          Lifespan-owned dependency container
  api/
    dependencies.py       Application context and HTTP Basic Auth
    router.py             Versioned REST and SSE transport
  schemas/__init__.py     Strict Pydantic request contracts
  bot_manager.py          Telethon runtime and update handlers
  client.py               Telegram client/session management
  telegram_accounts.py    Account registry, sessions, avatars, selection
  telegram_runtimes.py    Parallel per-account runtime registry
  telegram_preview.py     Dialog/message/media reads and plain-text sending
  services/rules.py       Forwarding and button-rule application service
  forwarder/              Filtering and Telegram delivery pipeline
  forward_queue.py        Persistent queue, retries, and recovery
  exporter/               Export source, archives, workers, and scheduler
  stats_db.py             Statistics and forwarded-message history
  events.py               In-process SSE event bus
  config.py               Environment and atomic YAML configuration

frontend/src/
  main.tsx                React entry point
  App.tsx                 Session gate, router, lazy pages, query client
  api/                    Authenticated fetch, downloads, and SSE client
  components/AppShell.tsx Navigation, account, status, and language shell
  components/ui/          Shared controls, panels, dialogs, and fields
  pages/                  Eight route-level feature pages
  locales/                zh-CN and en-US resources
  i18n.ts                 Locale initialization and persistence
  i18next.d.ts            Typed translation resources
  global.css              Tailwind entry and shared styling

tests/                     Backend unit and API contract tests
```

## Non-Negotiable Invariants

### One Worker

Uvicorn must run with `workers=1`. The runtime registry, scheduler, event bus, and in-memory export job registry are process singletons. Multiple workers would duplicate every account client and other runtime side effects.

### Parallel Telegram Accounts

User mode runs every authenticated account concurrently on the FastAPI event loop. Each account owns an isolated `BotManager`, `AuthManager`, Telegram client, handler set, deduplication state, configuration, statistics database, export services, and persistent forwarding queue. An account connection or authentication failure must not stop other accounts.

The selected account is only the control-console context for Telegram preview and manual exports. Selecting another account must not stop or restart any runtime. Global start, stop, restart, and rule changes apply to all eligible account runtimes.

Authenticated account IDs are Telegram numeric user IDs. Account configuration is stored at `config/<telegram_user_id>.yaml`; sessions, queues, statistics, export state, archives, and avatars are stored below `data/<telegram_user_id>/`. Pending accounts exist only in `data/telegram_accounts.json` and must not create account-scoped directories before authentication succeeds.

The `default` ID and the former shared paths are legacy migration inputs only. Migration must be idempotent and must never overwrite an existing account-scoped destination.

### Preview Mutation Boundary

Telegram preview may send only new plain-text messages through its explicit compose endpoint. It must not send media, create replies, forward, edit, delete, react, vote, or acknowledge messages as read. Plain-text sends must disable formatting parsing and link previews. Reads must use Telegram APIs that do not issue read confirmations.

Remote bot command discovery is read-only and depends on the selected dialog being a bot, not on the current account's session mode. Live preview update handlers must exist only for an active preview SSE connection and must be removed when the browser disconnects or navigates away.

The persistent preview cache contains only avatars and thumbnails and is bounded to 128 MB. Full images, GIFs, and stickers use temporary files and must be cleaned after the response. Do not enable video, audio, voice, or arbitrary document downloads through this feature.

Do not send MTProto `auth_key`, file references, or session material to the browser.

### Credential Boundaries

- `.env` owns Telegram credentials, Bot Tokens, Web auth, and process settings.
- `config/<telegram_user_id>.yaml` owns that account's mutable rules, queue settings, and export settings. It is generated after authentication and managed through the console.
- The entire `config/` directory is runtime data and must remain ignored by Git and Docker build contexts.
- Configuration import/export must never include `.env` secrets.
- HTTP Basic Auth applies to the versioned router when both Web credentials are configured.
- `/api/v1/health` is intentionally outside the authenticated router.

Telegram sessions, databases, exports, cache keys, and backups are sensitive even when the account registry itself contains only public metadata.

### Async and Thread Boundaries

`TelegramRuntimeRegistry` coordinates account lifecycle on the FastAPI lifespan loop. Each `BotManager.start`, `stop`, and `restart` is async, and each account `AuthManager` uses its own `asyncio.Future` challenges for phone, code, and password.

Export workers may perform file and SQLite work in threads. Telegram calls from those workers must be submitted back to the main runtime loop. The optional Admin Bot retains its own thread and submits control work to the FastAPI loop.

Do not introduce blocking Telegram or filesystem work directly into the event loop.

## Backend Change Guidance

- Keep route functions focused on HTTP parsing, authorization, status codes, and response shaping.
- Put reusable behavior in the existing service or domain module.
- Define request bodies in `backend/schemas/__init__.py`; models use `extra="forbid"`.
- Preserve structured API errors through `detail.code` and `detail.message`.
- Use `asyncio.to_thread` for existing synchronous SQLite and filesystem operations called by API handlers.
- Publish relevant state changes through `EventBus` so open consoles update.
- Use the logger from `backend.logger`; do not configure ad hoc root handlers.
- Preserve atomic YAML/JSON writes and locks around mutable configuration or account state.
- Continue using structured parsers for YAML, JSON, URLs, and Telegram entities.

Exports are User-mode-only. Check `ExportService.availability()` instead of duplicating mode or connection checks.

## Frontend Change Guidance

- Use `request()` and `json()` from `frontend/src/api/client.ts` for JSON APIs.
- Use authenticated fetch/blob helpers for downloads and protected images. A plain `<a href>` or `<img src>` cannot attach credentials stored in `sessionStorage`.
- Keep server state in TanStack Query. Invalidate existing query keys after mutations instead of creating parallel caches.
- Clear Telegram preview queries when the selected account changes.
- Reuse `components/ui` controls and the existing `cn()` utility.
- Add routes and lazy page imports in `App.tsx`; navigation lives in `AppShell.tsx`.
- Keep stable avatar colors through `frontend/src/utils/color.ts`; foreground and background must remain a contrast-tested pair.
- Do not edit generated `frontend/dist`; rebuild it from source.

All user-visible text must use i18next keys. Add keys to the nested `zh-CN` resource first, mirror the exact structure in `en-US`, and rely on `i18next.d.ts` for key and interpolation typing. Dates and numbers must use the active locale.

TypeScript is pinned to 5.9.3. Upgrade it only after verifying the complete typecheck and Vite build.

## Persistence and Compatibility

Important paths:

```text
.env
config/<telegram_user_id>.yaml
data/telegram_accounts.json
data/<telegram_user_id>/telegram.session
data/<telegram_user_id>/forward_queue.db
data/<telegram_user_id>/stats.db
data/<telegram_user_id>/exports.db
data/<telegram_user_id>/db/msg_export_{chat_id}.sqlite3
data/<telegram_user_id>/exports/
data/<telegram_user_id>/avatar.jpg
data/telegram_preview_cache/
data/.telegram_preview_cache.key
logs/telerelay.log
```

Schema or path changes must preserve existing deployments or include an explicit migration. Keep queue recovery and deduplication semantics across restarts. Do not replace persistent stores with process memory.

## Common Change Locations

- Telegram lifecycle or handlers: `backend/bot_manager.py`, `backend/client.py`
- Filtering and relay behavior: `backend/filters.py`, `backend/forwarder/`
- Queue retries and recovery: `backend/forward_queue.py`
- Rule CRUD and validation: `backend/services/rules.py`
- API contracts and routes: `backend/schemas/__init__.py`, `backend/api/router.py`
- Multi-account metadata: `backend/telegram_accounts.py`
- Multi-account lifecycle: `backend/telegram_runtimes.py`
- Dialog/message preview and plain-text sending: `backend/telegram_preview.py`
- Export behavior and schedules: `backend/exporter/`
- Dashboard/history statistics: `backend/stats_db.py`
- Frontend routes and pages: `frontend/src/App.tsx`, `frontend/src/pages/`
- Shared UI and styling: `frontend/src/components/ui/`, `frontend/src/global.css`
- Translation resources: `frontend/src/locales/`, `frontend/src/i18next.d.ts`

## Test Expectations

Scale validation with the behavior changed:

- Backend logic: add or update a focused `unittest` module.
- API changes: cover auth, response shape, error code, and status code.
- Account/session changes: test default-session compatibility and physical session-file behavior.
- Preview changes: test no-read semantics, account isolation, cache boundaries, and media cleanup.
- Queue changes: test retry, FloodWait, restart recovery, and duplicate prevention.
- Frontend changes: run typecheck, format check, and production build; verify both locale resources when visible text changes.
- User-facing layout changes: verify desktop and mobile rendering with a browser screenshot.

Do not report browser verification as complete unless the current build was actually loaded and visually inspected.
