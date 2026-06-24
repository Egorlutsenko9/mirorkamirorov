from __future__ import annotations

import logging

from telethon import TelegramClient, utils

try:
    from telethon.tl.functions.channels import GetForumTopicsByIDRequest
except ImportError:  # pragma: no cover - depends on Telethon version
    GetForumTopicsByIDRequest = None


class TelegramNameResolver:
    def __init__(self, client: TelegramClient) -> None:
        self._client = client
        self._logger = logging.getLogger("name_resolver")
        self._chat_cache: dict[int, str] = {}
        self._topic_cache: dict[tuple[int, int], str] = {}

    async def chat_name(self, chat_id: int) -> str:
        cached = self._chat_cache.get(chat_id)
        if cached:
            return cached

        try:
            entity = await self._client.get_entity(chat_id)
            title = (
                getattr(entity, "title", None)
                or getattr(entity, "username", None)
                or getattr(entity, "first_name", None)
                or str(chat_id)
            )
            name = f"{title} ({chat_id})"
        except Exception as exc:  # noqa: BLE001
            self._logger.warning("Could not resolve chat name %s: %s", chat_id, exc)
            name = str(chat_id)

        self._chat_cache[chat_id] = name
        return name

    async def topic_name(
        self,
        chat_id: int,
        topic_id: int | None,
        *,
        none_label: str,
    ) -> str:
        if topic_id is None:
            return none_label

        key = (chat_id, topic_id)
        cached = self._topic_cache.get(key)
        if cached:
            return cached

        try:
            if GetForumTopicsByIDRequest is None:
                raise RuntimeError("Telethon does not support GetForumTopicsByIDRequest")

            entity = await self._client.get_entity(chat_id)
            input_channel = utils.get_input_channel(entity)
            result = await self._client(
                GetForumTopicsByIDRequest(channel=input_channel, topics=[topic_id])
            )
            topics = getattr(result, "topics", None) or []
            title = getattr(topics[0], "title", None) if topics else None
            name = f"{title} ({topic_id})" if title else f"topic {topic_id}"
        except Exception as exc:  # noqa: BLE001
            self._logger.warning(
                "Could not resolve topic name %s in chat %s: %s",
                topic_id,
                chat_id,
                exc,
            )
            name = f"topic {topic_id}"

        self._topic_cache[key] = name
        return name

    def clear_cache(self) -> None:
        self._chat_cache.clear()
        self._topic_cache.clear()
