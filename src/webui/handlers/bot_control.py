"""
Bot Control Handler
"""
from typing import Tuple
from src.bot_manager import BotManager
from src.config import Config
from src.logger import get_logger
from src.i18n import t
from ..utils import format_message
from .auth import STATE_DESCRIPTIONS

logger = get_logger()


class BotControlHandler:
    """Bot Control Handler"""

    def __init__(self, bot_manager: BotManager, config: Config):
        self.bot_manager = bot_manager
        self.config = config

    def start_bot(self) -> str:
        """Start Bot"""
        try:
            if self.bot_manager.is_running:
                # If in User mode, check authentication status
                if self.config.session_type == "user" and self.bot_manager.auth_manager:
                    state_info = self.bot_manager.auth_manager.get_state()
                    state = state_info["state"]

                    # If in authentication process, prompt user
                    if state in ["waiting_phone", "waiting_code", "waiting_password"]:
                        return format_message(t("message.bot.auth_in_progress", state=STATE_DESCRIPTIONS.get(state, "")), "info")

                    # If authentication is already successful
                    if state == "success":
                        return format_message(t("message.bot.running"), "success")

                return format_message(t("message.bot.already_running"), "info")

            # Validate configuration
            is_valid, error_msg = self.config.validate()
            if not is_valid:
                return format_message(t("message.bot.config_invalid", error=error_msg), "error")

            # Start Bot (User mode will automatically trigger authentication process)
            success = self.bot_manager.start()
            if success:
                logger.info(t("log.bot.started", count=1) + t("misc.via_webui"))
                if self.config.session_type == "user":
                    # Check if session file exists
                    from pathlib import Path
                    session_file = Path("sessions/telegram_session.session")
                    if session_file.exists():
                        return format_message(t("message.bot.session_detected"), "success")
                    else:
                        return format_message(t("message.bot.auth_started"), "success")
                else:
                    return format_message(t("message.bot.start_success"), "success")
            else:
                return format_message(t("message.bot.start_failed"), "error")

        except Exception as e:
            logger.error(t("log.bot.start_failed", error=str(e)), exc_info=True)
            return format_message(t("message.bot.start_failed") + f": {str(e)}", "error")

    def stop_bot(self) -> str:
        """Stop Bot"""
        try:
            if not self.bot_manager.is_running:
                return format_message(t("message.bot.not_running"), "info")

            success = self.bot_manager.stop()
            if success:
                logger.info(t("log.bot.stop_success") + t("misc.via_webui"))
                return format_message(t("message.bot.stop_success"), "success")
            else:
                return format_message(t("message.bot.stop_failed"), "error")

        except Exception as e:
            logger.error(t("log.bot.stop_failed", error=str(e)), exc_info=True)
            return format_message(t("message.bot.stop_failed") + f": {str(e)}", "error")

    def restart_bot(self) -> str:
        """Restart Bot"""
        try:
            # Reload configuration
            self.config.load()

            success = self.bot_manager.restart()

            if success:
                logger.info(t("log.bot.started", count=1) + t("misc.via_webui_restart"))
                return format_message(t("message.bot.restart_success"), "success")
            else:
                return format_message(t("message.bot.restart_failed"), "error")

        except Exception as e:
            logger.error(t("log.bot.start_failed", error=str(e)) + t("misc.restart_suffix"), exc_info=True)
            return format_message(t("message.bot.restart_failed") + f": {str(e)}", "error")

    def get_status(self) -> Tuple[str, str, str, str]:
        """
        Get Bot status

        Returns:
            (status text, forwarded count, filtered count, total count)
        """
        try:
            status = self.bot_manager.get_status()

            if status['is_running']:
                status_text = t("ui.status.running") if status['is_connected'] else t("ui.status.connecting")
            else:
                status_text = t("ui.status.stopped")

            stats = status.get('stats', {})
            forwarded = str(stats.get('forwarded', 0))
            filtered = str(stats.get('filtered', 0))
            total = str(stats.get('total', 0))

            return status_text, forwarded, filtered, total

        except Exception as e:
            logger.error(t("log.auth.get_failed", name=t("log.auth.status"), error=str(e)), exc_info=True)
            return t("ui.status.error"), "0", "0", "0"

    def get_auth_success_message(self) -> str:
        """Get authentication success message (if any)"""
        if self.config.session_type == "user" and self.bot_manager.auth_manager:
            user_info = self.bot_manager.get_and_clear_auth_success_user_info()
            if user_info:
                return user_info
        return ""
