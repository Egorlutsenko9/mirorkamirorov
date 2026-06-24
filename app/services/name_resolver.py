from __future__ import annotations

import inspect
import logging

from telethon import TelegramClient, utils

try:
    from telethon.tl.functions.channels import GetForumTopicsByIDRequest
except ImportError:  # pragma: no cover - depends on Telethon version
    GetForumTopicsByIDRequest = None

try:
    from telethon.tl.functions.channels import GetForumTopicsRequest
except ImportError:  # pragma: no cover - depends on Telethon version
    GetForumTopicsRequest = None


class TelegramNameResolver:
    def __init__(self, client: TelegramClient) -> None:
        self._client = client
        self._logger = logging.getLogger("name_resolver")
        self._chat_cache: dict[int, str] = {}
        self._topic_cache: dict[tuple[int, int], str] = {}
        self._topic_list_cache: dict[int, dict[int, str]] = {}

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
            entity = await self._client.get_entity(chat_id)
            input_channel = utils.get_input_channel(entity)
            title = await self._resolve_topic_title(chat_id, input_channel, topic_id)
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

    async def _resolve_topic_title(
        self,
        chat_id: int,
        input_channel: object,
        topic_id: int,
    ) -> str | None:
        if GetForumTopicsByIDRequest is not None:
            result = await self._client(
                GetForumTopicsByIDRequest(channel=input_channel, topics=[topic_id])
            )
            topics = getattr(result, "topics", None) or []
            return getattr(topics[0], "title", None) if topics else None

        if GetForumTopicsRequest is None:
            raise RuntimeError("Telethon does not support forum topic requests")

        cached_topics = self._topic_list_cache.get(chat_id)
        if cached_topics is not None:
            return cached_topics.get(topic_id)

        result = await self._client(
            GetForumTopicsRequest(**self._forum_topics_kwargs(input_channel))
        )
        topics = getattr(result, "topics", None) or []
        self._topic_list_cache[chat_id] = {
            int(getattr(topic, "id")): str(getattr(topic, "title"))
            for topic in topics
            if getattr(topic, "id", None) is not None and getattr(topic, "title", None)
        }

        for topic in topics:
            if getattr(topic, "id", None) == topic_id:
                return getattr(topic, "title", None)

        return None

    @staticmethod
    def _forum_topics_kwargs(input_channel: object) -> dict[str, object]:
        signature = inspect.signature(GetForumTopicsRequest.__init__)
        supported = set(signature.parameters)
        values: dict[str, object] = {
            "channel": input_channel,
            "q": "",
            "offset_date": None,
            "offset_id": 0,
            "offset_topic": 0,
            "limit": 100,
        }
        return {key: value for key, value in values.items() if key in supported}

    def clear_cache(self) -> None:
        self._chat_cache.clear()
        self._topic_cache.clear()
        self._topic_list_cache.clear()
