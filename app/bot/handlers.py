from __future__ import annotations

import logging
from dataclasses import dataclass

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from ..db import Database
from ..services.name_resolver import TelegramNameResolver
from ..services.route_service import RouteService
from .keyboards import build_main_keyboard


@dataclass(slots=True)
class PendingAddRoute:
    step: int = 1
    source_chat_id: int | None = None
    source_thread_id: int | None = None
    prompt_message_id: int | None = None


@dataclass(slots=True)
class UiSession:
    main_message_id: int | None = None
    pending: PendingAddRoute | None = None


class AdminRouterUI:
    def __init__(
        self,
        bot: Bot,
        admin_user_id: int,
        fixed_dest_chat_id: int,
        db: Database,
        route_service: RouteService,
        name_resolver: TelegramNameResolver,
    ) -> None:
        self._bot = bot
        self._admin_user_id = admin_user_id
        self._fixed_dest_chat_id = fixed_dest_chat_id
        self._db = db
        self._route_service = route_service
        self._name_resolver = name_resolver
        self._sessions: dict[int, UiSession] = {}
        self._logger = logging.getLogger("ui")

        self.router = Router()
        self.router.message.register(self.on_start, CommandStart())
        self.router.message.register(self.on_user_input, F.text)
        self.router.callback_query.register(self.on_callback)

    def _is_admin(self, user_id: int | None) -> bool:
        return user_id == self._admin_user_id

    async def on_start(self, message: Message) -> None:
        if not self._is_admin(message.from_user.id if message.from_user else None):
            return

        text = await self._build_main_text(notice="Панель управления обновлена")
        keyboard = build_main_keyboard(self._route_service.list_routes())
        sent = await message.answer(text, reply_markup=keyboard)

        session = self._sessions.setdefault(message.chat.id, UiSession())
        session.main_message_id = sent.message_id
        session.pending = None
        await self._db.set_main_message_id(message.chat.id, sent.message_id)

    async def on_callback(self, callback: CallbackQuery) -> None:
        if not self._is_admin(callback.from_user.id if callback.from_user else None):
            await callback.answer("Доступ запрещен", show_alert=True)
            return

        message = callback.message
        if message is None:
            await callback.answer()
            return

        chat_id = message.chat.id
        if not await self._is_current_main_message(chat_id, message.message_id):
            await callback.answer("Используйте /start для нового интерфейса", show_alert=True)
            return

        data = callback.data or ""
        await callback.answer()
        try:
            if data == "menu:add":
                await self._start_add_flow(chat_id)
            elif data == "menu:refresh":
                self._name_resolver.clear_cache()
                await self._render_main(chat_id, notice="Список маршрутов обновлен")
            elif data.startswith("route:toggle:"):
                route_id = int(data.split(":")[-1])
                enabled = await self._route_service.toggle_route(route_id)
                state = "включен" if enabled else "выключен"
                await self._render_main(chat_id, notice=f"Маршрут #{route_id} {state}")
            elif data.startswith("route:delete:"):
                route_id = int(data.split(":")[-1])
                await self._route_service.delete_route(route_id)
                await self._render_main(chat_id, notice=f"Маршрут #{route_id} удален")
        except Exception as exc:  # noqa: BLE001
            self._logger.error("Ошибка обработки callback: %s", exc)
            await self._render_main(chat_id, notice=f"Ошибка: {exc}")

    async def on_user_input(self, message: Message) -> None:
        if not self._is_admin(message.from_user.id if message.from_user else None):
            return

        session = self._sessions.get(message.chat.id)
        if session is None or session.pending is None:
            return

        pending = session.pending
        raw_text = (message.text or "").strip()
        await self._cleanup_temp_messages(message.chat.id, pending.prompt_message_id, message.message_id)

        if pending.step == 1:
            source_chat_id = self._parse_int(raw_text)
            if source_chat_id is None:
                await self._start_add_flow(message.chat.id, "Нужен числовой ID источника")
                return

            pending.source_chat_id = source_chat_id
            pending.step = 2
            pending.prompt_message_id = await self._ask_input(
                message.chat.id,
                "Введите ID ветки источника. Отправьте 0, если фильтр по ветке не нужен.",
            )
            return

        if pending.step == 2:
            is_valid, source_thread_id = self._parse_optional_int(raw_text)
            if not is_valid:
                pending.prompt_message_id = await self._ask_input(
                    message.chat.id,
                    "ID ветки должен быть числом или 0. Попробуйте еще раз.",
                )
                return

            pending.source_thread_id = source_thread_id
            pending.step = 3
            pending.prompt_message_id = await self._ask_input(
                message.chat.id,
                "Введите ID ветки назначения. Отправьте 0, если пересылка без ветки.",
            )
            return

        if pending.step == 3:
            is_valid, dest_thread_id = self._parse_optional_int(raw_text)
            if not is_valid:
                pending.prompt_message_id = await self._ask_input(
                    message.chat.id,
                    "ID ветки назначения должен быть числом или 0. Попробуйте еще раз.",
                )
                return

            route_id = await self._route_service.add_route(
                source_chat_id=pending.source_chat_id,
                source_thread_id=pending.source_thread_id,
                dest_chat_id=self._fixed_dest_chat_id,
                dest_thread_id=dest_thread_id,
            )
            session.pending = None
            await self._render_main(message.chat.id, notice=f"Маршрут #{route_id} добавлен")

    async def _start_add_flow(self, chat_id: int, notice: str | None = None) -> None:
        session = self._sessions.setdefault(chat_id, UiSession())
        pending = PendingAddRoute()
        session.pending = pending
        await self._render_main(chat_id, notice=notice or "Добавление нового маршрута")
        pending.prompt_message_id = await self._ask_input(
            chat_id,
            "Введите ID источника (канал/супергруппа), например -1001234567890.",
        )

    async def _ask_input(self, chat_id: int, text: str) -> int:
        msg = await self._bot.send_message(chat_id, text)
        return msg.message_id

    async def _cleanup_temp_messages(
        self,
        chat_id: int,
        prompt_message_id: int | None,
        user_message_id: int,
    ) -> None:
        if prompt_message_id is not None:
            try:
                await self._bot.delete_message(chat_id, prompt_message_id)
            except TelegramBadRequest:
                pass

        try:
            await self._bot.delete_message(chat_id, user_message_id)
        except TelegramBadRequest:
            pass

    async def _render_main(self, chat_id: int, notice: str | None = None) -> None:
        session = self._sessions.setdefault(chat_id, UiSession())
        main_message_id = session.main_message_id
        if main_message_id is None:
            main_message_id = await self._db.get_main_message_id(chat_id)
            session.main_message_id = main_message_id

        if main_message_id is None:
            return

        text = await self._build_main_text(notice=notice)
        keyboard = build_main_keyboard(self._route_service.list_routes())

        try:
            await self._bot.edit_message_text(
                chat_id=chat_id,
                message_id=main_message_id,
                text=text,
                reply_markup=keyboard,
            )
        except TelegramBadRequest as exc:
            if "message is not modified" not in str(exc).lower():
                raise

    async def _build_main_text(self, notice: str | None = None) -> str:
        routes = self._route_service.list_routes()
        dest_chat_name = await self._name_resolver.chat_name(self._fixed_dest_chat_id)

        lines = [
            "Управление пересылкой сообщений",
            "",
            f"Чат назначения (фикс): {dest_chat_name}",
            "",
            "Маршруты:",
        ]

        if not routes:
            lines.append("- Пока нет маршрутов")
        else:
            for route in routes:
                enabled = "✅" if route.enabled else "❌"
                source_name = await self._name_resolver.chat_name(route.source_chat_id)
                dest_name = await self._name_resolver.chat_name(route.dest_chat_id)
                source_topic = await self._name_resolver.topic_name(
                    route.source_chat_id,
                    route.source_thread_id,
                    none_label="все ветки",
                )
                dest_topic = await self._name_resolver.topic_name(
                    route.dest_chat_id,
                    route.dest_thread_id,
                    none_label="без ветки",
                )
                lines.append(f"- #{route.id} {enabled}")
                lines.append(f"  из: {source_name} / {source_topic}")
                lines.append(f"  в: {dest_name} / {dest_topic}")

        if notice:
            lines.extend(["", f"Статус: {notice}"])

        return "\n".join(lines)

    async def _is_current_main_message(self, chat_id: int, message_id: int) -> bool:
        session = self._sessions.setdefault(chat_id, UiSession())
        if session.main_message_id is None:
            session.main_message_id = await self._db.get_main_message_id(chat_id)
        return session.main_message_id == message_id

    @staticmethod
    def _parse_int(value: str) -> int | None:
        try:
            return int(value)
        except ValueError:
            return None

    @staticmethod
    def _parse_optional_int(value: str) -> tuple[bool, int | None]:
        stripped = value.strip().lower()
        if stripped in {"", "0", "-", "none", "нет"}:
            return True, None
        try:
            return True, int(stripped)
        except ValueError:
            return False, None
