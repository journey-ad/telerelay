"""In-process event fan-out used by the Server-Sent Events endpoint."""

import asyncio
import json
import logging
from collections import deque
from contextlib import suppress
from datetime import datetime, timezone
from itertools import count
from collections.abc import Callable
from typing import Any, AsyncIterator


class EventBus:
    def __init__(self, queue_size: int = 256, history_size: int = 1024):
        self.queue_size = queue_size
        self.loop: asyncio.AbstractEventLoop | None = None
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._history: deque[dict[str, Any]] = deque(maxlen=max(1, history_size))
        self._ids = count(1)

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop

    def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        event = {
            "id": next(self._ids),
            "type": event_type,
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "payload": payload,
        }
        if event_type != "log":
            self._history.append(event)
        for queue in tuple(self._subscribers):
            if queue.full():
                with suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
            with suppress(asyncio.QueueFull):
                queue.put_nowait(event)

    def publish_threadsafe(self, event_type: str, payload: dict[str, Any]) -> None:
        if self.loop and not self.loop.is_closed():
            self.loop.call_soon_threadsafe(self.publish, event_type, payload)

    def recent(
        self,
        limit: int = 10,
        event_types: set[str] | None = None,
        predicate: Callable[[dict[str, Any]], bool] | None = None,
    ) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        result = []
        for event in reversed(self._history):
            if event_types and event["type"] not in event_types:
                continue
            if predicate and not predicate(event):
                continue
            result.append(event)
            if len(result) >= limit:
                break
        return result

    async def stream(
        self,
        predicate: Callable[[dict[str, Any]], bool] | None = None,
    ) -> AsyncIterator[str]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(self.queue_size)
        self._subscribers.add(queue)
        try:
            yield "event: ready\ndata: {}\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=20)
                    if predicate and not predicate(event):
                        continue
                    data = json.dumps(event, ensure_ascii=False, default=str)
                    yield f"event: {event['type']}\ndata: {data}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            self._subscribers.discard(queue)


class EventLogHandler(logging.Handler):
    def __init__(self, bus: EventBus):
        super().__init__()
        self.bus = bus

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.bus.publish_threadsafe(
                "log",
                {
                    "level": record.levelname.lower(),
                    "message": self.format(record),
                    "logger": record.name,
                },
            )
        except Exception:
            self.handleError(record)
