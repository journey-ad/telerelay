# Telegram Message Forwarder

A powerful Telegram message auto-forwarding tool with intelligent filtering based on regex patterns and keywords, featuring a modern Web management interface.

## ✨ Features

- 🤖 **Smart Forwarding**: Automatically monitor specified Telegram groups/channels and forward messages to multiple targets
- 📋 **Multi-Rule Management**: Support multiple independent forwarding rules, each with its own sources, targets, and filters
- 🔍 **Powerful Filtering**: Support regex and keyword matching, whitelist/blacklist modes, media type and file size filtering
- 🚫 **Ignore List**: Ignore specific messages by user ID and keywords
- 💪 **Force Forward**: Bypass noforwards restrictions on channels/groups by downloading and re-uploading
- 📸 **Media Group Support**: Full support for media group (album) forwarding with automatic deduplication and smart filtering
- 🌐 **Web Management Interface**: Intuitive configuration management and real-time log viewing based on Gradio
- 🌍 **Internationalization**: Full i18n support with built-in Chinese and English interfaces, switchable in Web UI
- 🔐 **Dual Authentication Modes**: Support both User Session (phone login) and Bot Token methods
- 📊 **Real-time Monitoring**: Display Bot status, statistics, and logs in real-time
- 🐳 **Docker Support**: One-click deployment, ready to use
- 🔒 **Secure**: Support HTTP Basic Auth for Web interface
- ⚡ **Performance Optimized**: Asynchronous processing with rate limiting and error retry
- 🔌 **Proxy Support**: Support SOCKS5/HTTP proxy configuration

## 🚀 Quick Start

### Prerequisites

1. **Telegram API Credentials**
   - Visit [https://my.telegram.org](https://my.telegram.org)
   - Create an app to get `API_ID` and `API_HASH`

2. **Bot Token** (if using Bot mode)
   - Chat with [@BotFather](https://t.me/BotFather) to create a Bot
   - Get the Bot Token

### Method 1: Docker Deployment (Recommended)

1. **Clone the project**
   ```bash
   cd tg-box
   ```

2. **Configure environment variables**
   ```bash
   # Copy example configuration
   cp .env.example .env
   # Edit the config file, fill in your API_ID and API_HASH
   nano .env
   ```

3. **Configure forwarding rules**
   ```bash
   cp config/config.yaml.example config/config.yaml
   # Edit config.yaml to configure source and target groups
   nano config/config.yaml
   ```

4. **Start the container**
   ```bash
   docker-compose up -d
   ```

5. **Access Web interface**
   - Open browser and visit: `http://localhost:8080`
   - If HTTP Basic Auth is configured, enter username and password

### Method 2: Local Run

1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configuration files** (same as Docker deployment steps 2-3)

3. **Run the program**
   ```bash
   python -m src.main
   ```

4. **Access Web interface**: `http://localhost:8080`

## 📖 Configuration

### Environment Variables (.env)

```env
# Telegram API credentials (required)
API_ID=your_api_id
API_HASH=your_api_hash

# Bot Token (required for Bot mode)
BOT_TOKEN=your_bot_token

# Session type: user or bot
# user: Use user account (can monitor all groups)
# bot: Use Bot Token (can only monitor groups the bot has joined)
SESSION_TYPE=user

# Proxy configuration (optional)
# Supported protocols: socks5, http
# Example: socks5://127.0.0.1:1080 or http://127.0.0.1:1080
PROXY_URL=

# Web service configuration
WEB_HOST=0.0.0.0
WEB_PORT=8080

# Web interface authentication (recommended for production)
WEB_AUTH_USERNAME=
WEB_AUTH_PASSWORD=

# Log level: DEBUG, INFO, WARNING, ERROR
LOG_LEVEL=INFO

# Interface language: zh_CN (Chinese) or en_US (English)
LANGUAGE=zh_CN
```

### Configuration File (config/config.yaml)

Two configuration methods are supported:

#### Method 1: Single Rule Configuration (Simple Scenarios)

```yaml
# Source groups/channels list (to monitor)
source_chats:
  - -100123456789  # Group ID
  - "@channel_name"  # Channel username

# Target groups/channels list (forward to, supports multiple targets)
target_chats:
  - -100987654321  # Target group 1
  - "@target_channel"  # Target channel 2

# Filter rules
filters:
  # Regex patterns (any match passes)
  regex_patterns:
    - "\\[Important\\].*"
    - "Urgent notification.*"

  # Keywords (any match passes)
  keywords:
    - "keyword1"
    - "keyword2"

  # Filter mode: whitelist or blacklist
  mode: whitelist

  # Media type filtering (optional)
  media_types:
    - text      # Text messages
    - photo     # Photos
    - video     # Videos
    - document  # Documents
    - audio     # Audio
    - voice     # Voice messages
    - sticker   # Stickers
    - animation # Animations/GIFs

  # File size limits (optional, in bytes)
  max_file_size: 52428800  # 50MB
  min_file_size: 0

# Forwarding options
forwarding:
  preserve_format: true  # Preserve original format
  add_source_info: true  # Add source information
  delay: 0.5  # Forwarding delay (seconds)
  force_forward: false  # Force forward (bypass noforwards restrictions)

# Ignore list (higher priority than filter rules)
ignore:
  # Ignored user ID list
  user_ids:
    # - 123456789

  # Ignored keywords list (case insensitive)
  keywords:
    # - "spam"
```

#### Method 2: Multi-Rule Configuration (Complex Scenarios)

```yaml
# Multi-rule configuration, each rule runs independently
rules:
  - name: "Rule 1"
    enabled: true
    source_chats:
      - -100123456789
    target_chats:
      - -100987654321
    filters:
      regex_patterns:
        - "\\[Important\\].*"
      mode: whitelist
    forwarding:
      preserve_format: true
      add_source_info: true
      delay: 0.5
      force_forward: false
    ignore:
      user_ids: []
      keywords: []

  - name: "Rule 2"
    enabled: true
    source_chats:
      - "@source_channel"
    target_chats:
      - "@target_channel"
    filters:
      keywords:
        - "keyword"
      mode: whitelist
      media_types:
        - photo
        - video
    forwarding:
      preserve_format: false
      add_source_info: false
      delay: 1.0
      force_forward: true
    ignore:
      user_ids: []
      keywords: []
```

## 🎮 Usage Guide

### Authentication Mode Comparison

| Feature | User Mode | Bot Mode |
|---------|-----------|----------|
| Authentication | Phone + Code | Bot Token |
| Monitoring Scope | All joined groups | Only groups bot joined |
| Web Interface | Has auth tab | No auth tab |
| First Use | Requires phone verification | No verification |
| Session Persistence | sessions/ directory | sessions/ directory |

### User Mode Authentication Flow

1. Set `SESSION_TYPE=user`
2. Start the app and access Web interface
3. Click "Start Authentication" in the "🔐 Authentication" tab
4. Enter phone number (international format, e.g., `+8613800138000`)
5. Enter the verification code sent by Telegram
6. If two-step verification is enabled, enter password
7. After successful authentication, current account information is displayed

### Getting Group ID

1. **Using @userinfobot**
   - Add [@userinfobot](https://t.me/userinfobot) to the group
   - Send any message in the group, bot will reply with group ID

2. **From messages**
   - Forward a group message to [@userinfobot](https://t.me/userinfobot)
   - Get the group ID from the message source

### Web Interface Features

#### Control Panel
- **Start/Stop/Restart**: Control Bot running status
- **Refresh Status**: Manually refresh current status
- **Status Display**: Running status, forwarded, filtered, total messages
- **Language Switcher**: Switch between Chinese and English interfaces

#### Configuration Tab
- **Rule Management**: View, add, edit, delete, enable/disable forwarding rules
- **Source Groups**: Configure groups to monitor
- **Target Groups**: Configure forwarding targets (supports multiple)
- **Filter Rules**: Regex, keyword matching, media type and file size filtering
- **Ignore List**: User ID and keyword blocking
- **Forwarding Options**: Format preservation, source info, delay settings, force forward

#### Logs Tab
- **Real-time Logs**: View running logs
- **Log Lines**: Adjustable display lines

#### Authentication Tab (User Mode Only)
- **Auth Status**: Display current login status and account info
- **Auth Operations**: Start authentication, cancel authentication
- **Input Forms**: Phone number, verification code, password

## 🔧 FAQ

### 1. User Mode Authentication

**How to authenticate in Docker for the first time?**
- Method 1: Run locally first to complete login, then mount `sessions/` directory to container
- Method 2: After Docker container starts, complete authentication through Web interface auth tab

**What if session expires?**
- Click "Cancel Authentication" in Web interface auth tab to clear old session
- Click "Start Authentication" again to complete new login

### 2. Bot Mode Configuration

**Why can't I see the authentication tab?**
- Bot mode doesn't require phone verification, auth tab is automatically hidden
- Confirm `SESSION_TYPE=bot` and `BOT_TOKEN` are configured in `.env`

### 3. Message Forwarding Issues

**Messages not forwarding?**
Check:
- Is Bot running (check Web interface status)
- Are filter rules correct (check logs)
- Does Bot have permission to send messages
- If using multi-rule configuration, check if rules are enabled

**Triggered rate limit (FloodWait)?**
- Program will automatically handle and wait
- Can increase `forwarding.delay` time

**Can't forward restricted channel content?**
- Enable `forwarding.force_forward: true` for force forward
- Note: Force forward downloads then re-uploads, may be slower

### 4. Proxy Configuration

**How to configure proxy?**
```env
# SOCKS5 proxy
PROXY_URL=socks5://127.0.0.1:1080

# HTTP proxy
PROXY_URL=http://127.0.0.1:1080

# Proxy with authentication
PROXY_URL=socks5://user:password@127.0.0.1:1080
```

## 📦 Project Structure

```
tg-box/
├── .env.example          # Environment variables example
├── config/               # Configuration directory
│   └── config.yaml.example
├── logs/                 # Log files
├── sessions/             # Telegram session files
├── src/                  # Source code
│   ├── i18n/             # Internationalization module
│   │   ├── locales/      # Language packs
│   │   │   ├── zh_CN.py  # Chinese translation
│   │   │   └── en_US.py  # English translation
│   │   └── translator.py # Translator
│   ├── forwarder/        # Forwarding module
│   │   ├── forwarder.py  # Message forwarding logic
│   │   ├── downloader.py # Media downloader
│   │   └── media_group.py # Media group handling
│   ├── webui/            # Gradio Web interface
│   │   ├── handlers/     # Business handlers
│   │   │   ├── auth.py         # Authentication handling
│   │   │   ├── bot_control.py  # Bot control
│   │   │   ├── config.py       # Configuration management
│   │   │   └── log.py          # Log viewing
│   │   ├── app.py        # UI construction
│   │   └── utils.py      # Utility functions
│   ├── main.py           # Main program entry
│   ├── config.py         # Configuration management
│   ├── rule.py           # Forwarding rule data class
│   ├── client.py         # Telegram client
│   ├── auth_manager.py   # User mode auth management
│   ├── bot_manager.py    # Bot lifecycle management
│   ├── filters.py        # Message filtering
│   ├── constants.py      # Constants definition
│   ├── utils.py          # Utility functions
│   └── logger.py         # Logging configuration
├── Dockerfile            # Docker image
├── docker-compose.yml    # Docker Compose configuration
└── requirements.txt      # Python dependencies
```

## 🛡️ Security Recommendations

1. **Protect Sensitive Information**
   - Don't commit `.env` file to Git
   - Regularly change API credentials
   - Keep session files secure

2. **Web Interface Security**
   - Must configure `WEB_AUTH_USERNAME` and `WEB_AUTH_PASSWORD` in production
   - Use reverse proxy (like Nginx) to add HTTPS

3. **Restrict Access**
   - Configure firewall in production environment
   - Restrict Web interface access IPs

4. **Regular Backups**
   - Backup session files (`sessions/`)
   - Backup configuration files

## 📝 License

MIT License

## 🤝 Contributing

Issues and Pull Requests are welcome!

## 📧 Contact

For questions, please submit an Issue.
