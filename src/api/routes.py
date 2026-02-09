"""
API 路由
定义所有 REST API 端点
"""
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pathlib import Path
from typing import List
from src.config import get_config, reload_config
from src.bot_manager import get_bot_manager
from src.api.models import (
    ConfigData,
    ConfigResponse,
    BotStatusResponse,
    MessageResponse,
    LogsResponse
)
from src.api.websocket import get_ws_manager
from src.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api")


# 配置管理端点
@router.get("/config", response_model=ConfigResponse)
async def get_current_config():
    """获取当前配置"""
    try:
        config = get_config()
        
        # 构建配置响应
        config_data = ConfigData(
            source_chats=config.source_chats,
            target_chat=config.target_chat,
            filters={
                "regex_patterns": config.filter_regex_patterns,
                "keywords": config.filter_keywords,
                "mode": config.filter_mode
            },
            forwarding={
                "preserve_format": config.preserve_format,
                "add_source_info": config.add_source_info,
                "delay": config.forward_delay
            }
        )
        
        return ConfigResponse(
            api_id=config.api_id,
            api_hash="***" if config.api_hash else None,
            bot_token="***" if config.bot_token else None,
            session_type=config.session_type,
            web_host=config.web_host,
            web_port=config.web_port,
            log_level=config.log_level,
            config=config_data
        )
    except Exception as e:
        logger.error(f"获取配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/config", response_model=MessageResponse)
async def update_config(config_data: ConfigData):
    """更新配置"""
    try:
        config = get_config()
        
        # 更新配置
        new_config = {
            "source_chats": config_data.source_chats,
            "target_chat": config_data.target_chat,
            "filters": {
                "regex_patterns": config_data.filters.regex_patterns,
                "keywords": config_data.filters.keywords,
                "mode": config_data.filters.mode
            },
            "forwarding": {
                "preserve_format": config_data.forwarding.preserve_format,
                "add_source_info": config_data.forwarding.add_source_info,
                "delay": config_data.forwarding.delay
            }
        }
        
        config.update(new_config)
        logger.info("配置已更新")
        
        return MessageResponse(
            success=True,
            message="配置已成功更新并保存"
        )
    except Exception as e:
        logger.error(f"更新配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Bot 控制端点
@router.post("/bot/start", response_model=MessageResponse)
async def start_bot():
    """启动 Bot"""
    try:
        bot_manager = get_bot_manager()
        
        if bot_manager.is_running:
            return MessageResponse(
                success=False,
                message="Bot 已在运行中"
            )
        
        # 验证配置
        config = get_config()
        is_valid, error_msg = config.validate()
        if not is_valid:
            return MessageResponse(
                success=False,
                message=f"配置验证失败: {error_msg}"
            )
        
        success = bot_manager.start()
        
        if success:
            logger.info("Bot 已通过 API 启动")
            return MessageResponse(
                success=True,
                message="Bot 已成功启动"
            )
        else:
            return MessageResponse(
                success=False,
                message="Bot 启动失败"
            )
    except Exception as e:
        logger.error(f"启动 Bot 失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bot/stop", response_model=MessageResponse)
async def stop_bot():
    """停止 Bot"""
    try:
        bot_manager = get_bot_manager()
        
        if not bot_manager.is_running:
            return MessageResponse(
                success=False,
                message="Bot 未在运行"
            )
        
        success = bot_manager.stop()
        
        if success:
            logger.info("Bot 已通过 API 停止")
            return MessageResponse(
                success=True,
                message="Bot 已成功停止"
            )
        else:
            return MessageResponse(
                success=False,
                message="Bot 停止失败"
            )
    except Exception as e:
        logger.error(f"停止 Bot 失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bot/restart", response_model=MessageResponse)
async def restart_bot():
    """重启 Bot"""
    try:
        # 重新加载配置
        reload_config()
        
        bot_manager = get_bot_manager()
        success = bot_manager.restart()
        
        if success:
            logger.info("Bot 已通过 API 重启")
            return MessageResponse(
                success=True,
                message="Bot 已成功重启"
            )
        else:
            return MessageResponse(
                success=False,
                message="Bot 重启失败"
            )
    except Exception as e:
        logger.error(f"重启 Bot 失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/bot/status", response_model=BotStatusResponse)
async def get_bot_status():
    """获取 Bot 状态"""
    try:
        bot_manager = get_bot_manager()
        status = bot_manager.get_status()
        
        return BotStatusResponse(
            is_running=status["is_running"],
            is_connected=status["is_connected"],
            stats=status["stats"]
        )
    except Exception as e:
        logger.error(f"获取 Bot 状态失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 日志端点
@router.get("/logs", response_model=LogsResponse)
async def get_logs(lines: int = 100):
    """
    获取最近的日志
    
    参数:
        lines: 返回的日志行数（默认100行）
    """
    try:
        log_dir = Path("logs")
        
        if not log_dir.exists():
            return LogsResponse(logs=[], total=0)
        
        # 获取最新的日志文件
        log_files = sorted(log_dir.glob("*.log"), key=lambda f: f.stat().st_mtime, reverse=True)
        
        if not log_files:
            return LogsResponse(logs=[], total=0)
        
        # 读取最新日志文件的最后 N 行
        log_file = log_files[0]
        with open(log_file, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()
            recent_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
            
        return LogsResponse(
            logs=[line.strip() for line in recent_lines],
            total=len(all_lines)
        )
    except Exception as e:
        logger.error(f"读取日志失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# WebSocket 端点
@router.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    """WebSocket 端点用于实时日志推送"""
    ws_manager = get_ws_manager()
    await ws_manager.connect(websocket)
    
    try:
        # 保持连接
        while True:
            # 等待客户端消息（用于保持连接）
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket 错误: {e}")
        ws_manager.disconnect(websocket)
