from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(slots=True)
class Settings:
    bot_token: str
    admin_user_id: int
    tg_api_id: int
    tg_api_hash: str
    tg_phone: str | None
    tg_session: str
    dest_chat_id: int
    db_path: Path
    log_level: str



def load_settings() -> Settings:
    load_dotenv()

    bot_token = os.getenv("BOT_TOKEN", "").strip()
    admin_user_id = int(os.getenv("ADMIN_USER_ID", "0"))
    tg_api_id = int(os.getenv("TG_API_ID", "0"))
    tg_api_hash = os.getenv("TG_API_HASH", "").strip()
    raw_phone = os.getenv("TG_PHONE", "").strip()
    tg_phone = raw_phone or None
    tg_session = os.getenv("TG_SESSION", "telethon_user")
    dest_chat_id = int(os.getenv("DEST_CHAT_ID", "-1003714740567"))
    db_path = Path(os.getenv("DB_PATH", "./data/routes.db"))
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    missing = []
    if not bot_token:
        missing.append("BOT_TOKEN")
    if admin_user_id == 0:
        missing.append("ADMIN_USER_ID")
    if tg_api_id == 0:
        missing.append("TG_API_ID")
    if not tg_api_hash:
        missing.append("TG_API_HASH")
    if dest_chat_id == 0:
        missing.append("DEST_CHAT_ID")
    if missing:
        raise ValueError(
            "Не заполнены обязательные переменные окружения: " + ", ".join(missing)
        )

    return Settings(
        bot_token=bot_token,
        admin_user_id=admin_user_id,
        tg_api_id=tg_api_id,
        tg_api_hash=tg_api_hash,
        tg_phone=tg_phone,
        tg_session=tg_session,
        dest_chat_id=dest_chat_id,
        db_path=db_path,
        log_level=log_level,
    )
