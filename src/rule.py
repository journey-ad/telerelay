"""
转发规则数据类
定义多规则组的数据结构
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class ForwardingRule:
    """转发规则"""
    name: str
    enabled: bool = True
    
    # 源和目标
    source_chats: List[Any] = field(default_factory=list)
    target_chats: List[Any] = field(default_factory=list)
    
    # 过滤配置
    filter_mode: str = "whitelist"
    filter_keywords: List[str] = field(default_factory=list)
    filter_regex_patterns: List[str] = field(default_factory=list)
    filter_media_types: List[str] = field(default_factory=list)
    filter_max_file_size: int = 0
    filter_min_file_size: int = 0
    
    # 忽略配置
    ignored_user_ids: List[int] = field(default_factory=list)
    ignored_keywords: List[str] = field(default_factory=list)
    
    # 转发配置
    preserve_format: bool = True
    add_source_info: bool = True
    delay: float = 0.5
    force_forward: bool = False
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ForwardingRule':
        """从字典创建规则"""
        filters = data.get("filters", {})
        ignore = data.get("ignore", {})
        forwarding = data.get("forwarding", {})
        
        return cls(
            name=data.get("name", "默认规则"),
            enabled=data.get("enabled", True),
            source_chats=data.get("source_chats", []),
            target_chats=data.get("target_chats", []),
            filter_mode=filters.get("mode", "whitelist"),
            filter_keywords=filters.get("keywords", []),
            filter_regex_patterns=filters.get("regex_patterns", []),
            filter_media_types=filters.get("media_types", []),
            filter_max_file_size=filters.get("max_file_size", 0),
            filter_min_file_size=filters.get("min_file_size", 0),
            ignored_user_ids=[int(uid) for uid in ignore.get("user_ids", []) if uid],
            ignored_keywords=ignore.get("keywords", []),
            preserve_format=forwarding.get("preserve_format", True),
            add_source_info=forwarding.get("add_source_info", True),
            delay=forwarding.get("delay", 0.5),
            force_forward=forwarding.get("force_forward", False),
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式（用于保存配置）"""
        return {
            "name": self.name,
            "enabled": self.enabled,
            "source_chats": self.source_chats,
            "target_chats": self.target_chats,
            "filters": {
                "mode": self.filter_mode,
                "keywords": self.filter_keywords,
                "regex_patterns": self.filter_regex_patterns,
                "media_types": self.filter_media_types,
                "max_file_size": self.filter_max_file_size,
                "min_file_size": self.filter_min_file_size,
            },
            "ignore": {
                "user_ids": self.ignored_user_ids,
                "keywords": self.ignored_keywords,
            },
            "forwarding": {
                "preserve_format": self.preserve_format,
                "add_source_info": self.add_source_info,
                "delay": self.delay,
                "force_forward": self.force_forward,
            },
        }


def load_rules_from_config(config_data: Dict[str, Any]) -> List[ForwardingRule]:
    """
    从配置数据加载规则列表
    
    支持新格式（forwarding_rules）和旧格式（扁平结构）
    """
    # 新格式：forwarding_rules 列表
    if "forwarding_rules" in config_data:
        return [ForwardingRule.from_dict(rule) for rule in config_data["forwarding_rules"]]
    
    # 旧格式：转换为单规则
    if config_data.get("source_chats"):
        return [ForwardingRule.from_dict({
            "name": "默认规则",
            "enabled": True,
            "source_chats": config_data.get("source_chats", []),
            "target_chats": config_data.get("target_chats", []),
            "filters": config_data.get("filters", {}),
            "ignore": config_data.get("ignore", {}),
            "forwarding": config_data.get("forwarding", {}),
        })]
    
    return []


def save_rules_to_config(rules: List[ForwardingRule]) -> Dict[str, Any]:
    """将规则列表保存为配置数据"""
    return {
        "forwarding_rules": [rule.to_dict() for rule in rules]
    }
