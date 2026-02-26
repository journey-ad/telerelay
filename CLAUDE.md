# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Telegram message auto-forwarding tool that supports intelligent filtering based on regex patterns and keywords, with a Gradio Web management interface.

**Core Features**:
- Monitor messages from specified Telegram groups/channels
- Filter messages based on configured rules (regex, keywords, whitelist/blacklist)
- Forward matching messages to target groups/channels
- Provide Web UI for real-time monitoring and configuration management

## Development Environment Setup

### Install Dependencies
```bash
pip install -r requirements.txt
```

### Run the Program
```bash
# Run locally
python -m src.main

# Run with Docker
docker-compose up -d
```

### Configuration Files
- `.env`: Environment variables (API_ID, API_HASH, BOT_TOKEN, etc.)
- `config/config.yaml`: Forwarding rules (source groups, target groups, filter rules, etc.)
- Example files are located in `config/*.example`

## Architecture Design

### Core Module Relationships

```
main.py (entry point)
  ├─> config.py (configuration management)
  ├─> bot_manager.py (Bot lifecycle management)
  │     ├─> client.py (Telegram client wrapper)
  │     ├─> filters.py (message filtering logic)
  │     └─> forwarder.py (message forwarding logic)
  └─> webui/ (Gradio Web interface)
        ├─> app.py (UI construction)
        └─> handlers/ (business handlers)
              ├─> bot_control.py (Bot control)
              ├─> config.py (configuration management)
              └─> log.py (log viewing)
```

### Key Design Patterns

1. **Threading Model**:
   - Main thread runs Gradio Web server
   - Bot runs in a separate thread with its own asyncio event loop
   - Uses `threading.RLock()` to ensure thread-safe state access

2. **Configuration Management**:
   - `Config` class manages both environment variables (.env) and YAML configuration
   - Supports runtime dynamic configuration updates and persistence
   - Configuration updates can trigger Bot restart

3. **Message Processing Flow**:
   ```
   Telegram message -> client.py (receive)
                    -> filters.py (filter)
                    -> forwarder.py (forward)
   ```

4. **UI Update Mechanism**:
   - Uses debounce mechanism (max once per second) to avoid frequent refreshes
   - `bot_manager.trigger_ui_update()` sets update flag
   - Gradio Timer periodically checks flag and updates UI

### Important Classes

- **BotManager** (`bot_manager.py`): Manages Bot startup, shutdown, restart, and coordinates components
- **TelegramClientManager** (`client.py`): Wraps Telethon client, handles connection and message listening
- **MessageFilter** (`filters.py`): Implements message filtering logic (regex, keywords, whitelist/blacklist, ignore list)
- **MessageForwarder** (`forwarder.py`): Handles message forwarding, including rate limiting and error retry
- **Config** (`config.py`): Configuration loading, validation, and persistence

## Common Development Tasks

### Modify Filtering Logic
Edit the `MessageFilter.should_forward()` method in `src/filters.py`.

### Add New Configuration Items
1. Add example configuration in `config/config.yaml.example`
2. Add corresponding `@property` in the `Config` class in `src/config.py`
3. Access via `config.xxx` in modules that need it

### Modify Web UI
- UI layout: `src/webui/app.py`
- Business logic: handlers in `src/webui/handlers/`

### Debugging Tips
- Log files are located in the `logs/` directory
- Set `LOG_LEVEL=DEBUG` in `.env` for detailed logs
- Use `python -m src.main` to run locally for easier debugging

## Important Notes

### Telegram Client
- Supports two modes: User Session (user account) and Bot Token (bot)
- User mode requires phone verification on first run, session files saved in `data/` directory
- Bot mode requires no verification, but can only monitor groups the bot has joined

### Thread Safety
- `BotManager`'s `is_running` and `is_connected` are protected with `@property` and locks
- Must use `with self._lock:` when accessing shared state

### Configuration Updates
- Bot must be restarted for configuration changes to take effect
- `save_config()` in `config_handler.py` automatically triggers restart

### Rate Limiting
- Telegram has strict rate limits (FloodWait)
- Automatic wait and retry mechanism implemented in `forwarder.py`
- Forwarding delay can be configured via `forwarding.delay`

## Project Conventions

- All comments and documentation use English
- Use Python 3.11+
- Async code uses `async/await` syntax
- Logging uses unified `logger` instance (obtained via `get_logger()`)
