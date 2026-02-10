"""Authentication Handler"""
import gradio as gr
from typing import Tuple, Optional
from src.auth_manager import AuthManager
from src.bot_manager import BotManager
from src.logger import get_logger
from src.i18n import t
from ..utils import format_message

logger = get_logger()

# State description mapping
STATE_DESCRIPTIONS = {
    "idle": t("ui.auth.idle"),
    "connecting": t("ui.auth.connecting"),
    "waiting_phone": t("ui.auth.waiting_phone"),
    "waiting_code": t("ui.auth.waiting_code"),
    "waiting_password": t("ui.auth.waiting_password"),
    "success": t("ui.auth.success"),
    "error": t("ui.auth.error")
}


class AuthHandler:
    """Authentication Handler"""

    def __init__(self, auth_manager: AuthManager, bot_manager: BotManager):
        self.auth_manager = auth_manager
        self.bot_manager = bot_manager

    def get_auth_state(self) -> Tuple[str, dict, dict, dict, dict, dict, dict, dict]:
        """Get authentication state

        Returns:
            (status text, phone_input visibility, submit_phone_btn visibility,
             code_input visibility, submit_code_btn visibility,
             password_input visibility, submit_password_btn visibility,
             error visibility)
        """
        try:
            state_info = self.auth_manager.get_state()
            state = state_info["state"]
            error = state_info["error"]
            user_info = state_info.get("user_info", "")

            # Status text
            status_text = STATE_DESCRIPTIONS.get(state, t("ui.auth.unknown"))

            # If authentication is successful and has user info, display user info
            if state == "success" and user_info:
                status_text = t("ui.auth.logged_in", user_info=user_info)

            # Control visibility of each input component
            phone_visible = (state == "waiting_phone")
            code_visible = (state == "waiting_code")
            password_visible = (state == "waiting_password")
            error_visible = (state == "error" and bool(error))

            return (
                status_text,
                gr.update(visible=phone_visible),
                gr.update(visible=phone_visible),
                gr.update(visible=code_visible),
                gr.update(visible=code_visible),
                gr.update(visible=password_visible),
                gr.update(visible=password_visible),
                gr.update(visible=error_visible, value=error if error_visible else "")
            )

        except Exception as e:
            logger.error(t("log.auth.get_failed", name=t("log.auth.auth_state"), error=str(e)), exc_info=True)
            return (
                t("ui.status.error"),
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(visible=True, value=str(e))
            )

    def start_auth(self) -> str:
        """Start authentication process

        Returns:
            Operation result message
        """
        try:
            # If bot is already running, check authentication status
            if self.bot_manager.is_running:
                state_info = self.auth_manager.get_state()
                state = state_info["state"]

                # If in authentication process, prompt user
                if state in ["waiting_phone", "waiting_code", "waiting_password"]:
                    return format_message(t("message.auth.in_progress", state=STATE_DESCRIPTIONS.get(state, "")), "info")

                # If authentication is already successful
                if state == "success":
                    return format_message(t("message.auth.completed"), "success")

                # In other cases, no need to re-authenticate
                return format_message(t("message.bot.already_running"), "info")

            # Reset authentication state
            self.auth_manager.reset()

            # Start Bot (will trigger authentication process)
            success = self.bot_manager.start()

            if success:
                logger.info(t("log.auth.submitted", name=t("log.auth.auth_flow")))
                return format_message(t("message.auth.started"), "success")
            else:
                return format_message(t("message.auth.start_failed"), "error")

        except Exception as e:
            logger.error(t("log.auth.get_failed", name=t("log.auth.start_auth"), error=str(e)), exc_info=True)
            return format_message(t("message.auth.start_failed") + f": {str(e)}", "error")

    def cancel_auth(self) -> str:
        """Cancel authentication process

        Returns:
            Operation result message
        """
        try:
            # Stop Bot
            if self.bot_manager.is_running:
                self.bot_manager.stop()

            # Clear session file
            from src.client import TelegramClientManager
            TelegramClientManager(self.bot_manager.config).clear_session()

            # Reset authentication state
            self.auth_manager.reset()

            logger.info(t("log.auth.reset") + t("misc.session_cleared"))
            return format_message(t("message.auth.cancelled"), "info")

        except Exception as e:
            logger.error(t("log.auth.get_failed", name=t("log.auth.cancel_auth"), error=str(e)), exc_info=True)
            return format_message(t("message.auth.cancel_failed", error=str(e)), "error")

    def submit_phone(self, phone: str) -> str:
        """Submit phone number

        Args:
            phone: Phone number

        Returns:
            Operation result message
        """
        try:
            success = self.auth_manager.submit_phone(phone)
            if success:
                return format_message(t("message.auth.phone_submitted"), "success")
            else:
                return format_message(t("message.auth.phone_invalid"), "error")

        except Exception as e:
            logger.error(t("log.auth.get_failed", name=t("log.auth.submit_phone"), error=str(e)), exc_info=True)
            return format_message(str(e), "error")

    def submit_code(self, code: str) -> str:
        """Submit verification code

        Args:
            code: Verification code

        Returns:
            Operation result message
        """
        try:
            success = self.auth_manager.submit_code(code)
            if success:
                return format_message(t("message.auth.code_submitted"), "success")
            else:
                return format_message(t("message.auth.code_failed"), "error")

        except Exception as e:
            logger.error(t("log.auth.get_failed", name=t("log.auth.submit_code"), error=str(e)), exc_info=True)
            return format_message(str(e), "error")

    def submit_password(self, password: str) -> str:
        """Submit two-step verification password

        Args:
            password: Password

        Returns:
            Operation result message
        """
        try:
            success = self.auth_manager.submit_password(password)
            if success:
                return format_message(t("message.auth.password_submitted"), "success")
            else:
                return format_message(t("message.auth.password_failed"), "error")

        except Exception as e:
            logger.error(t("log.auth.get_failed", name=t("log.auth.submit_password"), error=str(e)), exc_info=True)
            return format_message(str(e), "error")
