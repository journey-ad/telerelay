# Telegram 消息转发工具 - 功能扩展建议

本文档列出了基于当前项目架构的功能扩展建议，按优先级和实用性排序。

## 📋 当前已实现功能

- ✅ 监控指定 Telegram 群组/频道的消息
- ✅ 基于正则表达式和关键词的过滤（白名单/黑名单模式）
- ✅ 用户和关键词忽略列表
- ✅ 消息转发到多个目标
- ✅ 保留原始格式或复制消息
- ✅ 添加来源信息
- ✅ 转发延迟控制
- ✅ Gradio Web UI 管理界面
- ✅ 实时日志查看
- ✅ 统计信息（已转发、已过滤、总计）
- ✅ HTTP Basic Auth 认证
- ✅ 配置热重载

---

## 🎯 高优先级功能（实用且易实现）

### 1. 消息类型过滤

**功能描述**：
- 支持按媒体类型过滤（纯文本、图片、视频、文件、语音、贴纸等）
- 支持文件大小限制（如：只转发小于 10MB 的文件）

**配置示例**：
```yaml
filters:
  # 允许的消息类型
  media_types: ["text", "photo", "video"]
  # 最大文件大小（字节）
  max_file_size: 10485760  # 10MB
  # 最小文件大小（字节）
  min_file_size: 0
```

**实现要点**：
- 在 `filters.py` 的 `should_forward()` 方法中添加媒体类型检查
- 使用 Telethon 的 `message.media` 属性判断类型
- 文件大小通过 `message.file.size` 获取

---

### 2. 消息内容处理

**功能描述**：
- **正则替换**：转发前修改消息内容（如：替换敏感词、统一格式）
- **消息去重**：基于内容哈希避免重复转发相同消息
- **链接提取/过滤**：只转发包含特定域名的消息，或过滤掉所有链接

**配置示例**：
```yaml
content_processing:
  # 内容替换规则
  replacements:
    - pattern: "敏感词"
      replacement: "***"
    - pattern: "\\d{11}"  # 手机号
      replacement: "[已隐藏]"

  # 消息去重
  deduplicate: true
  deduplicate_window: 3600  # 1小时内去重（秒）

  # 链接过滤
  link_filter:
    mode: "whitelist"  # whitelist 或 blacklist
    domains:
      - "github.com"
      - "stackoverflow.com"
```

**实现要点**：
- 在 `forwarder.py` 中添加内容处理逻辑
- 使用 `hashlib` 计算消息哈希，存储在内存或 Redis 中
- 使用正则表达式提取和过滤链接

---

### 3. 多规则组支持

**功能描述**：
- 支持配置多组转发规则，每组独立的源、目标和过滤条件
- 适用场景：同时监控多个群组，转发到不同目标

**配置示例**：
```yaml
forwarding_rules:
  - name: "重要通知"
    enabled: true
    source_chats:
      - -100123456789
    target_chats:
      - -100111111111
    filters:
      mode: whitelist
      keywords: ["重要", "紧急"]
    forwarding:
      preserve_format: true
      add_source_info: true
      delay: 0.5

  - name: "技术讨论"
    enabled: true
    source_chats:
      - -100987654321
    target_chats:
      - -100222222222
      - -100333333333
    filters:
      mode: blacklist
      keywords: ["广告", "推广"]
```

**实现要点**：
- 重构 `config.py` 支持多规则配置
- 在 `bot_manager.py` 中为每个规则创建独立的 `MessageFilter` 和 `MessageForwarder`
- Web UI 支持规则列表的增删改查

---

### 4. 时间段过滤

**功能描述**：
- 只在特定时间段转发消息（如：工作时间 9:00-18:00）
- 支持时区配置
- 支持多个时间段

**配置示例**：
```yaml
filters:
  time_ranges:
    - start: "09:00"
      end: "18:00"
      timezone: "Asia/Shanghai"
      days: [1, 2, 3, 4, 5]  # 周一到周五，1=周一，7=周日
    - start: "20:00"
      end: "22:00"
      timezone: "Asia/Shanghai"
      days: [6, 7]  # 周末
```

**实现要点**：
- 在 `filters.py` 中添加时间检查方法
- 使用 `datetime` 和 `pytz` 处理时区
- 在 `should_forward()` 中添加时间判断

---

### 5. 消息历史记录

**功能描述**：
- 在 SQLite 数据库中记录已转发的消息
- Web UI 中查看转发历史
- 支持搜索和导出（CSV/JSON）
- 统计数据可视化（每日转发趋势图）

**数据库表结构**：
```sql
CREATE TABLE forwarded_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER,
    source_chat_id INTEGER,
    source_chat_name TEXT,
    sender_id INTEGER,
    sender_name TEXT,
    content TEXT,
    media_type TEXT,
    target_chats TEXT,  -- JSON 数组
    forwarded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    rule_name TEXT
);

CREATE INDEX idx_forwarded_at ON forwarded_messages(forwarded_at);
CREATE INDEX idx_source_chat ON forwarded_messages(source_chat_id);
```

**实现要点**：
- 使用 `sqlite3` 或 `sqlalchemy` 管理数据库
- 在 `forwarder.py` 转发成功后记录到数据库
- Web UI 添加"历史记录"标签页，支持分页和搜索
- 使用 `plotly` 或 `matplotlib` 生成统计图表

---

## 🔧 中优先级功能（增强体验）

### 6. 消息模板化

**功能描述**：
- 自定义转发消息的格式
- 支持变量：`{source}`, `{sender}`, `{time}`, `{content}`, `{message_id}` 等

**配置示例**：
```yaml
forwarding:
  message_template: |
    📢 来源：{source}
    👤 发送者：{sender}
    🕐 时间：{time}
    🔗 消息ID：{message_id}

    {content}
```

**实现要点**：
- 在 `forwarder.py` 中使用 Python 字符串格式化
- 支持条件模板（如：有媒体时显示不同格式）

---

### 7. 转发限额控制

**功能描述**：
- 每小时/每天最多转发 N 条消息
- 防止消息洪水
- 达到限额后暂停转发或发送通知

**配置示例**：
```yaml
forwarding:
  rate_limits:
    hourly: 100
    daily: 500
    action: "pause"  # pause 或 notify
```

**实现要点**：
- 使用滑动窗口算法统计转发数量
- 在 `forwarder.py` 中添加限额检查
- 达到限额后记录日志并执行相应动作

---

### 8. 关键消息通知

**功能描述**：
- 匹配特定规则时发送 Telegram 通知给管理员
- 支持多个通知目标
- 自定义通知消息格式

**配置示例**：
```yaml
notifications:
  enabled: true
  targets:
    - 123456789  # 管理员 user_id
    - -100999999999  # 管理群组
  rules:
    - pattern: "紧急|urgent|critical"
      message: "⚠️ 检测到紧急消息：{content}"
    - pattern: "错误|error|failed"
      message: "❌ 检测到错误消息：{content}"
```

**实现要点**：
- 在 `forwarder.py` 中添加通知逻辑
- 使用独立的方法发送通知，避免影响正常转发
- 支持通知去重（避免频繁通知）

---

### 9. 调试模式

**功能描述**：
- 模拟转发，不实际发送消息
- 在日志中显示会转发的内容
- 便于测试过滤规则

**配置示例**：
```yaml
debug:
  dry_run: true  # 只记录，不实际转发
  verbose: true  # 详细日志
```

**实现要点**：
- 在 `forwarder.py` 的 `forward_message()` 中添加 dry_run 检查
- dry_run 模式下只记录日志，不调用 Telegram API
- Web UI 添加"调试模式"开关

---

### 10. 发送者身份过滤

**功能描述**：
- 基于发送者角色过滤（管理员、普通成员、Bot）
- 基于发送者是否为 Premium 用户
- 基于发送者是否已验证

**配置示例**：
```yaml
filters:
  sender_types: ["admin", "member"]  # 只转发管理员和普通成员的消息
  exclude_bots: true  # 排除 Bot 发送的消息
  premium_only: false  # 是否只转发 Premium 用户的消息
  verified_only: false  # 是否只转发已验证用户的消息
```

**实现要点**：
- 使用 Telethon 的 `get_permissions()` 获取用户权限
- 检查 `sender.bot` 属性判断是否为 Bot
- 检查 `sender.premium` 和 `sender.verified` 属性

---

## 🚀 低优先级功能（高级需求）

### 11. Webhook 集成

**功能描述**：
- 将消息转发到外部 HTTP API
- 支持自定义请求格式
- 支持重试和错误处理

**配置示例**：
```yaml
webhooks:
  - name: "外部API"
    enabled: true
    url: "https://example.com/api/messages"
    method: "POST"
    headers:
      Authorization: "Bearer token"
      Content-Type: "application/json"
    body_template: |
      {
        "source": "{source}",
        "sender": "{sender}",
        "content": "{content}",
        "timestamp": "{timestamp}"
      }
    retry: 3
    timeout: 10
```

---

### 12. 消息队列

**功能描述**：
- 使用 Redis 作为消息队列
- 支持分布式部署
- 提高可靠性和性能

**实现要点**：
- 使用 `redis-py` 或 `rq` 库
- 消息先入队，由独立的 worker 处理转发
- 支持消息持久化和重试

---

### 13. 媒体处理

**功能描述**：
- 图片压缩（减小文件大小）
- 添加水印
- 视频截图
- 文件格式转换

**实现要点**：
- 使用 `Pillow` 处理图片
- 使用 `ffmpeg` 处理视频
- 在转发前对媒体文件进行处理

---

### 14. 多用户/多配置

**功能描述**：
- 支持多个独立的转发配置
- 每个配置独立运行
- Web UI 切换配置

**实现要点**：
- 重构配置管理，支持多配置文件
- 每个配置独立的 Bot 实例
- Web UI 添加配置选择器

---

### 15. 性能监控

**功能描述**：
- 转发延迟统计
- 成功率监控
- 资源使用情况（CPU、内存）
- Prometheus 指标导出

**实现要点**：
- 使用 `prometheus_client` 导出指标
- 记录每次转发的耗时
- 统计成功率和失败率
- Web UI 显示性能图表

---

## 📊 推荐实施顺序

如果要扩展功能，建议按以下顺序实施：

1. **消息类型过滤** - 最常见的需求，实现简单
2. **消息去重** - 避免重复转发，提升用户体验
3. **多规则组支持** - 大幅提升灵活性
4. **消息历史记录** - 便于追溯和统计
5. **时间段过滤** - 实用且易实现
6. **消息模板化** - 提升定制化能力
7. **调试模式** - 方便开发和测试
8. **转发限额控制** - 防止滥用
9. **关键消息通知** - 增强监控能力
10. 其他功能根据实际需求选择

---

## 🛠️ 技术实现建议

### 架构调整

1. **配置管理**：
   - 考虑使用 `pydantic` 进行配置验证
   - 支持配置文件热重载
   - 配置版本管理

2. **数据持久化**：
   - 使用 SQLite 作为默认数据库（轻量级）
   - 可选支持 PostgreSQL/MySQL（生产环境）
   - 使用 `sqlalchemy` 作为 ORM

3. **异步处理**：
   - 保持当前的 asyncio 架构
   - 考虑使用消息队列处理高负载场景
   - 添加任务队列管理

4. **错误处理**：
   - 完善异常捕获和日志记录
   - 添加错误重试机制
   - 错误通知（邮件/Telegram）

5. **测试**：
   - 添加单元测试（pytest）
   - 添加集成测试
   - 使用 Mock 测试 Telegram API 调用

### 代码组织

```
src/
├── core/              # 核心功能
│   ├── client.py
│   ├── filters.py
│   ├── forwarder.py
│   └── processor.py   # 新增：消息处理
├── storage/           # 新增：数据存储
│   ├── database.py
│   ├── cache.py
│   └── models.py
├── integrations/      # 新增：第三方集成
│   ├── webhook.py
│   └── notification.py
├── webui/
│   ├── app.py
│   ├── handlers/
│   └── components/    # 新增：UI 组件
└── utils/
    ├── time.py        # 新增：时间处理
    ├── media.py       # 新增：媒体处理
    └── template.py    # 新增：模板引擎
```

---

## 📝 注意事项

1. **Telegram API 限制**：
   - 注意速率限制（FloodWait）
   - 文件大小限制（2GB for bots, 4GB for users）
   - 消息长度限制（4096 字符）

2. **性能考虑**：
   - 大量消息时考虑使用消息队列
   - 数据库查询优化（索引、分页）
   - 缓存常用数据（Redis）

3. **安全性**：
   - 敏感信息加密存储
   - API Token 安全管理
   - 输入验证和过滤

4. **可维护性**：
   - 保持代码简洁和模块化
   - 完善的文档和注释
   - 遵循 Python 编码规范（PEP 8）

---

## 🤝 贡献指南

欢迎提交功能建议和 Pull Request！

在实现新功能前，请：
1. 在 Issues 中讨论功能需求
2. 确保功能符合项目定位
3. 遵循现有代码风格
4. 添加必要的测试和文档

---

**最后更新**：2026-02-09
