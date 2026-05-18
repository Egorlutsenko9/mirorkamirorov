from __future__ import annotations

import asyncio
from collections import defaultdict

from ..db import Database
from ..models import Route


class RouteService:
    def __init__(self, db: Database) -> None:
        self._db = db
        self._routes: list[Route] = []
        self._by_source: dict[int, list[Route]] = {}
        self._lock = asyncio.Lock()

    async def reload(self) -> None:
        async with self._lock:
            all_routes = await self._db.list_routes()
            self._routes = all_routes
            grouped: dict[int, list[Route]] = defaultdict(list)
            for route in all_routes:
                if route.enabled:
                    grouped[route.source_chat_id].append(route)
            self._by_source = dict(grouped)

    async def add_route(
        self,
        source_chat_id: int,
        source_thread_id: int | None,
        dest_chat_id: int,
        dest_thread_id: int | None,
    ) -> int:
        route_id = await self._db.add_route(
            source_chat_id=source_chat_id,
            source_thread_id=source_thread_id,
            dest_chat_id=dest_chat_id,
            dest_thread_id=dest_thread_id,
        )
        await self.reload()
        return route_id

    async def toggle_route(self, route_id: int) -> bool:
        enabled = await self._db.toggle_route(route_id)
        await self.reload()
        return enabled

    async def delete_route(self, route_id: int) -> None:
        await self._db.delete_route(route_id)
        await self.reload()

    async def force_destination_chat(self, dest_chat_id: int) -> None:
        await self._db.update_all_dest_chat(dest_chat_id)
        await self.reload()

    def list_routes(self) -> list[Route]:
        return list(self._routes)

    def match(self, source_chat_id: int, source_thread_id: int | None) -> list[Route]:
        routes: list[Route] = []
        for candidate in self._source_id_candidates(source_chat_id):
            routes.extend(self._by_source.get(candidate, []))
        if not routes:
            return []

        matched: list[Route] = []
        for route in routes:
            if route.source_thread_id is None:
                matched.append(route)
            elif route.source_thread_id == source_thread_id:
                matched.append(route)
        return matched

    @staticmethod
    def _source_id_candidates(source_chat_id: int) -> set[int]:
        candidates = {source_chat_id}
        source_str = str(source_chat_id)

        if source_str.startswith("-100"):
            plain_id = source_str[4:]
            if plain_id.isdigit():
                candidates.add(int(plain_id))
        elif source_chat_id > 0:
            candidates.add(int(f"-100{source_chat_id}"))

        return candidates
