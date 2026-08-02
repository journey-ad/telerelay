"""UI-independent forwarding and button-rule management."""

import re

from backend.button_actions import ButtonActionRule
from backend.config import Config
from backend.rule import ForwardingRule
from backend.schemas import ButtonActionRulePayload, ForwardingRulePayload
from backend.stats_db import get_stats_db


class ServiceError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def validate_regex_patterns(patterns: list[str]) -> list[dict[str, str]]:
    errors = []
    for pattern in patterns:
        try:
            re.compile(pattern)
        except re.error as exc:
            errors.append({"pattern": pattern, "error": str(exc)})
    return errors


def _ensure_valid_regex(patterns: list[str]) -> None:
    errors = validate_regex_patterns(patterns)
    if errors:
        first = errors[0]
        raise ServiceError(
            "invalid_regex",
            f"Invalid regex {first['pattern']!r}: {first['error']}",
        )


class RuleService:
    def __init__(self, config: Config, bot_manager, stats_db=None, session_type: str = "user"):
        self.config = config
        self.bot_manager = bot_manager
        self.stats_db = stats_db or get_stats_db()
        self.session_type = session_type

    def list_rules(self) -> list[dict]:
        return [rule.to_dict() for rule in self.config.get_forwarding_rules()]

    def list_button_rules(self) -> list[dict]:
        return [rule.to_dict() for rule in self.config.get_button_action_rules()]

    async def create_rule(self, payload: ForwardingRulePayload) -> dict:
        rules = self.config.get_forwarding_rules()
        self._ensure_unique(payload.name, [rule.name for rule in rules])
        rule = self._forwarding_rule(payload)
        rules.append(rule)
        self._save_rules(rules)
        await self._reload_if_running()
        return rule.to_dict()

    async def update_rule(self, index: int, payload: ForwardingRulePayload) -> dict:
        rules = self.config.get_forwarding_rules()
        self._ensure_index(index, rules)
        old_name = rules[index].name
        self._ensure_unique(
            payload.name,
            [rule.name for position, rule in enumerate(rules) if position != index],
        )
        rule = self._forwarding_rule(payload)
        rules[index] = rule
        self._save_rules(rules)
        if old_name != rule.name:
            self.stats_db.rename_rule(old_name, rule.name)
        await self._reload_if_running()
        return rule.to_dict()

    async def set_rule_enabled(self, index: int, enabled: bool) -> dict:
        """Toggle one rule without requiring the caller to resubmit its full definition."""
        rules = self.config.get_forwarding_rules()
        self._ensure_index(index, rules)
        payload = ForwardingRulePayload.model_validate(
            {**rules[index].to_dict(), "enabled": enabled}
        )
        rules[index] = self._forwarding_rule(payload)
        self._save_rules(rules)
        await self._reload_if_running()
        return rules[index].to_dict()

    async def delete_rule(self, index: int) -> None:
        rules = self.config.get_forwarding_rules()
        self._ensure_index(index, rules)
        deleted = rules.pop(index)
        self._save_rules(rules)
        self.stats_db.delete_rule(deleted.name)
        await self._reload_if_running()

    async def create_button_rule(self, payload: ButtonActionRulePayload) -> dict:
        rules = self.config.get_button_action_rules()
        self._ensure_unique(payload.name, [rule.name for rule in rules])
        rule = self._button_rule(payload)
        rules.append(rule)
        self._save_button_rules(rules)
        await self._reload_if_running()
        return rule.to_dict()

    async def update_button_rule(
        self,
        index: int,
        payload: ButtonActionRulePayload,
    ) -> dict:
        rules = self.config.get_button_action_rules()
        self._ensure_index(index, rules)
        old_name = rules[index].name
        self._ensure_unique(
            payload.name,
            [rule.name for position, rule in enumerate(rules) if position != index],
        )
        rule = self._button_rule(payload)
        rules[index] = rule
        self._save_button_rules(rules)
        if old_name != rule.name:
            self.stats_db.rename_button_rule(old_name, rule.name)
        await self._reload_if_running()
        return rule.to_dict()

    async def delete_button_rule(self, index: int) -> None:
        rules = self.config.get_button_action_rules()
        self._ensure_index(index, rules)
        deleted = rules.pop(index)
        self._save_button_rules(rules)
        self.stats_db.delete_button_rule(deleted.name)
        await self._reload_if_running()

    def _forwarding_rule(self, payload: ForwardingRulePayload) -> ForwardingRule:
        if payload.enabled and not payload.source_chats:
            raise ServiceError("rule_source_required", "Enabled rules need a source chat")
        if payload.enabled and not payload.target_chats:
            raise ServiceError("rule_target_required", "Enabled rules need a target chat")
        _ensure_valid_regex(payload.filters.regex_patterns)
        return ForwardingRule.from_dict(payload.model_dump())

    def _button_rule(self, payload: ButtonActionRulePayload) -> ButtonActionRule:
        if payload.enabled and self.session_type != "user":
            raise ServiceError("user_mode_required", "Button rules require a user session")
        if payload.enabled and not payload.source_chats:
            raise ServiceError("button_source_required", "Enabled button rules need a source chat")
        if payload.enabled and not payload.button_texts:
            raise ServiceError("button_text_required", "Enabled button rules need button text")
        if payload.match_mode == "regex":
            _ensure_valid_regex(payload.button_texts)
        return ButtonActionRule.from_dict(payload.model_dump())

    def _save_rules(self, rules: list[ForwardingRule]) -> None:
        self.config.update({"forwarding_rules": [rule.to_dict() for rule in rules]})

    def _save_button_rules(self, rules: list[ButtonActionRule]) -> None:
        self.config.update({"button_action_rules": [rule.to_dict() for rule in rules]})

    async def _reload_if_running(self) -> None:
        if self.bot_manager.is_running:
            await self.bot_manager.reload_rules()

    @staticmethod
    def _ensure_index(index: int, values: list) -> None:
        if index < 0 or index >= len(values):
            raise ServiceError("not_found", "Rule does not exist")

    @staticmethod
    def _ensure_unique(name: str, existing_names: list[str]) -> None:
        if name.casefold() in {item.casefold() for item in existing_names}:
            raise ServiceError("duplicate_name", "Rule names must be unique")
