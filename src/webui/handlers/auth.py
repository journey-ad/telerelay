"""认证处理器"""
import gradio as gr
from typing import Tuple, Optional
from src.auth_manager import AuthManager
from src.bot_manager import BotManager
from src.logger import get_logger
from ..utils import format_message

logger = get_logger()

# 状态描述映射
STATE_DESCRIPTIONS = {
    "idle": "未开始认证",
    "connecting": "🔄 正在连接...",
    "waiting_phone": "⏳ 请输入手机号",
    "waiting_code": "⏳ 验证码已发送到您的 Telegram，请查收",
    "waiting_password": "⏳ 检测到两步验证，请输入密码",
    "success": "✅ 认证成功！",
    "error": "❌ 认证失败"
}


class AuthHandler:
    """认证处理器"""

    def __init__(self, auth_manager: AuthManager, bot_manager: BotManager):
        self.auth_manager = auth_manager
        self.bot_manager = bot_manager

    def get_auth_state(self) -> Tuple[str, dict, dict, dict, dict, dict, dict, dict]:
        """获取认证状态

        返回:
            (状态文本, phone_input可见性, submit_phone_btn可见性,
             code_input可见性, submit_code_btn可见性,
             password_input可见性, submit_password_btn可见性,
             error可见性)
        """
        try:
            state_info = self.auth_manager.get_state()
            state = state_info["state"]
            error = state_info["error"]

            # 状态文本
            status_text = STATE_DESCRIPTIONS.get(state, "未知状态")

            # 控制各输入组件的可见性
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
            logger.error(f"获取认证状态失败: {e}", exc_info=True)
            return (
                "❌ 状态异常",
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(visible=True, value=str(e))
            )

    def start_auth(self) -> str:
        """开始认证流程

        返回:
            操作结果消息
        """
        try:
            # 如果 bot 已在运行，检查认证状态
            if self.bot_manager.is_running:
                state_info = self.auth_manager.get_state()
                state = state_info["state"]

                # 如果正在认证过程中，提示用户
                if state in ["waiting_phone", "waiting_code", "waiting_password"]:
                    return format_message(f"认证正在进行中，{STATE_DESCRIPTIONS.get(state, '请按提示操作')}", "info")

                # 如果认证已成功
                if state == "success":
                    return format_message("认证已完成，Bot 正在运行中", "success")

                # 其他情况，提示无需重新认证
                return format_message("Bot 已在运行中", "info")

            # 重置认证状态
            self.auth_manager.reset()

            # 启动 Bot（会触发认证流程）
            success = self.bot_manager.start()

            if success:
                logger.info("认证流程已启动")
                return format_message("认证流程已启动，请按提示操作", "success")
            else:
                return format_message("启动认证流程失败", "error")

        except Exception as e:
            logger.error(f"启动认证失败: {e}", exc_info=True)
            return format_message(f"启动认证失败: {str(e)}", "error")

    def cancel_auth(self) -> str:
        """取消认证流程

        返回:
            操作结果消息
        """
        try:
            # 停止 Bot
            if self.bot_manager.is_running:
                self.bot_manager.stop()

            # 清除 session 文件
            from src.client import TelegramClientManager
            TelegramClientManager(self.bot_manager.config).clear_session()

            # 重置认证状态
            self.auth_manager.reset()

            logger.info("认证已取消，session 已清除")
            return format_message("认证已取消，session 已清除", "info")

        except Exception as e:
            logger.error(f"取消认证失败: {e}", exc_info=True)
            return format_message(f"取消认证失败: {str(e)}", "error")

    def submit_phone(self, phone: str) -> str:
        """提交手机号

        参数:
            phone: 手机号

        返回:
            操作结果消息
        """
        try:
            success = self.auth_manager.submit_phone(phone)
            if success:
                return format_message("手机号已提交，等待验证码...", "success")
            else:
                return format_message("提交手机号失败，请检查格式", "error")

        except Exception as e:
            logger.error(f"提交手机号失败: {e}", exc_info=True)
            return format_message(str(e), "error")

    def submit_code(self, code: str) -> str:
        """提交验证码

        参数:
            code: 验证码

        返回:
            操作结果消息
        """
        try:
            success = self.auth_manager.submit_code(code)
            if success:
                return format_message("验证码已提交，正在验证...", "success")
            else:
                return format_message("提交验证码失败", "error")

        except Exception as e:
            logger.error(f"提交验证码失败: {e}", exc_info=True)
            return format_message(str(e), "error")

    def submit_password(self, password: str) -> str:
        """提交两步验证密码

        参数:
            password: 密码

        返回:
            操作结果消息
        """
        try:
            success = self.auth_manager.submit_password(password)
            if success:
                return format_message("密码已提交，正在验证...", "success")
            else:
                return format_message("提交密码失败", "error")

        except Exception as e:
            logger.error(f"提交密码失败: {e}", exc_info=True)
            return format_message(str(e), "error")
