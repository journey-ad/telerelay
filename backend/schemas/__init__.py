"""Pydantic request and response contracts for the HTTP API."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from backend.timezones import (
    TIMEZONE_NAMES,
    TIMEZONE_NAME_SET,
    TIMEZONE_OPTIONS,
    system_timezone,
    timezone_label,
)


ChatRef = int | str


def timezone_schema(schema: dict[str, Any]) -> None:
    schema.update(
        {
            "default": system_timezone(),
            "enum": list(TIMEZONE_NAMES),
            "x-enum-labels": [timezone_label(*option) for option in TIMEZONE_OPTIONS],
        }
    )


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConfigModel(BaseModel):
    """Known configuration fields with compatibility for legacy extensions."""

    model_config = ConfigDict(extra="allow", strict=True)


class ApiMessage(StrictModel):
    ok: bool = True
    code: str
    message: str = ""


class FilterConfig(StrictModel):
    mode: Literal["whitelist", "blacklist"] = "whitelist"
    keywords: list[str] = Field(default_factory=list)
    regex_patterns: list[str] = Field(default_factory=list)
    media_types: list[str] = Field(default_factory=list)
    max_file_size: int = Field(default=0, ge=0)
    min_file_size: int = Field(default=0, ge=0)


class IgnoreConfig(StrictModel):
    user_ids: list[int] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)


class ForwardingOptions(StrictModel):
    preserve_format: bool = True
    add_source_info: bool = True
    delay: float = Field(default=0.5, ge=0, le=3600)
    force_forward: bool = False
    hide_sender: bool = False
    hide_media_caption: bool = False
    deduplicate: bool = False
    deduplicate_window: int = Field(default=3600, ge=0, le=604800)


class ForwardingRulePayload(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    enabled: bool = True
    source_chats: list[ChatRef] = Field(default_factory=list)
    target_chats: list[ChatRef] = Field(default_factory=list)
    filters: FilterConfig = Field(default_factory=FilterConfig)
    ignore: IgnoreConfig = Field(default_factory=IgnoreConfig)
    forwarding: ForwardingOptions = Field(default_factory=ForwardingOptions)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Rule name is required")
        return value


class ButtonActionRulePayload(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    enabled: bool = False
    source_chats: list[ChatRef] = Field(default_factory=list)
    button_texts: list[str] = Field(default_factory=list)
    match_mode: Literal["exact", "contains", "regex"] = "exact"
    delay: float = Field(default=0, ge=0, le=30)
    click_all_matches: bool = False


class ConfigFilter(ConfigModel):
    mode: Literal["whitelist", "blacklist"] = "whitelist"
    keywords: list[str] = Field(
        default_factory=list, json_schema_extra={"x-item-control": "tags"}
    )
    regex_patterns: list[str] = Field(
        default_factory=list, json_schema_extra={"x-item-control": "regex"}
    )
    media_types: list[Literal[
        "text", "photo", "video", "document", "audio", "voice", "sticker", "animation", "webpage"
    ]] = Field(default_factory=list)
    max_file_size: int = Field(default=0, ge=0)
    min_file_size: int = Field(default=0, ge=0)


class ConfigIgnore(ConfigModel):
    user_ids: list[int] = Field(
        default_factory=list, json_schema_extra={"x-item-control": "integer-tags"}
    )
    keywords: list[str] = Field(
        default_factory=list, json_schema_extra={"x-item-control": "tags"}
    )


class ConfigForwarding(ConfigModel):
    preserve_format: bool = True
    add_source_info: bool = True
    delay: float = Field(default=0.5, ge=0, le=3600)
    force_forward: bool = False
    hide_sender: bool = False
    hide_media_caption: bool = False
    deduplicate: bool = False
    deduplicate_window: int = Field(default=3600, ge=0, le=604800)


class ConfigForwardingRule(ConfigModel):
    name: str = Field(default="", min_length=1, max_length=100)
    enabled: bool = True
    source_chats: list[ChatRef] = Field(
        default_factory=list, json_schema_extra={"x-item-control": "chat-ref"}
    )
    target_chats: list[ChatRef] = Field(
        default_factory=list, json_schema_extra={"x-item-control": "chat-ref"}
    )
    filters: ConfigFilter = Field(default_factory=ConfigFilter)
    ignore: ConfigIgnore = Field(default_factory=ConfigIgnore)
    forwarding: ConfigForwarding = Field(default_factory=ConfigForwarding)


class ConfigButtonActionRule(ConfigModel):
    name: str = Field(default="", min_length=1, max_length=100)
    enabled: bool = False
    source_chats: list[ChatRef] = Field(
        default_factory=list, json_schema_extra={"x-item-control": "chat-ref"}
    )
    button_texts: list[str] = Field(
        default_factory=list, json_schema_extra={"x-item-control": "tags"}
    )
    match_mode: Literal["exact", "contains", "regex"] = "exact"
    delay: float = Field(default=0, ge=0, le=30)
    click_all_matches: bool = False


class ConfigExport(ConfigModel):
    root_dir: str = Field(default="data/exports", json_schema_extra={"readOnly": True})
    message_db_dir: str = Field(default="data/db", json_schema_extra={"readOnly": True})
    timezone: str = Field(
        default_factory=system_timezone,
        json_schema_extra=timezone_schema,
    )
    concurrency: int = Field(default=2, ge=1, le=4)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        if value not in TIMEZONE_NAME_SET:
            raise ValueError("Unsupported timezone")
        return value


class ConfigForwardQueue(ConfigModel):
    db_path: str = Field(default="data/forward_queue.db", json_schema_extra={"readOnly": True})
    max_retries: int = Field(default=5, ge=1, le=100)
    retry_base_seconds: float = Field(default=5, ge=0.1, le=3600)
    flood_wait_buffer: float = Field(default=1, ge=0, le=60)
    poll_interval: float = Field(default=1, ge=0.05, le=60)
    media_group_settle_seconds: float = Field(default=1, ge=0.1, le=10)
    completed_retention_days: int = Field(default=7, ge=1, le=3650)


class ConfigDocument(ConfigModel):
    session_type: Literal["user", "bot"] = Field(
        default="user", json_schema_extra={"readOnly": True}
    )
    bot_commands_enabled: bool = Field(
        default=True,
        json_schema_extra={"x-visible-if": {"session_type": "bot"}},
    )
    filters: ConfigFilter = Field(default_factory=ConfigFilter)
    forwarding: ConfigForwarding = Field(default_factory=ConfigForwarding)
    forwarding_rules: list[ConfigForwardingRule] = Field(default_factory=list)
    button_action_rules: list[ConfigButtonActionRule] = Field(default_factory=list)
    ignore: ConfigIgnore = Field(default_factory=ConfigIgnore)
    language: Literal["zh_CN", "en_US"] = "zh_CN"
    source_chats: list[ChatRef] = Field(
        default_factory=list, json_schema_extra={"x-item-control": "chat-ref"}
    )
    target_chats: list[ChatRef] = Field(
        default_factory=list, json_schema_extra={"x-item-control": "chat-ref"}
    )
    export: ConfigExport = Field(default_factory=ConfigExport)
    forward_queue: ConfigForwardQueue = Field(default_factory=ConfigForwardQueue)


def config_json_schema() -> dict[str, Any]:
    """Return the schema consumed by the schema-driven configuration editor."""
    return ConfigDocument.model_json_schema()


def validate_config(config: dict[str, Any]) -> None:
    """Validate known fields while preserving unknown legacy fields."""
    ConfigDocument.model_validate(config)


def config_validation_message(error: ValidationError) -> str:
    """Format the first validation error for the API error contract."""
    detail = error.errors()[0]
    path = ".".join(str(part) for part in detail.get("loc", ())) or "config"
    return f"{path}: {detail.get('msg', 'Invalid value')}"


class AuthValue(StrictModel):
    value: str = Field(min_length=1, max_length=512)


class TelegramAccountCreate(StrictModel):
    label: str = Field(min_length=1, max_length=100)
    kind: Literal["user", "bot"] = "user"
    bot_token: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        validate_default=True,
    )

    @field_validator("label")
    @classmethod
    def clean_label(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Account label is required")
        return value

    @field_validator("bot_token")
    @classmethod
    def clean_bot_token(cls, value: str | None, info) -> str | None:
        if info.data.get("kind") == "bot" and not value:
            raise ValueError("Bot token is required")
        return value.strip() if value else None


class TelegramAccountUpdate(StrictModel):
    label: str = Field(min_length=1, max_length=100)

    @field_validator("label")
    @classmethod
    def clean_update_label(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Account label is required")
        return value


class BotTokenPayload(StrictModel):
    bot_token: str = Field(min_length=1, max_length=200)


class TelegramChatResponse(StrictModel):
    id: int
    title: str
    kind: Literal["bot", "private", "group", "supergroup", "channel"]
    username: str | None = None


class GroupExportRequest(StrictModel):
    formats: list[Literal["json", "csv", "html"]]
    subdirectory: str = "groups"


class MessageExportRequest(StrictModel):
    chat_id: int
    start_at: str | None = None
    end_at: str | None = None
    formats: list[Literal["json", "csv", "html", "sqlite"]]
    subdirectory: str = "messages"
    all_history: bool = False


class ExportTaskPayload(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    chat_id: int
    initial_start_at: str | None = None
    formats: list[Literal["json", "csv", "html", "sqlite"]]
    subdirectory: str = "scheduled"
    schedule_type: Literal["hourly", "daily", "weekly"] = "daily"
    minute: int = Field(default=0, ge=0, le=59)
    hour: int = Field(default=2, ge=0, le=23)
    weekday: int = Field(default=0, ge=0, le=6)
    timezone: str = "Asia/Shanghai"
    all_history: bool = False
    enabled: bool = True


class TogglePayload(StrictModel):
    enabled: bool


class RegexValidateRequest(StrictModel):
    patterns: list[str] = Field(default_factory=list, max_length=50)


class ConfigPayload(StrictModel):
    config: dict[str, Any]
