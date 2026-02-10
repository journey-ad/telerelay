"""Global constants definition"""

# Bot manager constants
BOT_STOP_TIMEOUT = 10          # Bot stop timeout (seconds)
BOT_RESTART_DELAY = 2          # Bot restart delay (seconds)
BOT_MAIN_LOOP_INTERVAL = 1     # Bot main loop interval (seconds)

# Forwarder constants
ENTITY_FETCH_TIMEOUT = 5       # Entity info fetch timeout (seconds)
MESSAGE_PREVIEW_LENGTH = 50    # Message preview length
FORWARD_PREVIEW_LENGTH = 30    # Forward preview length

# WebUI constants
UI_REFRESH_INTERVAL = 2.0      # UI refresh interval (seconds)
UI_UPDATE_DEBOUNCE = 1.0       # UI update debounce (seconds)
DEFAULT_LOG_LINES = 50         # Default log lines
MIN_LOG_LINES = 20             # Minimum log lines
MAX_LOG_LINES = 200            # Maximum log lines

# Log constants
LOG_FILE_MAX_BYTES = 10 * 1024 * 1024  # 10MB
LOG_FILE_BACKUP_COUNT = 5      # Keep 5 backups

# Message format
SUCCESS_PREFIX = "✅"
ERROR_PREFIX = "❌"
INFO_PREFIX = "ℹ️"
