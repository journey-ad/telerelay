"""全局常量定义"""

# Bot管理器常量
BOT_STOP_TIMEOUT = 10          # Bot停止超时（秒）
BOT_RESTART_DELAY = 2          # Bot重启延迟（秒）
BOT_MAIN_LOOP_INTERVAL = 1     # Bot主循环间隔（秒）

# 转发器常量
ENTITY_FETCH_TIMEOUT = 5       # 实体信息获取超时（秒）
MESSAGE_PREVIEW_LENGTH = 50    # 消息预览长度
FORWARD_PREVIEW_LENGTH = 30    # 转发预览长度

# WebUI常量
UI_REFRESH_INTERVAL = 0.5      # UI刷新间隔（秒）
UI_UPDATE_DEBOUNCE = 1.0       # UI更新防抖（秒）
DEFAULT_LOG_LINES = 50         # 默认日志行数
MIN_LOG_LINES = 20             # 最小日志行数
MAX_LOG_LINES = 200            # 最大日志行数

# 日志常量
LOG_FILE_MAX_BYTES = 10 * 1024 * 1024  # 10MB
LOG_FILE_BACKUP_COUNT = 5      # 保留5个备份

# 消息格式
SUCCESS_PREFIX = "✅"
ERROR_PREFIX = "❌"
INFO_PREFIX = "ℹ️"
