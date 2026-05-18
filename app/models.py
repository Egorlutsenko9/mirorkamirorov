from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Route:
    id: int
    source_chat_id: int
    source_thread_id: int | None
    dest_chat_id: int
    dest_thread_id: int | None
    enabled: bool
