from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from telethon import TelegramClient, events
from telethon.tl.custom.message import Message

from ..models import Route
from .bot_mirror_sender import BotMirrorSender
from .route_service import RouteService


@dataclass(slots=True)
class AlbumBucket:
    route: Route
    messages: dict[int, Message] = field(default_factory=dict)
    flush_task: asyncio.Task[None] | None = None


def _extract_topic_id(message: Message) -> int | None:
    reply_to = message.reply_to
    if reply_to is None:
        return None

    top_id = getattr(reply_to, "reply_to_top_id", None)
    if top_id:
        return int(top_id)

    # In forum chats Telethon may put the topic/root message id here,
    # including messages that are not explicit replies inside the topic.
    topic_id = getattr(reply_to, "reply_to_msg_id", None)
    if topic_id:
        return int(topic_id)

    return None


class TelethonForwarder:
    def __init__(
        self,
        client: TelegramClient,
        routes: RouteService,
        sender: BotMirrorSender,
    ) -> None:
        self._client = client
        self._routes = routes
        self._sender = sender
        self._logger = logging.getLogger("forwarder")

        self._album_lock = asyncio.Lock()
        self._album_buckets: dict[tuple[int, int], AlbumBucket] = {}

    def register(self) -> None:
        @self._client.on(events.NewMessage())
        async def on_new_message(event: events.NewMessage.Event) -> None:
            chat_id = event.chat_id
            if chat_id is None:
                return

            topic_id = _extract_topic_id(event.message)
            matched_routes = self._routes.match(chat_id, topic_id)
            if not matched_routes and topic_id is None and self._is_forum_chat(event):
                matched_routes = self._routes.match(chat_id, 1)
                if matched_routes:
                    topic_id = 1

            if not matched_routes:
                source_routes = self._routes.source_routes(chat_id)
                if source_routes:
                    expected_topics = [
                        route.source_thread_id if route.source_thread_id is not None else "все"
                        for route in source_routes
                    ]
                    self._logger.info(
                        "Сообщение из настроенного источника %s не подошло по ветке: получена=%s, ожидается=%s",
                        chat_id,
                        topic_id if topic_id is not None else "без темы",
                        expected_topics,
                    )
                    return

                self._logger.debug(
                    "Сообщение без подходящего маршрута: источник=%s тема=%s",
                    chat_id,
                    topic_id if topic_id is not None else "без темы",
                )
                return

            self._logger.info(
                "Получено сообщение из %s (тема: %s). Маршрутов: %s",
                chat_id,
                topic_id if topic_id is not None else "без темы",
                len(matched_routes),
            )

            for route in matched_routes:
                if event.message.grouped_id:
                    await self._queue_album_item(route, event.message)
                else:
                    await self._send_single_route(route, event.message)

    async def _send_single_route(self, route: Route, message: Message) -> None:
        try:
            await self._sender.send_single(
                message=message,
                dest_chat_id=route.dest_chat_id,
                dest_thread_id=route.dest_thread_id,
            )
            self._logger.info(
                "Отправлено ботом %s -> %s (тема: %s)",
                message.chat_id,
                route.dest_chat_id,
                route.dest_thread_id if route.dest_thread_id is not None else "без темы",
            )
        except Exception as exc:  # noqa: BLE001
            self._logger.error(
                "Ошибка отправки ботом в %s (тема: %s): %s",
                route.dest_chat_id,
                route.dest_thread_id if route.dest_thread_id is not None else "без темы",
                exc,
            )

    async def _queue_album_item(self, route: Route, message: Message) -> None:
        grouped_id = message.grouped_id
        if grouped_id is None:
            await self._send_single_route(route, message)
            return

        key = (route.id, int(grouped_id))
        async with self._album_lock:
            bucket = self._album_buckets.get(key)
            if bucket is None:
                bucket = AlbumBucket(route=route)
                self._album_buckets[key] = bucket

            bucket.messages[message.id] = message

            if bucket.flush_task and not bucket.flush_task.done():
                bucket.flush_task.cancel()

            bucket.flush_task = asyncio.create_task(
                self._flush_album_later(key),
                name=f"album-flush-{route.id}-{grouped_id}",
            )

    async def _flush_album_later(self, key: tuple[int, int]) -> None:
        try:
            await asyncio.sleep(0.9)
        except asyncio.CancelledError:
            return

        async with self._album_lock:
            bucket = self._album_buckets.pop(key, None)

        if bucket is None:
            return

        messages = sorted(bucket.messages.values(), key=lambda m: m.id)
        if not messages:
            return

        try:
            await self._sender.send_album(
                messages=messages,
                dest_chat_id=bucket.route.dest_chat_id,
                dest_thread_id=bucket.route.dest_thread_id,
            )
            self._logger.info(
                "Отправлен альбом ботом: %s шт, %s -> %s (тема: %s)",
                len(messages),
                messages[0].chat_id,
                bucket.route.dest_chat_id,
                bucket.route.dest_thread_id if bucket.route.dest_thread_id is not None else "без темы",
            )
        except Exception as exc:  # noqa: BLE001
            self._logger.error(
                "Ошибка отправки альбома ботом в %s (тема: %s): %s",
                bucket.route.dest_chat_id,
                bucket.route.dest_thread_id if bucket.route.dest_thread_id is not None else "без темы",
                exc,
            )

    @staticmethod
    def _is_forum_chat(event: events.NewMessage.Event) -> bool:
        chat = getattr(event, "chat", None)
        return bool(getattr(chat, "forum", False))
