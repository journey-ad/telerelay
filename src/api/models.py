"""
API 数据模型
定义 Pydantic 模型用于 API 请求和响应
"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class FilterConfig(BaseModel):
    """过滤规则配置"""
    regex_patterns: List[str] = Field(default_factory=list, description="正则表达式列表")
    keywords: List[str] = Field(default_factory=list, description="关键词列表")
    mode: str = Field(default="whitelist", description="过滤模式: whitelist 或 blacklist")


class ForwardingConfig(BaseModel):
    """转发选项配置"""
    preserve_format: bool = Field(default=True, description="是否保留原始格式")
    add_source_info: bool = Field(default=True, description="是否添加来源信息")
    delay: float = Field(default=0.5, description="转发延迟（秒）")


class ConfigData(BaseModel):
    """配置数据模型"""
    source_chats: List[Any] = Field(default_factory=list, description="源群组/频道列表")
    target_chats: List[Any] = Field(default_factory=list, description="目标群组/频道列表")
    filters: FilterConfig = Field(default_factory=FilterConfig, description="过滤规则")
    forwarding: ForwardingConfig = Field(default_factory=ForwardingConfig, description="转发选项")


class ConfigResponse(BaseModel):
    """配置响应模型"""
    api_id: Optional[int] = None
    api_hash: Optional[str] = None
    bot_token: Optional[str] = None
    session_type: str
    web_host: str
    web_port: int
    log_level: str
    config: ConfigData


class BotStatusResponse(BaseModel):
    """Bot 状态响应模型"""
    is_running: bool = Field(description="是否正在运行")
    is_connected: bool = Field(description="是否已连接")
    stats: Dict[str, int] = Field(default_factory=dict, description="统计信息")


class MessageResponse(BaseModel):
    """通用消息响应模型"""
    success: bool = Field(description="操作是否成功")
    message: str = Field(description="消息内容")
    data: Optional[Dict[str, Any]] = Field(default=None, description="附加数据")


class LogEntry(BaseModel):
    """日志条目模型"""
    timestamp: str = Field(description="时间戳")
    level: str = Field(description="日志级别")
    logger: str = Field(description="日志记录器名称")
    message: str = Field(description="日志消息")


class LogsResponse(BaseModel):
    """日志响应模型"""
    logs: List[str] = Field(description="日志行列表")
    total: int = Field(description="总日志行数")
