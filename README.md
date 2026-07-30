[中文文档](README_zh.md)

# TeleRelay

TeleRelay is a self-hosted Telegram relay and archive tool. It uses a FastAPI backend and a Vue 3 control console, with persistent forwarding queues, rule-based filtering, callback-button automation, and message exports.

## Features

- Multiple independent forwarding rules with source, target, filter, ignore, and forwarding options
- Persistent SQLite forwarding queue with retry, FloodWait handling, and restart recovery
- User session and Bot Token modes
- Exact, contains, and regex matching for Telegram callback-button automation in User mode
- JSON, CSV, SQLite, and offline HTML message exports
- Hourly, daily, and weekly incremental export tasks
- Live runtime status and logs over Server-Sent Events
- HTTP Basic authentication for the management API and console
- Optional Telegram Admin Bot controls

## Architecture

TeleRelay is intentionally deployed as one service:

- `backend/`: FastAPI, Telethon runtime, application services, SQLite stores, and REST/SSE API
- `frontend/`: Vue 3, TypeScript, Vite, Pinia, TanStack Query, and ECharts
- FastAPI serves the production frontend from `frontend/dist`
- Uvicorn runs with one worker so the Telegram client, scheduler, and in-memory jobs are created once

REST endpoints are under `/api/v1`, OpenAPI documentation is available at `/api/docs`, and `/api/v1/events` provides the SSE stream.

## Quick Start

### Configuration

Create local configuration files from the examples:

```bash
cp .env.example .env
cp config/config.yaml.example config/config.yaml
```

At minimum, set `API_ID` and `API_HASH` in `.env`. Set `BOT_TOKEN` when using `SESSION_TYPE=bot`. For a remotely accessible console, also set `WEB_AUTH_USERNAME` and `WEB_AUTH_PASSWORD`.

Telegram API credentials are available from [my.telegram.org](https://my.telegram.org). Bot tokens are created with [@BotFather](https://t.me/BotFather).

### Docker Compose

```bash
docker compose up -d --build
```

Open `http://localhost:8080`. Compose persists configuration, Telegram sessions, databases, exports, and logs through the `config/`, `data/`, and `logs/` mounts.

To use the published image instead of a local build, remove `build: .` from `docker-compose.yml` and keep `image: ghcr.io/journey-ad/telerelay:latest`.

### Local Production Build

Requirements: Python 3.11+ and Node.js 22+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd frontend
npm ci
npm run build
cd ..
python -m backend.main
```

Open `http://localhost:8080`.

### Frontend Development

Run the API and Vite server in separate terminals:

```bash
python -m backend.main
```

```bash
cd frontend
npm ci
npm run dev
```

Vite serves the console at `http://localhost:5173` and proxies `/api` to `http://127.0.0.1:8080`.

## Configuration Ownership

`.env` contains process credentials and runtime settings:

- Telegram credentials and `SESSION_TYPE`
- proxy, host, port, log level, and runtime language
- Web Basic Auth credentials
- optional Admin Bot and Mini App settings

`config/config.yaml` contains mutable application configuration:

- forwarding and callback-button rules
- filtering, ignore, and forwarding options
- forwarding queue settings
- export directories, timezone, and concurrency

The console can import or export the YAML configuration. Credentials remain in `.env` and are not included in these backups.

## Persistent Data

- `data/telegram_session.session`: Telegram user session
- `data/forward_queue.db`: pending forwarding work and deduplication tombstones
- `data/stats.db`: forwarding statistics and history
- `data/exports.db`: export tasks and run history
- `data/db/msg_export_{chat_id}.sqlite3`: canonical message archives
- `data/exports/`: generated JSON, CSV, SQLite, and HTML files
- `logs/telerelay.log`: rotating application log

Back up `config/`, `data/`, and `.env` together. Treat `.env` and Telegram session files as secrets.

## User Authentication Flow

With `SESSION_TYPE=user`, open Settings and start Telegram authentication. Submit the phone number, login code, and 2FA password when requested. The async challenge is managed by the API; no terminal input is required.

With `SESSION_TYPE=bot`, configure `BOT_TOKEN`. Callback-button automation and account-wide export discovery are unavailable because they require a user session.

## Admin Bot

Set `ADMIN_BOT_TOKEN` and `ADMIN_CHAT_ID` to enable remote commands:

- `/status`
- `/bot start|stop|restart`
- `/rule list|detail|add|del|rename|toggle|set`
- `/webapp`

The Admin Bot uses a separate Telegram token. Its control commands are submitted to the FastAPI runtime loop.

## Development Checks

```bash
PYTHONPYCACHEPREFIX=/tmp/telerelay-pyc .venv/bin/python -m compileall -q backend tests
.venv/bin/python -m unittest discover -s tests -v
cd frontend && npm run build
```

## Project Structure

```text
telerelay/
├── backend/              # FastAPI API and Telegram runtime
│   ├── api/              # REST and SSE routes
│   ├── exporter/         # Export engine and scheduler
│   ├── forwarder/        # Message forwarding pipeline
│   ├── schemas/          # HTTP request contracts
│   ├── services/         # UI-independent application services
│   └── main.py           # FastAPI/Uvicorn entry point
├── frontend/             # Vue 3 + TypeScript console
│   └── src/
├── config/               # Mutable YAML configuration
├── data/                 # Sessions, SQLite databases, and exports
├── logs/                 # Rotating logs
├── tests/
├── Dockerfile
└── docker-compose.yml
```

## Security

- Enable Web Basic Auth whenever port 8080 is reachable by other machines.
- Terminate HTTPS at a reverse proxy; Basic Auth credentials must not travel over plain public HTTP.
- Restrict access to `.env`, `data/*.session`, databases, exports, and backups.
- Keep Uvicorn at one worker. Multiple workers would start duplicate Telegram clients and schedulers.

## License

[MIT License](LICENSE)
