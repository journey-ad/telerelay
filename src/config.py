"""
配置加载和验证模块
支持从 .env 和 config.yaml 加载配置
"""
import os
import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv
from src.logger import get_logger

logger = get_logger(__name__)


class Config:
    """配置管理类"""
    
    def __init__(self, env_file: str = ".env", config_file: str = "config/config.yaml"):
        """
        初始化配置
        
        参数:
            env_file: 环境变量文件路径
            config_file: YAML 配置文件路径
        """
        self.env_file = env_file
        self.config_file = config_file
        self.config_data: Dict[str, Any] = {}
        
        # 加载配置
        self.load()
    
    def load(self) -> None:
        """加载所有配置"""
        # 加载环境变量
        env_path = Path(self.env_file)
        if env_path.exists():
            load_dotenv(env_path)
            logger.info(f"已加载环境变量文件: {env_path}")
        else:
            logger.warning(f"环境变量文件不存在: {env_path}")
        
        # 加载 YAML 配置
        config_path = Path(self.config_file)
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                self.config_data = yaml.safe_load(f) or {}
            logger.info(f"已加载 YAML 配置文件: {config_path}")
        else:
            logger.warning(f"YAML 配置文件不存在: {config_path}")
            self.config_data = {}
    
    def save(self) -> None:
        """保存配置到 YAML 文件"""
        config_path = Path(self.config_file)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(self.config_data, f, allow_unicode=True, default_flow_style=False)
        
        logger.info(f"已保存配置到: {config_path}")
    
    def update(self, new_config: Dict[str, Any]) -> None:
        """
        更新配置
        
        参数:
            new_config: 新的配置数据
        """
        self.config_data.update(new_config)
        self.save()
        logger.info("配置已更新并保存")
    
    # Telegram API 配置
    @property
    def api_id(self) -> Optional[int]:
        """Telegram API ID"""
        api_id = os.getenv("API_ID")
        return int(api_id) if api_id else None
    
    @property
    def api_hash(self) -> Optional[str]:
        """Telegram API Hash"""
        return os.getenv("API_HASH")
    
    @property
    def bot_token(self) -> Optional[str]:
        """Telegram Bot Token"""
        return os.getenv("BOT_TOKEN")
    
    @property
    def session_type(self) -> str:
        """会话类型: user 或 bot"""
        return os.getenv("SESSION_TYPE", "user")
    
    # Web 服务配置
    @property
    def web_host(self) -> str:
        """Web 服务主机"""
        return os.getenv("WEB_HOST", "0.0.0.0")
    
    @property
    def web_port(self) -> int:
        """Web 服务端口"""
        return int(os.getenv("WEB_PORT", "8080"))
    
    # 日志配置
    @property
    def log_level(self) -> str:
        """日志级别"""
        return os.getenv("LOG_LEVEL", "INFO")
    
    # 源和目标配置
    @property
    def source_chats(self) -> List[Any]:
        """源群组/频道列表"""
        return self.config_data.get("source_chats", [])
    
    @property
    def target_chat(self) -> Optional[Any]:
        """目标群组/频道"""
        return self.config_data.get("target_chat")
    
    # 过滤规则配置
    @property
    def filter_regex_patterns(self) -> List[str]:
        """正则表达式过滤规则"""
        filters = self.config_data.get("filters", {})
        return filters.get("regex_patterns", [])
    
    @property
    def filter_keywords(self) -> List[str]:
        """关键词过滤规则"""
        filters = self.config_data.get("filters", {})
        return filters.get("keywords", [])
    
    @property
    def filter_mode(self) -> str:
        """过滤模式: whitelist 或 blacklist"""
        filters = self.config_data.get("filters", {})
        return filters.get("mode", "whitelist")
    
    # 转发选项配置
    @property
    def preserve_format(self) -> bool:
        """是否保留原始格式"""
        forwarding = self.config_data.get("forwarding", {})
        return forwarding.get("preserve_format", True)
    
    @property
    def add_source_info(self) -> bool:
        """是否添加来源信息"""
        forwarding = self.config_data.get("forwarding", {})
        return forwarding.get("add_source_info", True)
    
    @property
    def forward_delay(self) -> float:
        """转发延迟（秒）"""
        forwarding = self.config_data.get("forwarding", {})
        return float(forwarding.get("delay", 0.5))
    
    def validate(self) -> tuple[bool, str]:
        """
        验证配置是否完整
        
        返回:
            (是否有效, 错误信息)
        """
        # 验证 API 凭据
        if not self.api_id or not self.api_hash:
            return False, "缺少 API_ID 或 API_HASH 配置"
        
        # 如果是 bot 模式，需要 Bot Token
        if self.session_type == "bot" and not self.bot_token:
            return False, "Bot 模式需要配置 BOT_TOKEN"
        
        # 验证源群组
        if not self.source_chats:
            return False, "未配置源群组/频道"
        
        # 验证目标
        if not self.target_chat:
            return False, "未配置目标群组/频道"
        
        return True, "配置验证通过"
    
    def to_dict(self) -> Dict[str, Any]:
        """
        将配置转换为字典
        
        返回:
            配置字典
        """
        return {
            "api_id": self.api_id,
            "api_hash": "***" if self.api_hash else None,  # 隐藏敏感信息
            "bot_token": "***" if self.bot_token else None,
            "session_type": self.session_type,
            "web_host": self.web_host,
            "web_port": self.web_port,
            "log_level": self.log_level,
            "config": self.config_data
        }


# 全局配置实例
_config: Optional[Config] = None


def get_config() -> Config:
    """
    获取全局配置实例
    
    返回:
        Config 对象
    """
    global _config
    if _config is None:
        _config = Config()
    return _config


def reload_config() -> Config:
    """
    重新加载配置
    
    返回:
        新的 Config 对象
    """
    global _config
    _config = Config()
    return _config
