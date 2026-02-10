"""
Forwarding rule data class
Defines data structure for multi-rule groups
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any
from src.i18n import t


@dataclass
class ForwardingRule:
    """Forwarding rule"""
    name: str
    enabled: bool = True

    # Source and target
    source_chats: List[Any] = field(default_factory=list)
    target_chats: List[Any] = field(default_factory=list)

    # Filter configuration
    filter_mode: str = "whitelist"
    filter_keywords: List[str] = field(default_factory=list)
    filter_regex_patterns: List[str] = field(default_factory=list)
    filter_media_types: List[str] = field(default_factory=list)
    filter_max_file_size: int = 0
    filter_min_file_size: int = 0

    # Ignore configuration
    ignored_user_ids: List[int] = field(default_factory=list)
    ignored_keywords: List[str] = field(default_factory=list)

    # Forwarding configuration
    preserve_format: bool = True
    add_source_info: bool = True
    delay: float = 0.5
    force_forward: bool = False
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ForwardingRule':
        """Create rule from dictionary"""
        filters = data.get("filters", {})
        ignore = data.get("ignore", {})
        forwarding = data.get("forwarding", {})
        
        return cls(
            name=data.get("name", t("ui.status.default_rule")),
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
        """Convert to dictionary format (for saving configuration)"""
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
    Load rule list from configuration data

    Supports new format (forwarding_rules) and old format (flat structure)
    """
    # New format: forwarding_rules list
    if "forwarding_rules" in config_data:
        return [ForwardingRule.from_dict(rule) for rule in config_data["forwarding_rules"]]

    # Old format: convert to single rule
    if config_data.get("source_chats"):
        return [ForwardingRule.from_dict({
            "name": t("ui.status.default_rule"),
            "enabled": True,
            "source_chats": config_data.get("source_chats", []),
            "target_chats": config_data.get("target_chats", []),
            "filters": config_data.get("filters", {}),
            "ignore": config_data.get("ignore", {}),
            "forwarding": config_data.get("forwarding", {}),
        })]
    
    return []


def save_rules_to_config(rules: List[ForwardingRule]) -> Dict[str, Any]:
    """Save rule list as configuration data"""
    return {
        "forwarding_rules": [rule.to_dict() for rule in rules]
    }
