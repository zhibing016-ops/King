"""Persistência JSON atômica e serializada por servidor."""
import asyncio
import copy
import json
import os
import tempfile
from pathlib import Path
from typing import Callable
from ..config import DATA_DIR, default_guild_config

class GuildJsonStore:
    def __init__(self, directory: Path = DATA_DIR):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._locks: dict[int, asyncio.Lock] = {}

    def _path(self, guild_id: int) -> Path:
        if not isinstance(guild_id, int) or guild_id <= 0:
            raise ValueError('guild_id inválido')
        return self.directory / f'{guild_id}.json'

    def _lock(self, guild_id: int) -> asyncio.Lock:
        return self._locks.setdefault(guild_id, asyncio.Lock())

    def _read_unlocked(self, guild_id: int) -> dict:
        path = self._path(guild_id)
        if not path.exists():
            return default_guild_config(guild_id)
        with path.open('r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict) or data.get('guild_id') != str(guild_id):
            raise ValueError('Arquivo JSON inválido ou servidor incompatível')
        return data

    def _write_unlocked(self, guild_id: int, data: dict) -> None:
        path = self._path(guild_id)
        if not isinstance(data, dict) or data.get('guild_id') != str(guild_id):
            raise ValueError('Dados incompatíveis com o servidor')
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.directory,
                                             prefix=f'{guild_id}.', suffix='.tmp', delete=False) as f:
                temporary = Path(f.name)
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.write('\n')
                f.flush()
                os.fsync(f.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    async def get(self, guild_id: int) -> dict:
        async with self._lock(guild_id):
            return copy.deepcopy(self._read_unlocked(guild_id))

    async def initialize(self, guild_id: int) -> tuple[dict, bool]:
        async with self._lock(guild_id):
            path = self._path(guild_id)
            if path.exists():
                return copy.deepcopy(self._read_unlocked(guild_id)), False
            data = default_guild_config(guild_id)
            self._write_unlocked(guild_id, data)
            return copy.deepcopy(data), True

    async def mutate(self, guild_id: int, change: Callable[[dict], None]) -> dict:
        async with self._lock(guild_id):
            data = self._read_unlocked(guild_id)
            change(data)
            if data.get('guild_id') != str(guild_id):
                raise ValueError('guild_id não pode ser alterado')
            self._write_unlocked(guild_id, data)
            return copy.deepcopy(data)

    async def update(self, guild_id: int, changes: dict) -> dict:
        if {'guild_id', 'schema_version'} & changes.keys():
            raise ValueError('Campos reservados não podem ser alterados')
        return await self.mutate(guild_id, lambda data: data.update(changes))

    async def toggle_enabled(self, guild_id: int) -> dict:
        return await self.mutate(guild_id, lambda data: data.update(enabled=not bool(data.get('enabled', False))))
