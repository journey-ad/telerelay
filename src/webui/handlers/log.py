"""
日志处理器
"""
from pathlib import Path
from src.logger import get_logger

logger = get_logger()


class LogHandler:
    """日志处理器"""

    @staticmethod
    def get_recent_logs(lines: int = 50) -> str:
        """
        获取最近的日志

        参数:
            lines: 返回的日志行数

        返回:
            日志文本
        """
        try:
            log_dir = Path("logs")

            if not log_dir.exists():
                return "暂无日志"

            # 获取最新的日志文件
            log_files = sorted(log_dir.glob("*.log"), key=lambda f: f.stat().st_mtime, reverse=True)

            if not log_files:
                return "暂无日志"

            # 读取最新日志文件的最后N行
            log_file = log_files[0]
            with open(log_file, 'r', encoding='utf-8') as f:
                all_lines = f.readlines()
                recent_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines

            return ''.join(recent_lines)

        except Exception as e:
            logger.error(f"读取日志失败: {e}", exc_info=True)
            return f"读取日志失败: {str(e)}"
