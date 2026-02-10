[中文文档](README_zh.md)

# TeleRelay

An intelligent Telegram message relay tool with smart filtering based on regex patterns and keywords, featuring a modern Web management interface.

<p align="center">
  <img src="https://count.getloli.com/@telerelay.github?theme=minecraft&padding=7&offset=0&align=top&scale=1&pixelated=1&darkmode=auto" width="400">
</p>

## Preview

<p align="center">
  <img src="./docs/preview_en.jpeg" width="600">
</p>

## ✨ Features

- 🤖 **Smart Forwarding**: Automatically monitor specified Telegram groups/channels/accounts and forward messages to multiple targets
- 📋 **Multi-Rule Management**: Support multiple independent forwarding rules, each with its own sources, targets, and filters
- 🔍 **Powerful Filtering**: Support regex and keyword matching, whitelist/blacklist modes, media type and file size filtering
- 🚫 **Ignore List**: Ignore specific messages by user ID and keywords
- 💪 **Force Forward**: Bypass noforwards restrictions on channels/groups by downloading and re-uploading
- 🌐 **Web Management Interface**: Gradio-based configuration panel with real-time Bot status, statistics, and logs
- 🌍 **Internationalization**: Full i18n support with built-in Chinese and English interfaces
- 🔐 **Dual Authentication Modes**: Support both User Session (phone login) and Bot Token methods
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

Pull the pre-built image from GitHub Container Registry:

```bash
docker pull ghcr.io/journey-ad/telerelay:latest
```

Run with Docker:

```bash
docker run -d -p 8080:8080 \
  -v $(pwd)/.env:/app/.env \
  -v $(pwd)/config:/app/config \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/sessions:/app/sessions \
  ghcr.io/journey-ad/telerelay:latest
```

Or use docker-compose:

```yaml
version: '3'
services:
  telerelay:
    image: ghcr.io/journey-ad/telerelay:latest
    ports:
      - "8080:8080"
    volumes:
      - ./.env:/app/.env
      - ./config:/app/config
      - ./logs:/app/logs
      - ./sessions:/app/sessions
```

Access Web interface:
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

## 🎮 Usage Guide

### Authentication Mode Comparison

| Feature | User Mode | Bot Mode |
|---------|-----------|----------|
| Authentication | Phone + Code | Bot Token |
| Monitoring Scope | All joined groups | Only groups bot joined |
| First Use | Requires phone verification | No verification |

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
   - Share the group to [@userinfobot](https://t.me/userinfobot)
   - Bot will reply with the group ID

2. **From Web Telegram URL**
   - Open Web Telegram and enter the group chat
   - URL format: `https://web.telegram.org/a/#-100123456789`
   - The number after `#` is the group ID, e.g., `-100123456789`

### Web Interface Features

#### Control Panel
- **Start/Stop/Restart**: Control Bot running status
- **Refresh Status**: Manually refresh current status
- **Status Display**: Running status, forwarded, filtered, total messages

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

### Message Forwarding Issues

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

### Proxy Configuration

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
telerelay/
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
   - Don't expose `.env` file publicly
   - Regularly change API credentials
   - Keep session files secure

2. **Web Interface Security**
   - Must configure `WEB_AUTH_USERNAME` and `WEB_AUTH_PASSWORD` in production
   - Use reverse proxy (like Nginx) to add HTTPS
   - Configure firewall in production environment
   - Restrict Web interface access IPs

3. **Regular Backups**
   - Backup session files (`sessions/`)
   - Backup configuration files

## 📝 License

[MIT License](LICENSE)
