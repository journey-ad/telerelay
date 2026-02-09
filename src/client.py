"""
Telegram 客户端管理模块
封装 Telethon 客户端，处理连接和会话管理
"""
import asyncio
from pathlib import Path
from typing import Optional, Callable
from urllib.parse import urlparse
from telethon import TelegramClient, events
from telethon.errors import (
    SessionPasswordNeededError,
    FloodWaitError,
    PhoneNumberInvalidError,
    PhoneCodeInvalidError,
    PasswordHashInvalidError
)
from telethon.tl.types import User
from src.config import Config
from src.logger import get_logger

logger = get_logger()


class TelegramClientManager:
    """Telegram 客户端管理器"""

    def __init__(self, config: Config, auth_manager: Optional['AuthManager'] = None):
        """
        初始化客户端管理器

        参数:
            config: 配置对象
            auth_manager: 认证管理器（用于 User 模式认证）
        """
        self.config = config
        self.auth_manager = auth_manager
        self.client: Optional[TelegramClient] = None
        self.is_connected = False

        # 确保会话目录存在
        session_dir = Path("sessions")
        session_dir.mkdir(exist_ok=True)

        # 会话文件路径
        self.session_name = session_dir / "telegram_session"
    
    def _parse_proxy(self) -> Optional[tuple]:
        """
        解析代理配置
        
        返回:
            (proxy_type, proxy_host, proxy_port) 或 None
        """
        if not self.config.proxy_url:
            return None
        
        try:
            parsed = urlparse(self.config.proxy_url)
            proxy_type = parsed.scheme.lower()
            
            if proxy_type not in ['socks5', 'http', 'socks4']:
                logger.warning(f"不支持的代理类型: {proxy_type}")
                return None
            
            # 转换为 Telethon 支持的代理类型
            if proxy_type == 'socks5':
                import python_socks
                proxy_type = python_socks.ProxyType.SOCKS5
            elif proxy_type == 'socks4':
                import python_socks
                proxy_type = python_socks.ProxyType.SOCKS4
            elif proxy_type == 'http':
                import python_socks
                proxy_type = python_socks.ProxyType.HTTP
            
            proxy_host = parsed.hostname
            proxy_port = parsed.port or 1080
            
            # 如果有用户名和密码
            proxy_username = parsed.username
            proxy_password = parsed.password
            
            logger.info(f"使用代理: {proxy_type} {proxy_host}:{proxy_port}")
            
            return (proxy_type, proxy_host, proxy_port, True, proxy_username, proxy_password)
        
        except Exception as e:
            logger.error(f"解析代理配置失败: {e}")
            return None
    
    async def connect(self) -> bool:
        """
        连接到 Telegram
        
        返回:
            是否成功连接
        """
        try:
            # 解析代理配置
            proxy = self._parse_proxy()
            
            # 创建客户端
            if self.config.session_type == "bot":
                # Bot 模式
                if not self.config.bot_token:
                    logger.error("Bot 模式需要 BOT_TOKEN")
                    return False
                
                self.client = TelegramClient(
                    str(self.session_name),
                    self.config.api_id,
                    self.config.api_hash,
                    proxy=proxy
                )
                
                await self.client.start(bot_token=self.config.bot_token)
                logger.info("已使用 Bot Token 连接到 Telegram")
            else:
                # 用户模式
                self.client = TelegramClient(
                    str(self.session_name),
                    self.config.api_id,
                    self.config.api_hash,
                    proxy=proxy
                )

                # 检查是否已有 session 文件
                from pathlib import Path
                session_file = Path(f"{self.session_name}.session")
                has_session = session_file.exists()

                try:
                    # 如果有 session，设置"正在连接"状态；否则会在回调中设置状态
                    if has_session:
                        self.auth_manager.set_state("connecting", "")
                        logger.info("检测到已有 session，尝试自动登录...")

                    # 使用回调方式进行认证
                    await self.client.start(
                        phone=self.auth_manager.phone_callback,
                        code_callback=self.auth_manager.code_callback,
                        password=self.auth_manager.password_callback
                    )

                    # 获取用户信息
                    me: User = await self.client.get_me()
                    logger.info(f"已登录到 Telegram - 用户: {me.first_name} (@{me.username})")

                    # 设置认证成功状态
                    self.auth_manager.set_state("success")

                except PhoneNumberInvalidError:
                    logger.error("手机号格式无效")
                    self.auth_manager.set_state("error", "手机号格式无效，请检查格式（如 +8613800138000）")
                    return False

                except PhoneCodeInvalidError:
                    logger.error("验证码错误")
                    self.auth_manager.set_state("error", "验证码错误，请重新开始认证")
                    return False

                except PasswordHashInvalidError:
                    logger.error("两步验证密码错误")
                    self.auth_manager.set_state("error", "两步验证密码错误，请重新开始认证")
                    return False

                except TimeoutError as e:
                    logger.error(f"认证超时: {e}")
                    self.auth_manager.set_state("error", str(e))
                    return False
            
            self.is_connected = True
            return True
            
        except Exception as e:
            logger.error(f"连接 Telegram 失败: {e}")
            return False
    
    async def disconnect(self) -> None:
        """断开连接"""
        if self.client:
            await self.client.disconnect()
            self.is_connected = False
            logger.info("已断开 Telegram 连接")
    
    def add_message_handler(
        self,
        callback: Callable,
        chats: list = None
    ) -> None:
        """
        添加消息处理器
        
        参数:
            callback: 消息处理回调函数
            chats: 要监听的聊天 ID 列表
        """
        if not self.client:
            logger.error("客户端未初始化")
            return
        
        # 注册新消息事件处理器
        @self.client.on(events.NewMessage(chats=chats))
        async def handler(event):
            try:
                await callback(event)
            except FloodWaitError as e:
                logger.warning(f"触发速率限制，需要等待 {e.seconds} 秒")
                await asyncio.sleep(e.seconds)
            except Exception as e:
                logger.error(f"处理消息时出错: {e}", exc_info=True)
        
        logger.info(f"已注册消息处理器 - 监听 {len(chats) if chats else '所有'} 个聊天")
    
    async def run_until_disconnected(self) -> None:
        """运行客户端直到断开连接"""
        if self.client:
            logger.info("Telegram 客户端开始运行...")
            await self.client.run_until_disconnected()
    
    def get_client(self) -> Optional[TelegramClient]:
        """
        获取 Telethon 客户端实例

        返回:
            TelegramClient 对象或 None
        """
        return self.client

    def clear_session(self) -> None:
        """清除 session 文件"""
        try:
            import os
            session_files = [
                f"{self.session_name}.session",
                f"{self.session_name}.session-journal"
            ]

            for session_file in session_files:
                if os.path.exists(session_file):
                    os.remove(session_file)
                    logger.info(f"已删除 session 文件: {session_file}")

            logger.info("Session 文件已清除")
        except Exception as e:
            logger.error(f"清除 session 文件失败: {e}", exc_info=True)
