"""Armazenamento JSON assíncrono com escrita atômica por servidor."""
import asyncio
import json
import os
import tempfile
from copy import deepcopy
from pathlib import Path

from .config import new_config

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "levels"

class LevelStorage:
    def __init__(self, data_dir=DATA_DIR):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._locks = {}

    def _path(self, guild_id: int) -> Path:
        if not isinstance(guild_id, int) or guild_id <= 0:
            raise ValueError("guild_id inválido")
        return self.data_dir / f"guild_{guild_id}.json"

    def _read(self, guild_id: int) -> dict:
        path = self._path(guild_id)
        if not path.exists():
            return {"schema_version": 1, "guild_id": guild_id, "config": new_config(), "members": {}}
        with path.open("r", encoding="utf-8") as stream:
            data = json.load(stream)
        if not isinstance(data, dict) or data.get("guild_id") != guild_id:
            raise ValueError(f"Dados inválidos em {path}")
        data.setdefault("members", {})
        data.setdefault("config", new_config())
        for key, value in new_config().items():
            data["config"].setdefault(key, value)
        return data

    def _write(self, guild_id: int, data: dict):
        path = self._path(guild_id)
        fd, tmp = tempfile.mkstemp(prefix=".guild_", suffix=".tmp", dir=self.data_dir)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    async def get(self, guild_id: int) -> dict:
        lock = self._locks.setdefault(guild_id, asyncio.Lock())
        async with lock:
            return deepcopy(await asyncio.to_thread(self._read, guild_id))

    async def get_member(self, guild_id: int, member_id: int) -> dict:
        """Retorna um retrato do membro sem criar registro nem gravar JSON."""
        if not isinstance(member_id, int) or member_id <= 0:
            raise ValueError("member_id inválido")
        data = await self.get(guild_id)
        record = data["members"].get(str(member_id), {"xp": 0, "level": 0})
        from .level_calculator import level_from_xp
        xp = int(record["xp"])
        if xp < 0:
            raise ValueError("XP armazenado inválido")
        return {"xp": xp, "level": level_from_xp(xp)}

    async def update_config(self, guild_id: int, **changes) -> dict:
        allowed = set(new_config())
        if not set(changes).issubset(allowed):
            raise ValueError("Campo de configuração desconhecido")
        lock = self._locks.setdefault(guild_id, asyncio.Lock())
        async with lock:
            data = await asyncio.to_thread(self._read, guild_id)
            data["config"].update(changes)
            await asyncio.to_thread(self._write, guild_id, data)
            return deepcopy(data["config"])

    async def set_member(self, guild_id: int, member_id: int, *, xp: int, level: int) -> dict:
        if min(xp, level) < 0:
            raise ValueError("XP e nível não podem ser negativos")
        lock = self._locks.setdefault(guild_id, asyncio.Lock())
        async with lock:
            data = await asyncio.to_thread(self._read, guild_id)
            member = {"xp": int(xp), "level": int(level)}
            data["members"][str(member_id)] = member
            await asyncio.to_thread(self._write, guild_id, data)
            return deepcopy(member)

    async def add_xp(self, guild_id: int, member_id: int, amount: int) -> tuple[dict, int]:
        """Incrementa XP e recalcula nível dentro da trava do servidor."""
        from .level_calculator import level_from_xp
        if amount < 0 or member_id <= 0:
            raise ValueError("XP ou usuário inválido")
        lock = self._locks.setdefault(guild_id, asyncio.Lock())
        async with lock:
            data = await asyncio.to_thread(self._read, guild_id)
            member = data["members"].setdefault(str(member_id), {"xp": 0, "level": 0})
            old_level = level_from_xp(member["xp"])
            member["xp"] += amount
            member["level"] = level_from_xp(member["xp"])
            await asyncio.to_thread(self._write, guild_id, data)
            return deepcopy(member), old_level
