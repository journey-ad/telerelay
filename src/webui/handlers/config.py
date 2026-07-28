"""
Configuration Handler - Multi-rule Management Support
"""
import re
from typing import List, Tuple

from src.button_actions import ButtonActionRule
from src.bot_manager import BotManager
from src.config import Config
from src.i18n import t
from src.logger import get_logger
from src.rule import ForwardingRule

from ..utils import format_message, parse_chat_list

logger = get_logger()


class ConfigHandler:
    """Configuration Handler - Multi-rule Management Support"""

    def __init__(self, config: Config, bot_manager: BotManager):
        self.config = config
        self.bot_manager = bot_manager

    def get_rule_names(self) -> List[str]:
        """Get list of all rule names"""
        rules = self.config.get_forwarding_rules()
        if not rules:
            return [t("ui.status.default_rule")]
        return [rule.name for rule in rules]

    def get_button_action_rule_names(self) -> List[str]:
        """Get names for the independent message-button rules."""
        rules = self.config.get_button_action_rules()
        if not rules:
            return [t("ui.status.default_button_action_rule")]
        return [rule.name for rule in rules]

    def load_button_action_rule(self, index: int = 0) -> dict:
        """Load one message-button rule into the UI."""
        rules = self.config.get_button_action_rules()
        if not rules:
            return self._default_button_action_rule_dict()
        if index >= len(rules):
            index = 0
        rule = rules[index]
        return {
            "enabled": rule.enabled,
            "source_chats": "\n".join(str(chat) for chat in rule.source_chats),
            "button_texts": "\n".join(rule.button_texts),
            "match_mode": rule.match_mode,
            "delay": rule.delay,
            "click_all_matches": rule.click_all_matches,
        }

    @staticmethod
    def _default_button_action_rule_dict() -> dict:
        return {
            "enabled": False,
            "source_chats": "",
            "button_texts": "",
            "match_mode": "exact",
            "delay": 0.0,
            "click_all_matches": False,
        }

    def load_rule(self, index: int = 0) -> dict:
        """Load rule at specified index to UI"""
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
                "hide_sender": rule.hide_sender,
                "delay": rule.delay,
                "enabled": rule.enabled,
            }
        except Exception as e:
            logger.error(t("message.config.load_failed", error=str(e)), exc_info=True)
            return self._default_rule_dict()

    def _default_rule_dict(self) -> dict:
        """Return default rule dictionary"""
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
            "hide_sender": False,
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
        hide_sender: bool,
        delay: float,
        enabled: bool = True,
    ) -> str:
        """Save rule at specified index"""
        try:
            # Parse input
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

            # Validate
            if not source_list:
                return format_message(t("message.config.source_required"), "error")
            if not target_list:
                return format_message(t("message.config.target_required"), "error")

            # Get existing rules, create default rule if empty
            rules = self.config.get_forwarding_rules()
            if not rules:
                # Create new rule when no rules exist
                rules = [ForwardingRule(name=t("ui.status.default_rule"), enabled=True)]

            if index >= len(rules):
                index = 0  # Fall back to first rule

            # Update rule
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
                    "hide_sender": hide_sender,
                    "delay": float(delay)
                }
            })

            # Save all rules
            all_rules = [r.to_dict() for r in rules]
            all_rules[index] = rule_dict
            self.config.update({"forwarding_rules": all_rules})

            return self._maybe_restart(t("message.config.rule_saved", rule=rule.name))

        except Exception as e:
            logger.error(t("message.config.save_failed", error=str(e)), exc_info=True)
            return format_message(t("message.config.save_failed", error=str(e)), "error")

    def save_button_action_rule(
        self,
        index: int,
        enabled: bool,
        source_chats: str,
        button_texts: str,
        match_mode: str,
        delay: float,
        click_all_matches: bool = False,
    ) -> str:
        """Save one independent message-button interaction rule."""
        try:
            source_list = parse_chat_list(source_chats)
            text_list = [line.strip() for line in button_texts.split("\n") if line.strip()]
            match_mode = (
                match_mode
                if match_mode in {"exact", "contains", "regex"}
                else "exact"
            )

            if enabled and self.config.session_type != "user":
                return format_message(t("message.config.button_action_user_mode"), "error")
            if enabled and not source_list:
                return format_message(t("message.config.button_action_source_required"), "error")
            if enabled and not text_list:
                return format_message(t("message.config.button_action_text_required"), "error")
            if match_mode == "regex":
                for pattern in text_list:
                    try:
                        re.compile(pattern)
                    except re.error as exc:
                        return format_message(
                            t(
                                "message.config.button_action_regex_invalid",
                                pattern=pattern,
                                error=str(exc),
                            ),
                            "error",
                        )

            rules = self.config.get_button_action_rules()
            if not rules:
                rules = [
                    ButtonActionRule(
                        name=t("ui.status.default_button_action_rule")
                    )
                ]
            if index >= len(rules):
                index = 0

            all_rules = [rule.to_dict() for rule in rules]
            all_rules[index].update(
                {
                    "enabled": enabled,
                    "source_chats": source_list,
                    "button_texts": text_list,
                    "match_mode": match_mode,
                    "delay": max(0.0, min(float(delay or 0.0), 30.0)),
                    "click_all_matches": bool(click_all_matches),
                }
            )
            self.config.update({"button_action_rules": all_rules})
            return self._maybe_restart_button_action(
                t("message.config.button_action_saved", rule=rules[index].name)
            )
        except Exception as e:
            logger.error(
                t("message.config.button_action_save_failed", error=str(e)),
                exc_info=True,
            )
            return format_message(
                t("message.config.button_action_save_failed", error=str(e)), "error"
            )

    def add_button_action_rule(self, name: str) -> Tuple[str, List[str], int]:
        """Add an independent message-button interaction rule."""
        try:
            rules = self.config.get_button_action_rules()
            name = name.strip() if name else ""
            if not name:
                name = t("misc.button_action_rule_name_template", count=len(rules) + 1)
            all_rules = [rule.to_dict() for rule in rules]
            all_rules.append(ButtonActionRule(name=name).to_dict())
            self.config.update({"button_action_rules": all_rules})
            return (
                format_message(t("message.config.button_action_added", name=name), "success"),
                self.get_button_action_rule_names(),
                len(all_rules) - 1,
            )
        except Exception as e:
            logger.error(t("message.config.button_action_add_failed", error=str(e)), exc_info=True)
            return (
                format_message(t("message.config.button_action_add_failed", error=str(e)), "error"),
                self.get_button_action_rule_names(),
                0,
            )

    def delete_button_action_rule(self, index: int) -> Tuple[str, List[str], int]:
        """Delete an independent message-button interaction rule."""
        try:
            rules = self.config.get_button_action_rules()
            if len(rules) <= 1:
                return (
                    format_message(t("message.config.button_action_delete_last"), "error"),
                    self.get_button_action_rule_names(),
                    0,
                )
            if index >= len(rules):
                return (
                    format_message(t("message.config.invalid_index"), "error"),
                    self.get_button_action_rule_names(),
                    0,
                )
            deleted_name = rules[index].name
            all_rules = [rule.to_dict() for i, rule in enumerate(rules) if i != index]
            self.config.update({"button_action_rules": all_rules})
            new_index = min(index, len(all_rules) - 1)
            return (
                format_message(
                    t("message.config.button_action_deleted", name=deleted_name),
                    "success",
                ),
                self.get_button_action_rule_names(),
                new_index,
            )
        except Exception as e:
            logger.error(t("message.config.button_action_delete_failed", error=str(e)), exc_info=True)
            return (
                format_message(t("message.config.button_action_delete_failed", error=str(e)), "error"),
                self.get_button_action_rule_names(),
                0,
            )

    def rename_button_action_rule(self, index: int, new_name: str) -> Tuple[str, List[str]]:
        """Rename an independent message-button interaction rule."""
        try:
            new_name = new_name.strip()
            if not new_name:
                return (
                    format_message(t("message.config.name_empty"), "error"),
                    self.get_button_action_rule_names(),
                )
            rules = self.config.get_button_action_rules()
            if index >= len(rules):
                return (
                    format_message(t("message.config.invalid_index"), "error"),
                    self.get_button_action_rule_names(),
                )
            old_name = rules[index].name
            all_rules = [rule.to_dict() for rule in rules]
            all_rules[index]["name"] = new_name
            self.config.update({"button_action_rules": all_rules})
            return (
                format_message(
                    t(
                        "message.config.button_action_renamed",
                        old_name=old_name,
                        new_name=new_name,
                    ),
                    "success",
                ),
                self.get_button_action_rule_names(),
            )
        except Exception as e:
            logger.error(t("message.config.button_action_rename_failed", error=str(e)), exc_info=True)
            return (
                format_message(t("message.config.button_action_rename_failed", error=str(e)), "error"),
                self.get_button_action_rule_names(),
            )

    def add_rule(self, name: str) -> Tuple[str, List[str], int]:
        """Add new rule, returns (message, rule name list, new rule index)"""
        try:
            if not name.strip():
                # Generate default name: Rule 1, Rule 2, ...
                rule_count = len(self.config.get_forwarding_rules()) + 1
                name = t("misc.rule_name_template", count=rule_count)
            else:
                name = name.strip()

            rules = self.config.get_forwarding_rules()
            new_rule = ForwardingRule(name=name, enabled=False)
            all_rules = [r.to_dict() for r in rules] + [new_rule.to_dict()]

            self.config.update({"forwarding_rules": all_rules})

            new_index = len(all_rules) - 1
            return (
                format_message(t("message.config.rule_added", name=name), "success"),
                self.get_rule_names(),
                new_index
            )
        except Exception as e:
            logger.error(t("message.config.add_failed", error=str(e)), exc_info=True)
            return format_message(t("message.config.add_failed", error=str(e)), "error"), self.get_rule_names(), 0

    def delete_rule(self, index: int) -> Tuple[str, List[str], int]:
        """Delete rule, returns (message, rule name list, new selected index)"""
        try:
            rules = self.config.get_forwarding_rules()
            if len(rules) <= 1:
                return format_message(t("message.config.delete_last_rule"), "error"), self.get_rule_names(), 0

            if index >= len(rules):
                return format_message(t("message.config.invalid_index"), "error"), self.get_rule_names(), 0

            deleted_name = rules[index].name
            all_rules = [r.to_dict() for i, r in enumerate(rules) if i != index]
            self.config.update({"forwarding_rules": all_rules})

            # Delete stats from DB
            from src.stats_db import get_stats_db
            get_stats_db().delete_rule(deleted_name)

            new_index = min(index, len(all_rules) - 1)
            return (
                format_message(t("message.config.rule_deleted", name=deleted_name), "success"),
                self.get_rule_names(),
                new_index
            )
        except Exception as e:
            logger.error(t("message.config.delete_failed", error=str(e)), exc_info=True)
            return format_message(t("message.config.delete_failed", error=str(e)), "error"), self.get_rule_names(), 0

    def rename_rule(self, index: int, new_name: str) -> Tuple[str, List[str]]:
        """Rename rule, returns (message, rule name list)"""
        try:
            new_name = new_name.strip()
            if not new_name:
                return format_message(t("message.config.name_empty"), "error"), self.get_rule_names()

            rules = self.config.get_forwarding_rules()
            if index >= len(rules):
                return format_message(t("message.config.invalid_index"), "error"), self.get_rule_names()

            old_name = rules[index].name
            all_rules = [r.to_dict() for r in rules]
            all_rules[index]["name"] = new_name
            self.config.update({"forwarding_rules": all_rules})

            # Rename in stats DB
            from src.stats_db import get_stats_db
            get_stats_db().rename_rule(old_name, new_name)

            return (
                format_message(t("message.config.rule_renamed", old_name=old_name, new_name=new_name), "success"),
                self.get_rule_names()
            )
        except Exception as e:
            logger.error(t("message.config.rename_failed", error=str(e)), exc_info=True)
            return format_message(t("message.config.rename_failed", error=str(e)), "error"), self.get_rule_names()

    def toggle_rule(self, index: int, enabled: bool) -> str:
        """Enable/disable rule"""
        try:
            rules = self.config.get_forwarding_rules()
            if index >= len(rules):
                return format_message(t("message.config.invalid_index"), "error")

            all_rules = [r.to_dict() for r in rules]
            all_rules[index]["enabled"] = enabled
            self.config.update({"forwarding_rules": all_rules})

            status = t("message.config.enabled") if enabled else t("message.config.disabled")
            return format_message(t("message.config.rule_toggled", rule=rules[index].name, status=status), "success")
        except Exception as e:
            logger.error(t("message.config.toggle_failed", error=str(e)), exc_info=True)
            return format_message(t("message.config.toggle_failed", error=str(e)), "error")

    def _maybe_restart(self, success_msg: str) -> str:
        """Restart if Bot is running"""
        if self.bot_manager.is_running:
            logger.debug(t("log.bot.restarting") + t("misc.config_updated"))
            if self.bot_manager.restart():
                return format_message(t("message.config.rule_saved_restarted", msg=success_msg), "success")
            else:
                return format_message(t("message.config.rule_saved_restart_failed", msg=success_msg), "success")
        return format_message(t("message.config.rule_saved_next_start", msg=success_msg), "success")

    def _maybe_restart_button_action(self, success_msg: str) -> str:
        """Restart the Telegram client so button listeners use the new rules."""
        if self.bot_manager.is_running:
            logger.debug(t("log.bot.restarting") + t("misc.config_updated"))
            if self.bot_manager.restart():
                return format_message(
                    t("message.config.button_action_saved_restarted", msg=success_msg),
                    "success",
                )
            return format_message(
                t("message.config.button_action_saved_restart_failed", msg=success_msg),
                "success",
            )
        return format_message(
            t("message.config.button_action_saved_next_start", msg=success_msg),
            "success",
        )

    # Compatible with old interface
    def load_config(self) -> dict:
        """Compatible with old interface: load first rule"""
        return self.load_rule(0)

    def save_config(self, *args, **kwargs) -> str:
        """Compatible with old interface: save first rule"""
        return self.save_rule(0, *args, **kwargs)
