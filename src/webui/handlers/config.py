"""
配置处理器 - 支持多规则管理
"""
from typing import List, Tuple
from src.bot_manager import BotManager
from src.config import Config
from src.rule import ForwardingRule
from src.logger import get_logger
from ..utils import parse_chat_list, format_message

logger = get_logger()


class ConfigHandler:
    """配置处理器 - 支持多规则管理"""

    def __init__(self, config: Config, bot_manager: BotManager):
        self.config = config
        self.bot_manager = bot_manager

    def get_rule_names(self) -> List[str]:
        """获取所有规则名称列表"""
        rules = self.config.get_forwarding_rules()
        if not rules:
            return ["默认规则"]
        return [rule.name for rule in rules]

    def load_rule(self, index: int = 0) -> dict:
        """加载指定索引的规则到 UI"""
        try:
            rules = self.config.get_forwarding_rules()
            if not rules:
                return self._default_rule_dict()
            
            if index >= len(rules):
                index = 0
            
            rule = rules[index]
            return {
                "source_chats": '\n'.join(str(chat) for chat in rule.source_chats),
                "target_chats": '\n'.join(str(chat) for chat in rule.target_chats),
                "regex_patterns": '\n'.join(rule.filter_regex_patterns),
                "keywords": '\n'.join(rule.filter_keywords),
                "filter_mode": rule.filter_mode,
                "media_types": rule.filter_media_types,
                "max_file_size": rule.filter_max_file_size / 1048576 if rule.filter_max_file_size else 0,
                "ignored_user_ids": '\n'.join(str(uid) for uid in rule.ignored_user_ids),
                "ignored_keywords": '\n'.join(rule.ignored_keywords),
                "preserve_format": rule.preserve_format,
                "add_source_info": rule.add_source_info,
                "force_forward": rule.force_forward,
                "delay": rule.delay,
                "enabled": rule.enabled,
            }
        except Exception as e:
            logger.error(f"加载规则失败: {e}", exc_info=True)
            return self._default_rule_dict()

    def _default_rule_dict(self) -> dict:
        """返回默认规则字典"""
        return {
            "source_chats": "",
            "target_chats": "",
            "regex_patterns": "",
            "keywords": "",
            "filter_mode": "whitelist",
            "media_types": [],
            "max_file_size": 0,
            "ignored_user_ids": "",
            "ignored_keywords": "",
            "preserve_format": True,
            "add_source_info": True,
            "force_forward": False,
            "delay": 0.5,
            "enabled": True,
        }

    def save_rule(
        self,
        index: int,
        source_chats: str,
        target_chats: str,
        regex_patterns: str,
        keywords: str,
        filter_mode: str,
        media_types: list,
        max_file_size: float,
        ignored_user_ids: str,
        ignored_keywords: str,
        preserve_format: bool,
        add_source_info: bool,
        force_forward: bool,
        delay: float,
        enabled: bool = True,
    ) -> str:
        """保存指定索引的规则"""
        try:
            # 解析输入
            source_list = parse_chat_list(source_chats)
            target_list = parse_chat_list(target_chats)
            regex_list = [line.strip() for line in regex_patterns.split('\n') if line.strip()]
            keyword_list = [line.strip() for line in keywords.split('\n') if line.strip()]

            ignored_user_id_list = []
            for line in ignored_user_ids.split('\n'):
                line = line.strip()
                if line and line.lstrip('-').isdigit():
                    ignored_user_id_list.append(int(line))

            ignored_keyword_list = [line.strip() for line in ignored_keywords.split('\n') if line.strip()]

            # 验证
            if not source_list:
                return format_message("请至少配置一个源群组/频道", "error")
            if not target_list:
                return format_message("请至少配置一个目标群组/频道", "error")

            # 获取现有规则，如果为空则创建默认规则
            rules = self.config.get_forwarding_rules()
            if not rules:
                # 没有规则时创建新规则
                rules = [ForwardingRule(name="默认规则", enabled=True)]
            
            if index >= len(rules):
                index = 0  # 回退到第一个规则

            # 更新规则
            rule = rules[index]
            rule_dict = rule.to_dict()
            rule_dict.update({
                "enabled": enabled,
                "source_chats": source_list,
                "target_chats": target_list,
                "filters": {
                    "regex_patterns": regex_list,
                    "keywords": keyword_list,
                    "mode": filter_mode,
                    "media_types": media_types or [],
                    "max_file_size": int(max_file_size * 1048576) if max_file_size else 0,
                },
                "ignore": {
                    "user_ids": ignored_user_id_list,
                    "keywords": ignored_keyword_list
                },
                "forwarding": {
                    "preserve_format": preserve_format,
                    "add_source_info": add_source_info,
                    "force_forward": force_forward,
                    "delay": float(delay)
                }
            })

            # 保存所有规则
            all_rules = [r.to_dict() for r in rules]
            all_rules[index] = rule_dict
            self.config.update({"forwarding_rules": all_rules})

            return self._maybe_restart(f"规则 '{rule.name}' 已保存")

        except Exception as e:
            logger.error(f"保存规则失败: {e}", exc_info=True)
            return format_message(f"保存失败: {str(e)}", "error")

    def add_rule(self, name: str) -> Tuple[str, List[str], int]:
        """添加新规则，返回 (消息, 规则名称列表, 新规则索引)"""
        try:
            name = name.strip() or f"规则 {len(self.config.get_forwarding_rules()) + 1}"
            
            rules = self.config.get_forwarding_rules()
            new_rule = ForwardingRule(name=name, enabled=True)
            all_rules = [r.to_dict() for r in rules] + [new_rule.to_dict()]
            
            self.config.update({"forwarding_rules": all_rules})
            
            new_index = len(all_rules) - 1
            return (
                format_message(f"已添加规则 '{name}'", "success"),
                self.get_rule_names(),
                new_index
            )
        except Exception as e:
            logger.error(f"添加规则失败: {e}", exc_info=True)
            return format_message(f"添加失败: {str(e)}", "error"), self.get_rule_names(), 0

    def delete_rule(self, index: int) -> Tuple[str, List[str], int]:
        """删除规则，返回 (消息, 规则名称列表, 新选中索引)"""
        try:
            rules = self.config.get_forwarding_rules()
            if len(rules) <= 1:
                return format_message("至少需要保留一个规则", "error"), self.get_rule_names(), 0
            
            if index >= len(rules):
                return format_message("规则索引无效", "error"), self.get_rule_names(), 0

            deleted_name = rules[index].name
            all_rules = [r.to_dict() for i, r in enumerate(rules) if i != index]
            self.config.update({"forwarding_rules": all_rules})

            new_index = min(index, len(all_rules) - 1)
            return (
                format_message(f"已删除规则 '{deleted_name}'", "success"),
                self.get_rule_names(),
                new_index
            )
        except Exception as e:
            logger.error(f"删除规则失败: {e}", exc_info=True)
            return format_message(f"删除失败: {str(e)}", "error"), self.get_rule_names(), 0

    def rename_rule(self, index: int, new_name: str) -> Tuple[str, List[str]]:
        """重命名规则，返回 (消息, 规则名称列表)"""
        try:
            new_name = new_name.strip()
            if not new_name:
                return format_message("规则名称不能为空", "error"), self.get_rule_names()

            rules = self.config.get_forwarding_rules()
            if index >= len(rules):
                return format_message("规则索引无效", "error"), self.get_rule_names()

            old_name = rules[index].name
            all_rules = [r.to_dict() for r in rules]
            all_rules[index]["name"] = new_name
            self.config.update({"forwarding_rules": all_rules})

            return (
                format_message(f"已将 '{old_name}' 重命名为 '{new_name}'", "success"),
                self.get_rule_names()
            )
        except Exception as e:
            logger.error(f"重命名规则失败: {e}", exc_info=True)
            return format_message(f"重命名失败: {str(e)}", "error"), self.get_rule_names()

    def toggle_rule(self, index: int, enabled: bool) -> str:
        """启用/禁用规则"""
        try:
            rules = self.config.get_forwarding_rules()
            if index >= len(rules):
                return format_message("规则索引无效", "error")

            all_rules = [r.to_dict() for r in rules]
            all_rules[index]["enabled"] = enabled
            self.config.update({"forwarding_rules": all_rules})

            status = "启用" if enabled else "禁用"
            return format_message(f"规则 '{rules[index].name}' 已{status}", "success")
        except Exception as e:
            logger.error(f"切换规则状态失败: {e}", exc_info=True)
            return format_message(f"操作失败: {str(e)}", "error")

    def _maybe_restart(self, success_msg: str) -> str:
        """如果 Bot 运行中则重启"""
        if self.bot_manager.is_running:
            logger.info("Bot 正在运行，将自动重启以应用新配置")
            if self.bot_manager.restart():
                return format_message(f"{success_msg}，已重启 Bot", "success")
            else:
                return format_message(f"{success_msg}，但重启失败", "success")
        return format_message(f"{success_msg}，下次启动时生效", "success")

    # 兼容旧接口
    def load_config(self) -> dict:
        """兼容旧接口：加载第一个规则"""
        return self.load_rule(0)

    def save_config(self, *args, **kwargs) -> str:
        """兼容旧接口：保存第一个规则"""
        return self.save_rule(0, *args, **kwargs)

