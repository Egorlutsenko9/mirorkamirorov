from __future__ import annotations

from getpass import getpass

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError


def _prompt_phone() -> str:
    while True:
        phone = input("Введите номер телефона Telegram (в формате +380...): ").strip()
        if phone:
            return phone
        print("Номер не может быть пустым.")


async def ensure_authorized(client: TelegramClient, phone: str | None) -> None:
    await client.connect()
    if await client.is_user_authorized():
        return

    print("Требуется авторизация Telethon.")
    phone_to_use = phone or _prompt_phone()
    await client.send_code_request(phone_to_use)
    code = input("Введите код из Telegram: ").strip()

    try:
        await client.sign_in(phone=phone_to_use, code=code)
    except SessionPasswordNeededError:
        password = getpass("Введите пароль 2FA: ")
        await client.sign_in(password=password)
