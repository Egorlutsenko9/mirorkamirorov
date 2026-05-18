from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Literal

from aiogram import Bot
from aiogram.types import (
    BufferedInputFile,
    InputMediaAudio,
    InputMediaDocument,
    InputMediaPhoto,
    InputMediaVideo,
    MessageEntity,
)
from telethon import TelegramClient
from telethon.tl import types as tl_types
from telethon.tl.custom.message import Message

MediaKind = Literal["photo", "video", "document", "audio", "voice", "video_note", "text", "unknown"]


@dataclass(slots=True)
class TextPayload:
    text: str | None
    entities: list[MessageEntity] | None


class BotMirrorSender:
    def __init__(self, bot: Bot, client: TelegramClient) -> None:
        self._bot = bot
        self._client = client
        self._logger = logging.getLogger("bot_sender")

    async def send_single(
        self,
        message: Message,
        dest_chat_id: int,
        dest_thread_id: int | None,
    ) -> None:
        thread_kwargs = self._thread_kwargs(dest_thread_id)
        kind = self._detect_kind(message)
        payload = self._extract_text_payload(message)

        try:
            if kind == "text":
                text = payload.text or " "
                await self._bot.send_message(
                    chat_id=dest_chat_id,
                    text=text,
                    entities=payload.entities,
                    parse_mode=None,
                    **thread_kwargs,
                )
                return

            input_file = await self._download_media(message)
            if input_file is None:
                if payload.text:
                    await self._bot.send_message(
                        chat_id=dest_chat_id,
                        text=payload.text,
                        entities=payload.entities,
                        parse_mode=None,
                        **thread_kwargs,
                    )
                return

            if kind == "photo":
                await self._bot.send_photo(
                    chat_id=dest_chat_id,
                    photo=input_file,
                    caption=payload.text,
                    caption_entities=payload.entities,
                    parse_mode=None,
                    **thread_kwargs,
                )
            elif kind == "video":
                await self._bot.send_video(
                    chat_id=dest_chat_id,
                    video=input_file,
                    caption=payload.text,
                    caption_entities=payload.entities,
                    parse_mode=None,
                    **thread_kwargs,
                )
            elif kind == "audio":
                await self._bot.send_audio(
                    chat_id=dest_chat_id,
                    audio=input_file,
                    caption=payload.text,
                    caption_entities=payload.entities,
                    parse_mode=None,
                    **thread_kwargs,
                )
            elif kind == "voice":
                await self._bot.send_voice(
                    chat_id=dest_chat_id,
                    voice=input_file,
                    caption=payload.text,
                    caption_entities=payload.entities,
                    parse_mode=None,
                    **thread_kwargs,
                )
            elif kind == "video_note":
                await self._bot.send_video_note(
                    chat_id=dest_chat_id,
                    video_note=input_file,
                    **thread_kwargs,
                )
                if payload.text:
                    await self._bot.send_message(
                        chat_id=dest_chat_id,
                        text=payload.text,
                        entities=payload.entities,
                        parse_mode=None,
                        **thread_kwargs,
                    )
            else:
                await self._bot.send_document(
                    chat_id=dest_chat_id,
                    document=input_file,
                    caption=payload.text,
                    caption_entities=payload.entities,
                    parse_mode=None,
                    **thread_kwargs,
                )
        except Exception as exc:  # noqa: BLE001
            self._logger.error("Ошибка отправки от имени бота: %s", exc)
            raise

    async def send_album(
        self,
        messages: list[Message],
        dest_chat_id: int,
        dest_thread_id: int | None,
    ) -> None:
        if len(messages) < 2:
            await self.send_single(messages[0], dest_chat_id, dest_thread_id)
            return

        thread_kwargs = self._thread_kwargs(dest_thread_id)
        media_items: list[InputMediaPhoto | InputMediaVideo | InputMediaDocument | InputMediaAudio] = []

        prepared = await asyncio.gather(*(self._prepare_album_item(msg) for msg in messages))
        for item in prepared:
            if item is not None:
                media_items.append(item)

        if len(media_items) < 2:
            for message in messages:
                await self.send_single(message, dest_chat_id, dest_thread_id)
            return

        album_caption = self._extract_album_caption(messages)
        if album_caption.text:
            first_item = media_items[0]
            media_items[0] = first_item.model_copy(
                update={
                    "caption": album_caption.text,
                    "caption_entities": album_caption.entities,
                    "parse_mode": None,
                }
            )

        chunk_size = 10
        for i in range(0, len(media_items), chunk_size):
            chunk = media_items[i : i + chunk_size]
            if len(chunk) == 1:
                only = messages[min(i, len(messages) - 1)]
                await self.send_single(only, dest_chat_id, dest_thread_id)
                continue

            await self._bot.send_media_group(
                chat_id=dest_chat_id,
                media=chunk,
                **thread_kwargs,
            )

    async def _prepare_album_item(
        self,
        message: Message,
    ) -> InputMediaPhoto | InputMediaVideo | InputMediaDocument | InputMediaAudio | None:
        kind = self._detect_kind(message)
        if kind not in {"photo", "video", "document", "audio"}:
            return None

        input_file = await self._download_media(message)
        if input_file is None:
            return None

        # Подпись альбома задаем отдельно на первом элементе группы,
        # чтобы Telegram отобразил ее корректно для всего альбома.
        if kind == "photo":
            return InputMediaPhoto(media=input_file)
        if kind == "video":
            return InputMediaVideo(media=input_file)
        if kind == "audio":
            return InputMediaAudio(media=input_file)
        return InputMediaDocument(media=input_file)

    async def _download_media(self, message: Message) -> BufferedInputFile | None:
        data = await self._client.download_media(message, file=bytes)
        if not isinstance(data, (bytes, bytearray)):
            return None

        file_name = self._file_name(message)
        return BufferedInputFile(file=bytes(data), filename=file_name)

    @staticmethod
    def _detect_kind(message: Message) -> MediaKind:
        if message.photo:
            return "photo"
        if message.video:
            return "video"
        if message.audio:
            return "audio"
        if message.voice:
            return "voice"
        if message.video_note:
            return "video_note"
        if message.document:
            return "document"
        if message.message:
            return "text"
        return "unknown"

    def _extract_text_payload(self, message: Message) -> TextPayload:
        text = (message.raw_text or "")
        if not text:
            return TextPayload(text=None, entities=None)

        entities = self._convert_entities(getattr(message, "entities", None) or [])
        return TextPayload(text=text, entities=entities or None)

    def _extract_album_caption(self, messages: list[Message]) -> TextPayload:
        for message in messages:
            payload = self._extract_text_payload(message)
            if payload.text:
                return payload
        return TextPayload(text=None, entities=None)

    @staticmethod
    def _convert_entities(entities: list[object]) -> list[MessageEntity]:
        converted: list[MessageEntity] = []

        for entity in entities:
            kind = None
            extra: dict[str, object] = {}

            if isinstance(entity, tl_types.MessageEntityBold):
                kind = "bold"
            elif isinstance(entity, tl_types.MessageEntityItalic):
                kind = "italic"
            elif isinstance(entity, tl_types.MessageEntityUnderline):
                kind = "underline"
            elif isinstance(entity, tl_types.MessageEntityStrike):
                kind = "strikethrough"
            elif isinstance(entity, tl_types.MessageEntityCode):
                kind = "code"
            elif isinstance(entity, tl_types.MessageEntityPre):
                kind = "pre"
                language = getattr(entity, "language", None)
                if language:
                    extra["language"] = language
            elif isinstance(entity, tl_types.MessageEntitySpoiler):
                kind = "spoiler"
            elif isinstance(entity, tl_types.MessageEntityBlockquote):
                kind = "blockquote"
            elif isinstance(entity, tl_types.MessageEntityUrl):
                kind = "url"
            elif isinstance(entity, tl_types.MessageEntityTextUrl):
                kind = "text_link"
                url = getattr(entity, "url", None)
                if url:
                    extra["url"] = url
            elif isinstance(entity, tl_types.MessageEntityMention):
                kind = "mention"
            elif isinstance(entity, tl_types.MessageEntityHashtag):
                kind = "hashtag"
            elif isinstance(entity, tl_types.MessageEntityCashtag):
                kind = "cashtag"
            elif isinstance(entity, tl_types.MessageEntityBotCommand):
                kind = "bot_command"
            elif isinstance(entity, tl_types.MessageEntityEmail):
                kind = "email"
            elif isinstance(entity, tl_types.MessageEntityPhone):
                kind = "phone_number"
            elif isinstance(entity, tl_types.MessageEntityCustomEmoji):
                kind = "custom_emoji"
                custom_emoji_id = getattr(entity, "document_id", None)
                if custom_emoji_id is not None:
                    extra["custom_emoji_id"] = str(custom_emoji_id)

            if not kind:
                continue

            converted.append(
                MessageEntity(
                    type=kind,
                    offset=int(getattr(entity, "offset", 0)),
                    length=int(getattr(entity, "length", 0)),
                    **extra,
                )
            )

        return converted

    @staticmethod
    def _thread_kwargs(dest_thread_id: int | None) -> dict[str, int]:
        if dest_thread_id is None:
            return {}
        return {"message_thread_id": dest_thread_id}

    @staticmethod
    def _file_name(message: Message) -> str:
        file_obj = getattr(message, "file", None)
        if file_obj is not None:
            name = getattr(file_obj, "name", None)
            if name:
                return str(name)
            ext = getattr(file_obj, "ext", None)
            if ext:
                return f"media_{message.id}{ext}"

        return f"media_{message.id}.bin"
