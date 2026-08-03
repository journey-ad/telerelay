"""Shared Telegram message-entity serialization for preview and forwarding history."""
from typing import Any

from telethon.tl import types

ENTITY_TYPES = {
    types.MessageEntityUrl: "url",
    types.MessageEntityTextUrl: "url",
    types.MessageEntityEmail: "email",
    types.MessageEntityPhone: "phone",
}


def serialize_entities(entities: Any) -> list[dict[str, Any]] | None:
    result = []
    for entity in entities or []:
        kind = ENTITY_TYPES.get(type(entity))
        if kind is None:
            continue
        result.append(
            {
                "type": kind,
                "offset": int(entity.offset),
                "length": int(entity.length),
                "url": getattr(entity, "url", None),
            }
        )
    return result or None
