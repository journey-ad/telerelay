"""
Bot控制处理器
"""
from typing import Tuple
from src.bot_manager import BotManager
from src.config import Config
from src.logger import get_logger
from ..utils import format_message

logger = get_logger()


class BotControlHandler:
    """Bot控制处理器"""

    def __init__(self, bot_manager: BotManager, config: Config):
        self.bot_manager = bot_manager
        self.config = config

    def start_bot(self) -> str:
        """启动Bot"""
        try:
            if self.bot_manager.is_running:
                return format_message("Bot 已在运行中", "info")

            # 验证配置
            is_valid, error_msg = self.config.validate()
            if not is_valid:
                return format_message(f"配置验证失败: {error_msg}", "error")

            success = self.bot_manager.start()
            if success:
                logger.info("Bot 已通过 WebUI 启动")
                return format_message("Bot 已成功启动", "success")
            else:
                return format_message("Bot 启动失败", "error")

        except Exception as e:
            logger.error(f"启动 Bot 失败: {e}", exc_info=True)
            return format_message(f"启动失败: {str(e)}", "error")

    def stop_bot(self) -> str:
        """停止Bot"""
        try:
            if not self.bot_manager.is_running:
                return format_message("Bot 未在运行", "info")

            success = self.bot_manager.stop()
            if success:
                logger.info("Bot 已通过 WebUI 停止")
                return format_message("Bot 已成功停止", "success")
            else:
                return format_message("Bot 停止失败", "error")

        except Exception as e:
            logger.error(f"停止 Bot 失败: {e}", exc_info=True)
            return format_message(f"停止失败: {str(e)}", "error")

    def restart_bot(self) -> str:
        """重启Bot"""
        try:
            # 重新加载配置
            self.config.load()

            success = self.bot_manager.restart()

            if success:
                logger.info("Bot 已通过 WebUI 重启")
                return format_message("Bot 已成功重启", "success")
            else:
                return format_message("Bot 重启失败", "error")

        except Exception as e:
            logger.error(f"重启 Bot 失败: {e}", exc_info=True)
            return format_message(f"重启失败: {str(e)}", "error")

    def get_status(self) -> Tuple[str, str, str, str]:
        """
        获取Bot状态

        返回:
            (状态文本, 已转发数, 已过滤数, 总计数)
        """
        try:
            status = self.bot_manager.get_status()

            if status['is_running']:
                status_text = "🟢 运行中" if status['is_connected'] else "🟡 连接中..."
            else:
                status_text = "⚫ 已停止"

            stats = status.get('stats', {})
            forwarded = str(stats.get('forwarded', 0))
            filtered = str(stats.get('filtered', 0))
            total = str(stats.get('total', 0))

            return status_text, forwarded, filtered, total

        except Exception as e:
            logger.error(f"获取状态失败: {e}", exc_info=True)
            return "❌ 状态异常", "0", "0", "0"
