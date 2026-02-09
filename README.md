# Telegram 消息转发工具

一个功能强大的 Telegram 消息自动转发工具，支持基于正则表达式和关键词的智能过滤，提供现代化的 Web 管理界面。

## ✨ 功能特性

- 🤖 **智能转发**: 自动监控指定 Telegram 群组/频道并转发消息
- 🔍 **强大过滤**: 支持正则表达式和关键词匹配，黑白名单模式
- 🚫 **忽略列表**: 支持按用户 ID 和关键词忽略特定消息
- 🌐 **Web 管理界面**: 基于 Gradio 的直观配置管理和实时日志查看
- 📊 **实时监控**: 实时显示 Bot 状态、统计信息和日志
- 🐳 **Docker 支持**: 一键部署，开箱即用
- 🔒 **安全可靠**: 支持 User Session 和 Bot Token 两种认证方式
- ⚡ **性能优化**: 异步处理，支持速率限制和错误重试

## 🚀 快速开始

### 前置要求

1. **Telegram API 凭据**
   - 访问 [https://my.telegram.org](https://my.telegram.org)
   - 创建应用获取 `API_ID` 和 `API_HASH`

2. **Bot Token**（可选，如果使用 Bot 模式）
   - 与 [@BotFather](https://t.me/BotFather) 对话创建 Bot
   - 获取 Bot Token

### 方式一：Docker 部署（推荐）

1. **克隆项目**
   ```bash
   cd tg-box
   ```

2. **配置环境变量**
   ```bash
   # 在项目根目录的 config 目录创建 .env 文件
   cp config/.env.example config/.env
   # 编辑配置文件，填入你的 API_ID 和 API_HASH
   nano config/.env
   ```

3. **配置转发规则**
   ```bash
   cp config/config.yaml.example config/config.yaml
   # 编辑 config.yaml，配置源群组和目标群组
   nano config/config.yaml
   ```

4. **启动容器**
   ```bash
   docker-compose up -d
   ```

5. **访问 Web 界面**
   - 打开浏览器访问: `http://localhost:8080`
   - 在 Web 界面中启动 Bot 并查看实时日志

### 方式二：本地运行

1. **安装依赖**
   ```bash
   pip install -r requirements.txt
   ```

2. **配置文件**（同 Docker 部署步骤 2-3）

3. **运行程序**
   ```bash
   python -m src.main
   ```

4. **访问 Web 界面**: `http://localhost:8080`

## 📖 配置说明

### 环境变量（.env）

```env
# Telegram API 凭据（必填）
API_ID=your_api_id
API_HASH=your_api_hash

# Bot Token（Bot 模式必填）
BOT_TOKEN=your_bot_token

# 会话类型: user 或 bot
SESSION_TYPE=user

# Web 服务配置
WEB_HOST=0.0.0.0
WEB_PORT=8080

# 日志级别
LOG_LEVEL=INFO
```

### 配置文件（config.yaml）

```yaml
# 源群组/频道列表（要监控的）
source_chats:
  - -100123456789  # 群组 ID
  - "@channel_name"  # 频道用户名

# 目标群组/频道（转发到的位置）
target_chat: -100987654321

# 过滤规则
filters:
  # 正则表达式（任意匹配即通过）
  regex_patterns:
    - "\\[重要\\].*"
    - "紧急通知.*"

  # 关键词（任意匹配即通过）
  keywords:
    - "关键词1"
    - "关键词2"

  # 过滤模式: whitelist（白名单）或 blacklist（黑名单）
  mode: whitelist

# 转发选项
forwarding:
  preserve_format: true  # 保留原始格式
  add_source_info: true  # 添加来源信息
  delay: 0.5  # 转发延迟（秒）

# 忽略列表（优先级高于过滤规则）
ignore:
  # 忽略的用户 ID 列表
  user_ids:
    # - 123456789

  # 忽略的关键词列表
  keywords:
    # - "广告"
```

## 🎮 使用说明

### 获取群组 ID

1. **User 模式**
   - 将 Bot [@userinfobot](https://t.me/userinfobot) 添加到群组
   - 查看群组 ID（负数）

2. **Bot 模式**
   - 将你的 Bot 添加到群组
   - 发送任意消息，Bot 会显示群组 ID

### Web 界面功能

- **Bot 控制**: 启动/停止/重启 Bot
- **配置管理**: 在线修改源群组、目标群组、过滤规则和忽略列表
- **实时日志**: 查看 Bot 运行状态和转发记录
- **统计信息**: 查看已转发、已过滤和总消息数
- **状态监控**: 实时显示 Bot 运行状态和连接状态

## 🔧 常见问题

### 1. 首次登录需要验证码

**User 模式**下首次运行需要手机验证。由于 Docker 容器内无法交互，建议：
- 本地先运行一次 `python -m src.main` 完成登录
- 会话文件保存在 `sessions/` 目录
- 将会话文件复制到 Docker 挂载的 `sessions/` 目录

**Bot 模式**无需验证，直接使用 Bot Token。

### 2. 无法监控某些群组

- **User 模式**: 可以监控你加入的所有群组
- **Bot 模式**: 只能监控 Bot 加入的群组

### 3. 消息未转发

检查：
- Bot 是否正在运行（查看 Web 界面状态）
- 过滤规则是否正确（检查日志）
- Bot 是否有发送消息权限

### 4. 速率限制 (FloodWait)

Telegram 有速率限制，程序会自动处理并等待。如果频繁触发：
- 增加 `forwarding.delay` 延迟时间
- 检查是否转发了过多消息

## 📦 项目结构

```
tg-box/
├── config/              # 配置文件
│   ├── config.yaml      # 转发规则配置
│   └── config.yaml.example
├── logs/                # 日志文件
├── sessions/            # Telegram 会话文件
├── src/                 # 源代码
│   ├── webui/           # Gradio Web 界面
│   │   ├── handlers/    # 业务处理器
│   │   │   ├── bot_control.py  # Bot 控制
│   │   │   ├── config.py       # 配置管理
│   │   │   └── log.py          # 日志查看
│   │   ├── app.py       # UI 构建
│   │   └── utils.py     # 工具函数
│   ├── main.py          # 主程序入口
│   ├── config.py        # 配置管理
│   ├── client.py        # Telegram 客户端
│   ├── filters.py       # 消息过滤
│   ├── forwarder.py     # 消息转发
│   ├── bot_manager.py   # Bot 生命周期管理
│   └── logger.py        # 日志配置
├── Dockerfile           # Docker 镜像
├── docker-compose.yml   # Docker Compose 配置
└── requirements.txt     # Python 依赖
```

## 🛡️ 安全建议

1. **保护敏感信息**
   - 不要将 `.env` 文件提交到 Git
   - 定期更改 API 凭据

2. **限制访问**
   - 在生产环境中配置防火墙
   - 考虑添加身份验证

3. **定期备份**
   - 备份会话文件（`sessions/`）
   - 备份配置文件

## 📝 许可证

MIT License

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📧 联系

如有问题，请提交 Issue。
