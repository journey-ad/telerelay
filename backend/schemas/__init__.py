"""Pydantic request and response contracts for the HTTP API."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


ChatRef = int | str


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


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


class AuthValue(StrictModel):
    value: str = Field(min_length=1, max_length=512)


class TelegramAccountCreate(StrictModel):
    label: str = Field(min_length=1, max_length=100)

    @field_validator("label")
    @classmethod
    def clean_label(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Account label is required")
        return value


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
