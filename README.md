# Telegram 消息转发工具

一个功能强大的 Telegram 消息自动转发工具，支持基于正则表达式和关键词的智能过滤，提供现代化的 Web 管理界面。

## ✨ 功能特性

- 🤖 **智能转发**: 自动监控指定 Telegram 群组/频道并转发消息到多个目标
- 🔍 **强大过滤**: 支持正则表达式和关键词匹配，黑白名单模式
- 🚫 **忽略列表**: 支持按用户 ID 和关键词忽略特定消息
- 🌐 **Web 管理界面**: 基于 Gradio 的直观配置管理和实时日志查看
- 🔐 **双重认证模式**: 支持 User Session（手机号登录）和 Bot Token 两种方式
- 📊 **实时监控**: 实时显示 Bot 状态、统计信息和日志
- 🐳 **Docker 支持**: 一键部署，开箱即用
- 🔒 **安全可靠**: 支持 Web 界面 HTTP Basic Auth 认证
- ⚡ **性能优化**: 异步处理，支持速率限制和错误重试
- 🌍 **代理支持**: 支持 SOCKS5/HTTP 代理配置

## 🚀 快速开始

### 前置要求

1. **Telegram API 凭据**
   - 访问 [https://my.telegram.org](https://my.telegram.org)
   - 创建应用获取 `API_ID` 和 `API_HASH`

2. **Bot Token**（如果使用 Bot 模式）
   - 与 [@BotFather](https://t.me/BotFather) 对话创建 Bot
   - 获取 Bot Token

### 方式一：Docker 部署（推荐）

1. **克隆项目**
   ```bash
   cd tg-box
   ```

2. **配置环境变量**
   ```bash
   # 复制示例配置
   cp .env.example .env
   # 编辑配置文件，填入你的 API_ID 和 API_HASH
   nano .env
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
   - 如果配置了 HTTP Basic Auth，输入用户名和密码

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
# user: 使用用户账号（可以监控所有群组）
# bot: 使用 Bot Token（仅能监控 Bot 加入的群组）
SESSION_TYPE=user

# 代理配置（可选）
# 支持的协议：socks5, http
# 示例：socks5://127.0.0.1:1080 或 http://127.0.0.1:1080
PROXY_URL=

# Web 服务配置
WEB_HOST=0.0.0.0
WEB_PORT=8080

# Web 界面认证（推荐在生产环境启用）
WEB_AUTH_USERNAME=
WEB_AUTH_PASSWORD=

# 日志级别：DEBUG, INFO, WARNING, ERROR
LOG_LEVEL=INFO
```

### 配置文件（config/config.yaml）

```yaml
# 源群组/频道列表（要监控的）
source_chats:
  - -100123456789  # 群组 ID
  - "@channel_name"  # 频道用户名

# 目标群组/频道列表（转发到的位置，支持多个目标）
target_chats:
  - -100987654321  # 目标群组 1
  - "@target_channel"  # 目标频道 2

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

  # 忽略的关键词列表（不区分大小写）
  keywords:
    # - "广告"
```

## 🎮 使用说明

### 认证模式对比

| 特性 | User 模式 | Bot 模式 |
|------|----------|---------|
| 认证方式 | 手机号 + 验证码 | Bot Token |
| 监控范围 | 所有已加入的群组 | 仅 Bot 加入的群组 |
| Web 界面 | 有认证标签页 | 无认证标签页 |
| 首次使用 | 需要手机验证 | 无需验证 |
| 会话持久化 | sessions/ 目录 | sessions/ 目录 |

### User 模式认证流程

1. 设置 `SESSION_TYPE=user`
2. 启动应用，访问 Web 界面
3. 在「🔐 认证」标签页点击「开始认证」
4. 输入手机号（国际格式，如 `+8613800138000`）
5. 输入 Telegram 发送的验证码
6. 如果启用了两步验证，输入密码
7. 认证成功后显示当前登录账号信息

### 获取群组 ID

1. **使用 @userinfobot**
   - 将 [@userinfobot](https://t.me/userinfobot) 添加到群组
   - 在群组中发送任意消息，Bot 会回复群组 ID

2. **从消息中获取**
   - 转发群组消息到 [@userinfobot](https://t.me/userinfobot)
   - 获取消息来源的群组 ID

### Web 界面功能

#### 控制面板
- **启动/停止/重启**: 控制 Bot 运行状态
- **刷新状态**: 手动刷新当前状态
- **状态显示**: 运行状态、已转发、已过滤、总消息数

#### 配置标签页
- **源群组配置**: 设置要监控的群组
- **目标群组配置**: 设置转发目标（支持多个）
- **过滤规则**: 正则表达式和关键词匹配
- **忽略列表**: 用户 ID 和关键词屏蔽
- **转发选项**: 格式保留、来源信息、延迟设置

#### 日志标签页
- **实时日志**: 查看运行日志
- **日志行数**: 可调整显示行数

#### 认证标签页（仅 User 模式）
- **认证状态**: 显示当前登录状态和账号信息
- **认证操作**: 开始认证、取消认证
- **输入表单**: 手机号、验证码、密码

## 🔧 常见问题

### 1. User 模式认证

**如何在 Docker 中进行首次认证？**
- 方式一：本地先运行完成登录，再将 `sessions/` 目录挂载到容器
- 方式二：Docker 容器启动后，通过 Web 界面的认证标签页完成认证

**会话过期怎么办？**
- 在 Web 界面的认证标签页点击「取消认证」清除旧会话
- 重新点击「开始认证」完成新的登录

### 2. Bot 模式配置

**为什么看不到认证标签页？**
- Bot 模式不需要手机验证，认证标签页会自动隐藏
- 确认 `.env` 中 `SESSION_TYPE=bot` 且 `BOT_TOKEN` 已配置

### 3. 消息转发问题

**消息未转发？**
检查：
- Bot 是否正在运行（查看 Web 界面状态）
- 过滤规则是否正确（检查日志）
- Bot 是否有发送消息权限

**触发速率限制 (FloodWait)？**
- 程序会自动处理并等待
- 可增加 `forwarding.delay` 延迟时间

### 4. 代理配置

**如何配置代理？**
```env
# SOCKS5 代理
PROXY_URL=socks5://127.0.0.1:1080

# HTTP 代理
PROXY_URL=http://127.0.0.1:1080

# 带认证的代理
PROXY_URL=socks5://user:password@127.0.0.1:1080
```

## 📦 项目结构

```
tg-box/
├── .env.example          # 环境变量示例
├── config/               # 配置文件目录
│   └── config.yaml.example
├── logs/                 # 日志文件
├── sessions/             # Telegram 会话文件
├── src/                  # 源代码
│   ├── webui/            # Gradio Web 界面
│   │   ├── handlers/     # 业务处理器
│   │   │   ├── auth.py         # 认证处理
│   │   │   ├── bot_control.py  # Bot 控制
│   │   │   ├── config.py       # 配置管理
│   │   │   └── log.py          # 日志查看
│   │   ├── app.py        # UI 构建
│   │   └── utils.py      # 工具函数
│   ├── main.py           # 主程序入口
│   ├── config.py         # 配置管理
│   ├── client.py         # Telegram 客户端
│   ├── auth_manager.py   # User 模式认证管理
│   ├── bot_manager.py    # Bot 生命周期管理
│   ├── filters.py        # 消息过滤
│   ├── forwarder.py      # 消息转发
│   ├── constants.py      # 常量定义
│   ├── utils.py          # 工具函数
│   └── logger.py         # 日志配置
├── Dockerfile            # Docker 镜像
├── docker-compose.yml    # Docker Compose 配置
└── requirements.txt      # Python 依赖
```

## 🛡️ 安全建议

1. **保护敏感信息**
   - 不要将 `.env` 文件提交到 Git
   - 定期更改 API 凭据
   - 妥善保管会话文件

2. **Web 界面安全**
   - 生产环境必须配置 `WEB_AUTH_USERNAME` 和 `WEB_AUTH_PASSWORD`
   - 使用反向代理（如 Nginx）添加 HTTPS

3. **限制访问**
   - 在生产环境中配置防火墙
   - 限制 Web 界面的访问 IP

4. **定期备份**
   - 备份会话文件（`sessions/`）
   - 备份配置文件

## 📝 许可证

MIT License

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📧 联系

如有问题，请提交 Issue。
