[English](README.md)

# TeleRelay

TeleRelay 是一个自托管的 Telegram 消息转发与归档工具。项目采用 FastAPI 后端和 Vue 3 管理控制台，支持持久化转发队列、规则过滤、回调按钮自动化及消息导出。

## 功能

- 多组独立转发规则，分别配置来源、目标、过滤、忽略及转发选项
- 基于 SQLite 的持久化转发队列，支持重试、FloodWait 和重启恢复
- User Session 与 Bot Token 两种 Telegram 运行模式
- User 模式下按精确、包含或正则匹配自动点击 Telegram 回调按钮
- 将消息导出为 JSON、CSV、SQLite 和离线 HTML
- 按小时、天或周执行增量导出任务
- 通过 Server-Sent Events 实时推送运行状态和日志
- 管理 API 与控制台支持 HTTP Basic Auth
- 可选的 Telegram 管理 Bot

## 架构

TeleRelay 有意保持为一个服务：

- `backend/`：FastAPI、Telethon 运行时、应用服务、SQLite 存储和 REST/SSE API
- `frontend/`：Vue 3、TypeScript、Vite、Pinia、TanStack Query 和 ECharts
- 生产环境由 FastAPI 直接托管 `frontend/dist`
- Uvicorn 固定为单 worker，确保 Telegram client、调度器和内存任务只启动一次

REST API 位于 `/api/v1`，OpenAPI 文档位于 `/api/docs`，SSE 事件流位于 `/api/v1/events`。

## 快速开始

### 配置

从示例创建本地配置：

```bash
cp .env.example .env
cp config/config.yaml.example config/config.yaml
```

至少需要在 `.env` 中设置 `API_ID` 和 `API_HASH`。使用 `SESSION_TYPE=bot` 时还需要设置 `BOT_TOKEN`。如果控制台会被其他设备访问，应同时设置 `WEB_AUTH_USERNAME` 和 `WEB_AUTH_PASSWORD`。

Telegram API 凭据从 [my.telegram.org](https://my.telegram.org) 获取，Bot Token 通过 [@BotFather](https://t.me/BotFather) 创建。

### Docker Compose

```bash
docker compose up -d --build
```

打开 `http://localhost:8080`。Compose 会通过 `config/`、`data/` 和 `logs/` 挂载持久化配置、Telegram session、数据库、导出文件及日志。

如需直接使用发布镜像，可删除 `docker-compose.yml` 中的 `build: .`，保留 `image: ghcr.io/journey-ad/telerelay:latest`。

### 本地生产构建

需要 Python 3.11+ 和 Node.js 22+。

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

打开 `http://localhost:8080`。

### 前端开发

分别启动 API 和 Vite：

```bash
python -m backend.main
```

```bash
cd frontend
npm ci
npm run dev
```

Vite 在 `http://localhost:5173` 提供控制台，并将 `/api` 代理到 `http://127.0.0.1:8080`。

## 配置职责

`.env` 保存进程凭据和运行参数：

- Telegram 凭据与 `SESSION_TYPE`
- 代理、监听地址、端口、日志级别和运行时语言
- Web Basic Auth 凭据
- 可选的管理 Bot 与 Mini App 设置

`config/config.yaml` 保存可变的应用配置：

- 转发规则和回调按钮规则
- 过滤、忽略及转发选项
- 持久转发队列设置
- 导出目录、时区和并发数

控制台可以导入或导出 YAML 配置。凭据仍保存在 `.env` 中，不会进入配置备份。

## 持久化数据

- `data/telegram_session.session`：Telegram 用户 session
- `data/forward_queue.db`：待转发任务和去重记录
- `data/stats.db`：转发统计与历史
- `data/exports.db`：导出任务与运行历史
- `data/db/msg_export_{chat_id}.sqlite3`：按会话保存的标准消息归档
- `data/exports/`：生成的 JSON、CSV、SQLite 和 HTML 文件
- `logs/telerelay.log`：按天轮转的应用日志

建议一起备份 `config/`、`data/` 和 `.env`。`.env` 与 Telegram session 均应视为敏感信息。

## User 模式认证

使用 `SESSION_TYPE=user` 时，在 Settings 页面启动 Telegram 认证，并按状态提交手机号、验证码和 2FA 密码。认证 challenge 由异步 API 管理，不需要在终端输入。

使用 `SESSION_TYPE=bot` 时配置 `BOT_TOKEN`。回调按钮自动化和账号级导出会话发现仅适用于 User 模式。

## 管理 Bot

设置 `ADMIN_BOT_TOKEN` 和 `ADMIN_CHAT_ID` 后可以使用：

- `/status`
- `/bot start|stop|restart`
- `/rule list|detail|add|del|rename|toggle|set`
- `/webapp`

管理 Bot 必须使用独立 Token，其控制命令会提交到 FastAPI 所在的 asyncio loop。

## 开发检查

```bash
PYTHONPYCACHEPREFIX=/tmp/telerelay-pyc .venv/bin/python -m compileall -q backend tests
.venv/bin/python -m unittest discover -s tests -v
cd frontend && npm run build
```

## 项目结构

```text
telerelay/
├── backend/              # FastAPI API 与 Telegram 运行时
│   ├── api/              # REST 与 SSE 路由
│   ├── exporter/         # 导出引擎与调度器
│   ├── forwarder/        # 消息转发流水线
│   ├── schemas/          # HTTP 请求契约
│   ├── services/         # 与 UI 无关的应用服务
│   └── main.py           # FastAPI/Uvicorn 入口
├── frontend/             # Vue 3 + TypeScript 控制台
│   └── src/
├── config/               # 可变 YAML 配置
├── data/                 # Session、SQLite 与导出文件
├── logs/                 # 轮转日志
├── tests/
├── Dockerfile
└── docker-compose.yml
```

## 安全建议

- 8080 端口会被其他设备访问时必须启用 Web Basic Auth。
- 通过反向代理提供 HTTPS；不要让 Basic Auth 凭据通过公网明文 HTTP 传输。
- 限制 `.env`、`data/*.session`、数据库、导出文件和备份的访问权限。
- Uvicorn 必须保持单 worker，多 worker 会重复启动 Telegram client 和调度器。

## 许可证

[MIT License](LICENSE)
