# CLAUDE.md

This file provides repository guidance for coding agents.

## Project Overview

TeleRelay is a personal Telegram forwarding and archive tool. The production application is a FastAPI backend with a Vue 3 + TypeScript frontend. Gradio has been removed and no compatibility layer is expected.

## Commands

```bash
# Python dependencies
pip install -r requirements.txt

# Frontend dependencies and production build
cd frontend && pnpm install --frozen-lockfile && pnpm run build

# Run the combined production app from the repository root
python -m backend.main

# Backend tests
.venv/bin/python -m unittest discover -s tests -v

# Backend syntax check
PYTHONPYCACHEPREFIX=/tmp/telerelay-pyc .venv/bin/python -m compileall -q backend tests
```

For frontend development, run `pnpm run dev` in `frontend/`; Vite proxies `/api` to the FastAPI server on port 8080.

## Architecture

```text
backend/main.py
  -> FastAPI lifespan and static frontend hosting
  -> backend/api/         REST and SSE transport
  -> backend/services/    UI-independent application operations
  -> BotManager           Telegram runtime on the FastAPI asyncio loop
     -> client.py
     -> filters.py
     -> forwarder/
     -> forward_queue.py
  -> exporter/            worker-backed exports and AsyncIOScheduler

frontend/src/
  -> Vue Router, Pinia, TanStack Query, vue-i18n, ECharts
```

The deployment model is one repository, one container, one process, and one Uvicorn worker. Do not configure multiple workers: the Telegram client, scheduler, and in-memory export job registry must be singletons.

REST is used for commands and CRUD. SSE is used for one-way logs and runtime status updates. HTTP Basic Auth protects the versioned API when credentials are configured.

## Configuration and Persistence

- `.env` owns credentials and process/runtime settings.
- `config/config.yaml` owns mutable forwarding, button, queue, and export configuration.
- `Config` uses an `RLock` and atomic YAML replacement.
- SQLite files under `data/` store forwarding state, statistics, export tasks, and message archives.

Do not put Telegram or Web credentials into YAML responses or backups.

## Runtime Notes

- `BotManager.start`, `stop`, and `restart` are async and run on the FastAPI loop.
- `AuthManager` resolves phone/code/password challenges with `asyncio.Future`.
- Export workers may do blocking file and SQLite work in threads; Telegram calls are submitted back to the main loop.
- The optional Admin Bot retains its own thread and submits runtime control commands to the FastAPI loop.

## Common Changes

- Filtering behavior: `backend/filters.py`
- Configuration properties: `backend/config.py` and `config/config.yaml.example`
- HTTP contracts: `backend/schemas/__init__.py` and `backend/api/router.py`
- Rule behavior: `backend/services/rules.py`
- Frontend routes/pages: `frontend/src/router.ts` and `frontend/src/pages/`
- Shared frontend styling: `frontend/src/styles.css`

Keep application behavior out of Vue components and API route functions when it belongs in a service. Reuse the existing stores and forwarding/export modules instead of duplicating persistence logic.

## Conventions

- Python 3.11+ and async/await for runtime I/O.
- TypeScript 5.9 is intentionally pinned; do not upgrade to TypeScript 7 without checking vue-tsc compatibility.
- Use the configured logger from `backend.logger`.
- Preserve the single-worker deployment invariant.
