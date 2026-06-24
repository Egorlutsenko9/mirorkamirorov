from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from ..models import Route



def build_main_keyboard(routes: list[Route]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="➕ Добавить маршрут", callback_data="menu:add")],
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="menu:refresh")],
    ]

    for route in routes:
        state = "✅" if route.enabled else "❌"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{state} #{route.id}",
                    callback_data=f"route:toggle:{route.id}",
                ),
                InlineKeyboardButton(
                    text=f"ℹ️ #{route.id}",
                    callback_data=f"route:details:{route.id}",
                ),
                InlineKeyboardButton(
                    text=f"🗑 Удалить #{route.id}",
                    callback_data=f"route:delete:{route.id}",
                ),
            ]
        )

    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_details_keyboard(route_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:refresh")],
            [InlineKeyboardButton(text=f"🗑 Удалить #{route_id}", callback_data=f"route:delete:{route_id}")],
        ]
    )
