"""
WebSocket 模块
实时推送日志到前端
"""
import asyncio
import logging
from typing import Set
from fastapi import WebSocket
from datetime import datetime
from src.logger import get_logger

logger = get_logger(__name__)


class WebSocketManager:
    """WebSocket 连接管理器"""
    
    def __init__(self):
        """初始化管理器"""
        self.active_connections: Set[WebSocket] = set()
        self.log_handler: Optional['WebSocketLogHandler'] = None
    
    async def connect(self, websocket: WebSocket):
        """
        接受 WebSocket 连接
        
        参数:
            websocket: WebSocket 连接对象
        """
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"WebSocket 客户端已连接 - 当前连接数: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        """
        移除 WebSocket 连接
        
        参数:
            websocket: WebSocket 连接对象
        """
        self.active_connections.discard(websocket)
        logger.info(f"WebSocket 客户端已断开 - 当前连接数: {len(self.active_connections)}")
    
    async def broadcast(self, message: str):
        """
        广播消息到所有连接的客户端
        
        参数:
            message: 要广播的消息
        """
        disconnected = set()
        
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.warning(f"发送 WebSocket 消息失败: {e}")
                disconnected.add(connection)
        
        # 移除断开的连接
        for connection in disconnected:
            self.disconnect(connection)
    
    def setup_log_handler(self):
        """设置日志处理器，将日志推送到 WebSocket"""
        if self.log_handler is None:
            self.log_handler = WebSocketLogHandler(self)
            
            # 添加到根日志记录器
            root_logger = logging.getLogger()
            root_logger.addHandler(self.log_handler)
            
            logger.info("已设置 WebSocket 日志处理器")


class WebSocketLogHandler(logging.Handler):
    """自定义日志处理器，将日志推送到 WebSocket"""
    
    def __init__(self, ws_manager: WebSocketManager):
        """
        初始化日志处理器
        
        参数:
            ws_manager: WebSocket 管理器
        """
        super().__init__()
        self.ws_manager = ws_manager
        
        # 设置日志格式
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        self.setFormatter(formatter)
    
    def emit(self, record: logging.LogRecord):
        """
        发送日志记录
        
        参数:
            record: 日志记录
        """
        try:
            # 格式化日志消息
            log_message = self.format(record)
            
            # 异步广播日志
            if self.ws_manager.active_connections:
                asyncio.create_task(self.ws_manager.broadcast(log_message))
        except Exception:
            self.handleError(record)


# 全局 WebSocket 管理器实例
ws_manager = WebSocketManager()


def get_ws_manager() -> WebSocketManager:
    """
    获取全局 WebSocket 管理器实例
    
    返回:
        WebSocketManager 对象
    """
    return ws_manager
