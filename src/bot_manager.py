"""
Bot 生命周期管理模块
管理 Telegram Bot 的启动、停止和重启
"""
import asyncio
import threading
from typing import Optional
from src.config import Config
from src.client import TelegramClientManager
from src.filters import MessageFilter
from src.forwarder import MessageForwarder
from src.logger import get_logger
from src.constants import (
    BOT_STOP_TIMEOUT,
    BOT_RESTART_DELAY,
    BOT_MAIN_LOOP_INTERVAL,
    UI_UPDATE_DEBOUNCE
)

logger = get_logger()


class BotManager:
    """Bot 生命周期管理器"""

    def __init__(self, config: Config):
        """初始化 Bot 管理器"""
        self.config = config
        self.client_manager: Optional[TelegramClientManager] = None
        self.forwarder: Optional[MessageForwarder] = None
        self.thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        # 线程安全的状态管理
        self._lock = threading.RLock()
        self._is_running = False
        self._is_connected = False
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        # UI 更新标志
        self._ui_update_flag = threading.Event()
        self._last_update_time = 0.0

    @property
    def is_running(self) -> bool:
        """线程安全的is_running访问"""
        with self._lock:
            return self._is_running

    @is_running.setter
    def is_running(self, value: bool):
        """线程安全的is_running设置"""
        with self._lock:
            self._is_running = value

    @property
    def is_connected(self) -> bool:
        """线程安全的is_connected访问"""
        with self._lock:
            return self._is_connected

    @is_connected.setter
    def is_connected(self, value: bool):
        """线程安全的is_connected设置"""
        with self._lock:
            self._is_connected = value
    
    def start(self) -> bool:
        """
        启动 Bot
        
        返回:
            是否成功启动
        """
        if self.is_running:
            logger.warning("Bot 已在运行中")
            return False
        
        try:
            self._stop_event.clear()
            self.thread = threading.Thread(target=self._run_bot, daemon=True)
            self.thread.start()
            logger.info("Bot 启动线程已创建")
            # 触发 UI 更新显示启动状态
            self.trigger_ui_update()
            return True
        except Exception as e:
            logger.error(f"启动 Bot 失败: {e}")
            return False
    
    def _run_bot(self) -> None:
        """在独立线程中运行 Bot"""
        try:
            # 创建新的事件循环
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            
            # 运行 Bot
            self.loop.run_until_complete(self._bot_main())
            
        except Exception as e:
            logger.error(f"Bot 运行出错: {e}", exc_info=True)
        finally:
            if self.loop:
                self.loop.close()
            self.is_running = False
    
    async def _bot_main(self) -> None:
        """Bot 主逻辑"""
        try:
            # 验证配置
            is_valid, error_msg = self.config.validate()
            if not is_valid:
                logger.error(f"配置验证失败: {error_msg}")
                return

            # 初始化客户端
            self.client_manager = TelegramClientManager(self.config)

            # 连接
            if not await self.client_manager.connect():
                logger.error("无法连接到 Telegram")
                return

            # 初始化过滤器
            message_filter = MessageFilter(
                regex_patterns=self.config.filter_regex_patterns,
                keywords=self.config.filter_keywords,
                mode=self.config.filter_mode,
                ignored_user_ids=self.config.ignored_user_ids,
                ignored_keywords=self.config.ignored_keywords
            )

            # 初始化转发器
            self.forwarder = MessageForwarder(
                client=self.client_manager.get_client(),
                config=self.config,
                message_filter=message_filter,
                bot_manager=self  # 传递 self 以便触发 UI 更新
            )

            # 注册消息处理器
            self.client_manager.add_message_handler(
                callback=self.forwarder.handle_message,
                chats=self.config.source_chats
            )

            self.is_running = True
            logger.info("✓ Bot 已启动并开始监听消息")
            self.trigger_ui_update()
            
            # 运行直到收到停止信号
            while not self._stop_event.is_set():
                await asyncio.sleep(BOT_MAIN_LOOP_INTERVAL)
            
            # 断开连接
            await self.client_manager.disconnect()
            logger.info("Bot 已停止")
            
        except Exception as e:
            logger.error(f"Bot 主逻辑出错: {e}", exc_info=True)
        finally:
            self.is_running = False
    
    def trigger_ui_update(self):
        """触发 UI 更新（由 forwarder 在转发后调用）"""
        import time
        with self._lock:
            current_time = time.time()
            # 防抖：1秒内只触发一次
            if current_time - self._last_update_time >= UI_UPDATE_DEBOUNCE:
                self._ui_update_flag.set()
                self._last_update_time = current_time
    
    def check_and_clear_ui_update(self) -> bool:
        """检查是否需要更新UI，并清除标志"""
        if self._ui_update_flag.is_set():
            self._ui_update_flag.clear()
            return True
        return False
    
    def stop(self) -> bool:
        """
        停止 Bot
        
        返回:
            是否成功停止
        """
        if not self.is_running:
            logger.warning("Bot 未在运行")
            return False
        
        try:
            logger.info("正在停止 Bot...")
            self._stop_event.set()
            
            # 等待线程结束（最多10秒）
            if self.thread:
                self.thread.join(timeout=BOT_STOP_TIMEOUT)
            
            self.is_running = False
            logger.info("✓ Bot 已停止")
            # 触发 UI 更新显示停止状态
            self.trigger_ui_update()
            return True
            
        except Exception as e:
            logger.error(f"停止 Bot 失败: {e}")
            return False
    
    def restart(self) -> bool:
        """
        重启 Bot
        
        返回:
            是否成功重启
        """
        logger.info("正在重启 Bot...")
        
        if self.is_running:
            if not self.stop():
                logger.error("无法停止 Bot，重启失败")
                return False
            
            # 等待完全停止
            import time
            time.sleep(BOT_RESTART_DELAY)
        
        return self.start()
    
    def get_status(self) -> dict:
        """
        获取 Bot 状态

        返回:
            状态信息字典
        """
        with self._lock:
            stats = {}
            if self.forwarder:
                stats = self.forwarder.get_stats()

            return {
                "is_running": self._is_running,
                "is_connected": self.client_manager.is_connected if self.client_manager else False,
                "stats": stats
            }
