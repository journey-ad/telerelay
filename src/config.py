"""
Configuration loading and validation module
Supports loading configuration from .env and config.yaml
"""
import os
import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv
from src.logger import get_logger
from src.rule import ForwardingRule, load_rules_from_config
from src.i18n import t

logger = get_logger()


class Config:
    """Configuration management class"""
    
    def __init__(self, env_file: str = ".env", config_file: str = "config/config.yaml"):
        """
        Initialize configuration

        Args:
            env_file: Path to environment variable file
            config_file: Path to YAML configuration file
        """
        self.env_file = env_file
        self.config_file = config_file
        self.config_data: Dict[str, Any] = {}

        # Load configuration
        self.load()
    
    def load(self) -> None:
        """Load all configuration"""
        # Load environment variables
        env_path = Path(self.env_file)
        if env_path.exists():
            load_dotenv(env_path)
            logger.info(t("log.config.env_loaded", path=env_path))
        else:
            logger.warning(t("log.config.env_not_found", path=env_path))

        # Load YAML configuration
        config_path = Path(self.config_file)
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                self.config_data = yaml.safe_load(f) or {}
            logger.info(t("log.config.yaml_loaded", path=config_path))
        else:
            logger.warning(t("log.config.yaml_not_found", path=config_path))
            self.config_data = {}
    
    def save(self) -> None:
        """Save configuration to YAML file"""
        config_path = Path(self.config_file)
        config_path.parent.mkdir(parents=True, exist_ok=True)

        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(self.config_data, f, allow_unicode=True, default_flow_style=False)

        logger.debug(t("log.config.saved", path=config_path))
    
    def update(self, new_config: Dict[str, Any]) -> None:
        """
        Update configuration

        Args:
            new_config: New configuration data
        """
        self.config_data.update(new_config)
        self.save()

    # Telegram API configuration
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
        """Session type: user or bot"""
        return os.getenv("SESSION_TYPE", "user")
    
    @property
    def proxy_url(self) -> Optional[str]:
        """Proxy URL (optional)"""
        return os.getenv("PROXY_URL") or None

    # Web service configuration
    @property
    def web_host(self) -> str:
        """Web service host"""
        return os.getenv("WEB_HOST", "0.0.0.0")
    
    @property
    def web_port(self) -> int:
        """Web service port"""
        return int(os.getenv("WEB_PORT", "8080"))
    
    @property
    def web_auth_username(self) -> str:
        """Web authentication username"""
        return os.getenv("WEB_AUTH_USERNAME", "")
    
    @property
    def web_auth_password(self) -> str:
        """Web authentication password"""
        return os.getenv("WEB_AUTH_PASSWORD", "")

    # Logging configuration
    @property
    def log_level(self) -> str:
        """Log level"""
        return os.getenv("LOG_LEVEL", "INFO")

    # Language configuration
    @property
    def language(self) -> str:
        """Interface language"""
        # Priority: config.yaml > environment variable > default Chinese
        config_lang = self.config_data.get("language")
        if config_lang:
            return config_lang
        return os.getenv("LANGUAGE", "zh_CN")

    def set_language(self, lang: str):
        """Set language and save to configuration file"""
        self.config_data["language"] = lang
        self.save()

    # Source and target configuration
    @property
    def source_chats(self) -> List[Any]:
        """Source group/channel list"""
        return self.config_data.get("source_chats", [])
    
    @property
    def target_chats(self) -> List[Any]:
        """Target group/channel list"""
        return self.config_data.get("target_chats", [])

    # Filter rules configuration
    @property
    def filter_regex_patterns(self) -> List[str]:
        """Regular expression filter rules"""
        filters = self.config_data.get("filters", {})
        return filters.get("regex_patterns", [])
    
    @property
    def filter_keywords(self) -> List[str]:
        """Keyword filter rules"""
        filters = self.config_data.get("filters", {})
        return filters.get("keywords", [])
    
    @property
    def filter_mode(self) -> str:
        """Filter mode: whitelist or blacklist"""
        filters = self.config_data.get("filters", {})
        return filters.get("mode", "whitelist")
    
    @property
    def filter_media_types(self) -> List[str]:
        """Allowed media types list (empty = all allowed)"""
        filters = self.config_data.get("filters", {})
        return filters.get("media_types", [])
    
    @property
    def filter_max_file_size(self) -> int:
        """Maximum file size (bytes), 0 = no limit"""
        filters = self.config_data.get("filters", {})
        return int(filters.get("max_file_size", 0))
    
    @property
    def filter_min_file_size(self) -> int:
        """Minimum file size (bytes)"""
        filters = self.config_data.get("filters", {})
        return int(filters.get("min_file_size", 0))

    # Ignore list configuration
    @property
    def ignored_user_ids(self) -> List[int]:
        """Ignored user ID list"""
        ignore = self.config_data.get("ignore", {})
        user_ids = ignore.get("user_ids", [])
        # Ensure conversion to integer list, filter out None values
        return [int(uid) for uid in user_ids if uid is not None]
    
    @property
    def ignored_keywords(self) -> List[str]:
        """Ignored keywords list"""
        ignore = self.config_data.get("ignore", {})
        return ignore.get("keywords", [])

    # Forwarding options configuration
    @property
    def preserve_format(self) -> bool:
        """Whether to preserve original format"""
        forwarding = self.config_data.get("forwarding", {})
        return forwarding.get("preserve_format", True)
    
    @property
    def add_source_info(self) -> bool:
        """Whether to add source information"""
        forwarding = self.config_data.get("forwarding", {})
        return forwarding.get("add_source_info", True)
    
    @property
    def forward_delay(self) -> float:
        """Forwarding delay (seconds)"""
        forwarding = self.config_data.get("forwarding", {})
        return float(forwarding.get("delay", 0.5))
    
    def get_forwarding_rules(self) -> List[ForwardingRule]:
        """Get forwarding rules list"""
        return load_rules_from_config(self.config_data)
    
    def get_enabled_rules(self) -> List[ForwardingRule]:
        """Get enabled rules"""
        return [r for r in self.get_forwarding_rules() if r.enabled]
    
    def validate(self) -> tuple[bool, str]:
        """Validate if configuration is complete"""
        # Validate API credentials
        if not self.api_id or not self.api_hash:
            return False, t("message.validation.api_missing")

        # If in bot mode, Bot Token is required
        if self.session_type == "bot" and not self.bot_token:
            return False, t("message.validation.bot_token_required")

        # Validate rules
        rules = self.get_enabled_rules()
        if not rules:
            return False, t("message.validation.no_rules")

        for rule in rules:
            if not rule.source_chats:
                return False, t("message.validation.no_source", rule=rule.name)
            if not rule.target_chats:
                return False, t("message.validation.no_target", rule=rule.name)

        return True, t("message.validation.passed")
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert configuration to dictionary

        Returns:
            Configuration dictionary
        """
        return {
            "api_id": self.api_id,
            "api_hash": "***" if self.api_hash else None,  # Hide sensitive information
            "bot_token": "***" if self.bot_token else None,
            "session_type": self.session_type,
            "web_host": self.web_host,
            "web_port": self.web_port,
            "log_level": self.log_level,
            "config": self.config_data
        }


# Factory function
def create_config(env_file: str = ".env", config_file: str = "config/config.yaml") -> Config:
    """
    Create configuration instance

    Args:
        env_file: Path to environment variable file
        config_file: Path to YAML configuration file

    Returns:
        Config object
    """
    return Config(env_file, config_file)
