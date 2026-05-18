from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from telethon import TelegramClient

from .bot.handlers import AdminRouterUI
from .config import load_settings
from .db import Database
from .logging_setup import setup_logging
from .services.bot_mirror_sender import BotMirrorSender
from .services.route_service import RouteService
from .services.telethon_forwarder import TelethonForwarder
from .telethon_auth import ensure_authorized


async def run() -> None:
    settings = load_settings()
    setup_logging(settings.log_level)
    logger = logging.getLogger("main")

    db = Database(settings.db_path)
    await db.connect()
    await db.init_schema()

    route_service = RouteService(db)
    await route_service.force_destination_chat(settings.dest_chat_id)

    bot = Bot(token=settings.bot_token)
    dp = Dispatcher()

    ui = AdminRouterUI(
        bot=bot,
        admin_user_id=settings.admin_user_id,
        fixed_dest_chat_id=settings.dest_chat_id,
        db=db,
        route_service=route_service,
    )
    dp.include_router(ui.router)

    tg_client = TelegramClient(settings.tg_session, settings.tg_api_id, settings.tg_api_hash)
    await ensure_authorized(tg_client, settings.tg_phone)

    bot_sender = BotMirrorSender(bot=bot, client=tg_client)
    forwarder = TelethonForwarder(tg_client, route_service, bot_sender)
    forwarder.register()

    logger.info("Сервис запущен. Ожидание сообщений и команд.")
    logger.info("Чат назначения зафиксирован: %s", settings.dest_chat_id)

    polling_task = asyncio.create_task(
        dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types()),
        name="bot-polling",
    )
    telethon_task = asyncio.create_task(
        tg_client.run_until_disconnected(),
        name="telethon-listener",
    )

    try:
        done, pending = await asyncio.wait(
            {polling_task, telethon_task},
            return_when=asyncio.FIRST_EXCEPTION,
        )

        for task in done:
            exc = task.exception()
            if exc:
                raise exc

        for task in pending:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    finally:
        for task in (polling_task, telethon_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(polling_task, telethon_task, return_exceptions=True)

        await tg_client.disconnect()
        await bot.session.close()
        await db.close()
        logger.info("Сервис остановлен")


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("Остановка по Ctrl+C")
