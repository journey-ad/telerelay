"""
FastAPI 应用
创建和配置 FastAPI 应用实例
"""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from src.api.routes import router
from src.api.websocket import get_ws_manager
from src.logger import get_logger

logger = get_logger(__name__)


def create_app() -> FastAPI:
    """
    创建并配置 FastAPI 应用
    
    返回:
        FastAPI 应用实例
    """
    app = FastAPI(
        title="Telegram 消息转发工具",
        description="自动监控 Telegram 群组并转发消息",
        version="1.0.0"
    )
    
    # 配置 CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # 生产环境应该限制具体域名
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # 注册 API 路由
    app.include_router(router)
    
    # 挂载静态文件目录
    static_dir = Path("static")
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
        logger.info(f"已挂载静态文件目录: {static_dir}")
    else:
        logger.warning(f"静态文件目录不存在: {static_dir}")
    
    # 设置 WebSocket 日志处理器
    ws_manager = get_ws_manager()
    ws_manager.setup_log_handler()
    
    logger.info("FastAPI 应用已创建")
    
    return app
