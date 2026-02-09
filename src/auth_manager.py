"""Telegram User 认证管理器"""
import queue
import threading
import asyncio
from typing import Optional
from src.logger import get_logger

logger = get_logger()


class AuthManager:
    """Telegram User 认证管理器

    负责管理 Telegram User 模式的认证流程，通过队列机制在
    WebUI 线程和 Bot 线程之间传递认证信息。
    """

    def __init__(self, input_timeout: int = 300):
        """初始化认证管理器

        参数:
            input_timeout: 用户输入超时时间（秒），默认 5 分钟
        """
        self._lock = threading.RLock()

        # 认证状态
        self._auth_state = "idle"
        self._error_message = ""

        # 当前登录用户信息
        self._user_info = ""

        # 用户输入队列（每个队列只能放一个值）
        self._phone_queue = queue.Queue(maxsize=1)
        self._code_queue = queue.Queue(maxsize=1)
        self._password_queue = queue.Queue(maxsize=1)

        # 超时配置
        self._input_timeout = input_timeout

        logger.info("AuthManager 已初始化")

    def get_state(self) -> dict:
        """获取当前认证状态

        返回:
            包含状态信息的字典
        """
        with self._lock:
            return {
                "state": self._auth_state,
                "error": self._error_message,
                "user_info": self._user_info
            }

    def set_state(self, state: str, error: str = "") -> None:
        """设置认证状态

        参数:
            state: 状态值
            error: 错误消息（可选）
        """
        with self._lock:
            self._auth_state = state
            self._error_message = error
            logger.debug(f"认证状态更新: {state} {f'({error})' if error else ''}")

    def set_user_info(self, user_info: str) -> None:
        """设置当前登录用户信息

        参数:
            user_info: 用户信息字符串
        """
        with self._lock:
            self._user_info = user_info
            logger.info(f"用户信息已保存: {user_info}")

    def _submit_to_queue(self, target_queue: queue.Queue, value: str, name: str) -> bool:
        """通用的提交到队列方法

        参数:
            target_queue: 目标队列
            value: 要提交的值
            name: 输入项名称（用于日志）

        返回:
            是否成功提交
        """
        try:
            target_queue.put_nowait(value)
            logger.info(f"{name}已提交")
            return True
        except queue.Full:
            logger.warning(f"{name}队列已满，请勿重复提交")
            return False

    def submit_phone(self, phone: str) -> bool:
        """提交手机号（WebUI 调用）"""
        phone = phone.strip()
        if not phone:
            self.set_state("error", "手机号不能为空")
            return False
        if not phone.startswith('+'):
            self.set_state("error", "手机号必须以 + 开头（如 +8613800138000）")
            return False
        if self._submit_to_queue(self._phone_queue, phone, "手机号"):
            logger.info(f"手机号: {phone[:5]}***")
            return True
        return False

    def submit_code(self, code: str) -> bool:
        """提交验证码（WebUI 调用）"""
        code = code.strip()
        if not code:
            self.set_state("error", "验证码不能为空")
            return False
        if not code.isdigit():
            self.set_state("error", "验证码应为纯数字")
            return False
        return self._submit_to_queue(self._code_queue, code, "验证码")

    def submit_password(self, password: str) -> bool:
        """提交两步验证密码（WebUI 调用）"""
        if not password:
            self.set_state("error", "密码不能为空")
            return False
        return self._submit_to_queue(self._password_queue, password, "密码")

    async def _wait_for_input(self, input_queue: queue.Queue, state: str, name: str) -> str:
        """通用的等待用户输入方法

        参数:
            input_queue: 要读取的队列
            state: 等待时的状态
            name: 输入项名称（用于日志）

        返回:
            用户输入

        异常:
            TimeoutError: 输入超时
        """
        logger.info(f"等待用户输入{name}...")
        self.set_state(state)

        try:
            loop = asyncio.get_event_loop()
            value = await loop.run_in_executor(
                None, input_queue.get, True, self._input_timeout
            )
            logger.info(f"收到{name}")
            return value
        except queue.Empty:
            error_msg = f"等待{name}输入超时（{self._input_timeout}秒）"
            logger.error(error_msg)
            self.set_state("error", error_msg)
            raise TimeoutError(error_msg)
        except Exception as e:
            logger.error(f"获取{name}失败: {e}")
            self.set_state("error", str(e))
            raise

    async def phone_callback(self) -> str:
        """手机号回调（Telethon 调用）"""
        value = await self._wait_for_input(self._phone_queue, "waiting_phone", "手机号")
        logger.info(f"手机号: {value[:5]}***")
        return value

    async def code_callback(self) -> str:
        """验证码回调（Telethon 调用）"""
        return await self._wait_for_input(self._code_queue, "waiting_code", "验证码")

    async def password_callback(self) -> str:
        """密码回调（Telethon 调用）"""
        return await self._wait_for_input(self._password_queue, "waiting_password", "密码")

    def reset(self) -> None:
        """重置认证状态和队列"""
        with self._lock:
            self._auth_state = "idle"
            self._error_message = ""
            self._user_info = ""

            # 清空所有队列
            while not self._phone_queue.empty():
                try:
                    self._phone_queue.get_nowait()
                except queue.Empty:
                    break

            while not self._code_queue.empty():
                try:
                    self._code_queue.get_nowait()
                except queue.Empty:
                    break

            while not self._password_queue.empty():
                try:
                    self._password_queue.get_nowait()
                except queue.Empty:
                    break

            logger.info("认证状态已重置")
