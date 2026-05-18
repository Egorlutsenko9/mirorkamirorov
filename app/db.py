from __future__ import annotations

from pathlib import Path

import aiosqlite

from .models import Route


class Database:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self._db_path)
        self._conn.row_factory = aiosqlite.Row

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def init_schema(self) -> None:
        conn = self._require_conn()
        await conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS routes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_chat_id INTEGER NOT NULL,
                source_thread_id INTEGER,
                dest_chat_id INTEGER NOT NULL,
                dest_thread_id INTEGER,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS ui_state (
                chat_id INTEGER PRIMARY KEY,
                main_message_id INTEGER NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        await conn.commit()

    async def list_routes(self) -> list[Route]:
        conn = self._require_conn()
        cursor = await conn.execute(
            """
            SELECT id, source_chat_id, source_thread_id, dest_chat_id, dest_thread_id, enabled
            FROM routes
            ORDER BY id ASC
            """
        )
        rows = await cursor.fetchall()
        return [
            Route(
                id=row["id"],
                source_chat_id=row["source_chat_id"],
                source_thread_id=row["source_thread_id"],
                dest_chat_id=row["dest_chat_id"],
                dest_thread_id=row["dest_thread_id"],
                enabled=bool(row["enabled"]),
            )
            for row in rows
        ]

    async def add_route(
        self,
        source_chat_id: int,
        source_thread_id: int | None,
        dest_chat_id: int,
        dest_thread_id: int | None,
    ) -> int:
        conn = self._require_conn()
        cursor = await conn.execute(
            """
            INSERT INTO routes (source_chat_id, source_thread_id, dest_chat_id, dest_thread_id, enabled)
            VALUES (?, ?, ?, ?, 1)
            """,
            (source_chat_id, source_thread_id, dest_chat_id, dest_thread_id),
        )
        await conn.commit()
        return int(cursor.lastrowid)

    async def toggle_route(self, route_id: int) -> bool:
        conn = self._require_conn()
        cursor = await conn.execute(
            "SELECT enabled FROM routes WHERE id = ?",
            (route_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            raise ValueError("Маршрут не найден")

        next_enabled = 0 if row["enabled"] else 1
        await conn.execute(
            "UPDATE routes SET enabled = ? WHERE id = ?",
            (next_enabled, route_id),
        )
        await conn.commit()
        return bool(next_enabled)

    async def delete_route(self, route_id: int) -> None:
        conn = self._require_conn()
        await conn.execute("DELETE FROM routes WHERE id = ?", (route_id,))
        await conn.commit()

    async def update_all_dest_chat(self, dest_chat_id: int) -> None:
        conn = self._require_conn()
        await conn.execute("UPDATE routes SET dest_chat_id = ?", (dest_chat_id,))
        await conn.commit()

    async def set_main_message_id(self, chat_id: int, message_id: int) -> None:
        conn = self._require_conn()
        await conn.execute(
            """
            INSERT INTO ui_state (chat_id, main_message_id, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(chat_id) DO UPDATE
            SET main_message_id = excluded.main_message_id,
                updated_at = CURRENT_TIMESTAMP
            """,
            (chat_id, message_id),
        )
        await conn.commit()

    async def get_main_message_id(self, chat_id: int) -> int | None:
        conn = self._require_conn()
        cursor = await conn.execute(
            "SELECT main_message_id FROM ui_state WHERE chat_id = ?",
            (chat_id,),
        )
        row = await cursor.fetchone()
        return int(row["main_message_id"]) if row else None

    def _require_conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("База данных не подключена")
        return self._conn
