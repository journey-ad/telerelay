"""
Log Handler
"""
from pathlib import Path
from src.logger import get_logger
from src.i18n import t

logger = get_logger()


class LogHandler:
    """Log Handler"""

    @staticmethod
    def get_recent_logs(lines: int = 50) -> str:
        """
        Get recent logs

        Args:
            lines: Number of log lines to return

        Returns:
            Log text
        """
        try:
            log_dir = Path("logs")

            if not log_dir.exists():
                return t("message.log.no_logs")

            # Get the latest log file
            log_files = sorted(log_dir.glob("*.log"), key=lambda f: f.stat().st_mtime, reverse=True)

            if not log_files:
                return t("message.log.no_logs")

            # Read the last N lines of the latest log file
            log_file = log_files[0]
            with open(log_file, 'r', encoding='utf-8') as f:
                all_lines = f.readlines()
                recent_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines

            return ''.join(recent_lines)

        except Exception as e:
            logger.error(t("message.log.read_failed", error=str(e)), exc_info=True)
            return t("message.log.read_failed", error=str(e))
