# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

这是一个 Telegram 消息自动转发工具，支持基于正则表达式和关键词的智能过滤，提供 Gradio Web 管理界面。

**核心功能**：
- 监控指定 Telegram 群组/频道的消息
- 根据配置的过滤规则（正则表达式、关键词、黑白名单）过滤消息
- 将符合条件的消息转发到目标群组/频道
- 提供 Web UI 进行实时监控和配置管理

## 开发环境设置

### 安装依赖
```bash
pip install -r requirements.txt
```

### 运行程序
```bash
# 本地运行
python -m src.main

# Docker 运行
docker-compose up -d
```

### 配置文件
- `.env`: 环境变量配置（API_ID, API_HASH, BOT_TOKEN 等）
- `config/config.yaml`: 转发规则配置（源群组、目标群组、过滤规则等）
- 示例文件位于 `config/*.example`

## 架构设计

### 核心模块关系

```
main.py (入口)
  ├─> config.py (配置管理)
  ├─> bot_manager.py (Bot 生命周期管理)
  │     ├─> client.py (Telegram 客户端封装)
  │     ├─> filters.py (消息过滤逻辑)
  │     └─> forwarder.py (消息转发逻辑)
  └─> webui/ (Gradio Web 界面)
        ├─> app.py (UI 构建)
        └─> handlers/ (业务处理器)
              ├─> bot_control.py (Bot 控制)
              ├─> config.py (配置管理)
              └─> log.py (日志查看)
```

### 关键设计模式

1. **线程模型**：
   - 主线程运行 Gradio Web 服务器
   - Bot 在独立线程中运行，拥有自己的 asyncio 事件循环
   - 使用 `threading.RLock()` 保证线程安全的状态访问

2. **配置管理**：
   - `Config` 类统一管理环境变量（.env）和 YAML 配置
   - 支持运行时动态更新配置并保存
   - 配置更新后可触发 Bot 重启

3. **消息处理流程**：
   ```
   Telegram 消息 -> client.py (接收)
                 -> filters.py (过滤)
                 -> forwarder.py (转发)
   ```

4. **UI 更新机制**：
   - 使用防抖机制（1秒内最多触发一次）避免频繁刷新
   - `bot_manager.trigger_ui_update()` 设置更新标志
   - Gradio Timer 定期检查标志并更新 UI

### 重要类说明

- **BotManager** (`bot_manager.py`): 管理 Bot 的启动、停止、重启，协调各组件
- **TelegramClientManager** (`client.py`): 封装 Telethon 客户端，处理连接和消息监听
- **MessageFilter** (`filters.py`): 实现消息过滤逻辑（正则、关键词、黑白名单、忽略列表）
- **MessageForwarder** (`forwarder.py`): 处理消息转发，包含速率限制和错误重试
- **Config** (`config.py`): 配置加载、验证和持久化

## 常见开发任务

### 修改过滤逻辑
编辑 `src/filters.py` 中的 `MessageFilter.should_forward()` 方法。

### 添加新的配置项
1. 在 `config/config.yaml.example` 添加示例配置
2. 在 `src/config.py` 的 `Config` 类添加对应的 `@property`
3. 在需要使用的模块中通过 `config.xxx` 访问

### 修改 Web UI
- UI 布局：`src/webui/app.py`
- 业务逻辑：`src/webui/handlers/` 下的各个处理器

### 调试技巧
- 日志文件位于 `logs/` 目录
- 修改 `.env` 中的 `LOG_LEVEL=DEBUG` 获取详细日志
- 使用 `python -m src.main` 本地运行便于调试

## 重要注意事项

### Telegram 客户端
- 支持两种模式：User Session（用户账号）和 Bot Token（机器人）
- User 模式首次运行需要手机验证码，会话文件保存在 `sessions/` 目录
- Bot 模式无需验证，但只能监控 Bot 加入的群组

### 线程安全
- `BotManager` 的 `is_running` 和 `is_connected` 使用 `@property` 和锁保护
- 访问共享状态时必须使用 `with self._lock:`

### 配置更新
- 配置更新后需要重启 Bot 才能生效
- `config_handler.py` 中的 `save_config()` 会自动触发重启

### 速率限制
- Telegram 有严格的速率限制（FloodWait）
- `forwarder.py` 中已实现自动等待和重试机制
- 可通过 `forwarding.delay` 配置转发延迟

## 项目约定

- 所有注释和文档使用中文
- 使用 Python 3.11+
- 异步代码使用 `async/await` 语法
- 日志使用统一的 `logger` 实例（通过 `get_logger()` 获取）
