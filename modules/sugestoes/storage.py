import json
import asyncio
from pathlib import Path
from modules.sugestoes.config import DATA_DIR

_locks = {}
def _path(guild_id): return DATA_DIR / f"guild_{guild_id}.json"
def _lock(guild_id): return _locks.setdefault(guild_id, asyncio.Lock())
async def read_data(guild_id):
    async with _lock(guild_id):
        p = _path(guild_id)
        if not p.exists(): return {"settings": {}, "suggestions": {}, "next_id": 1}
        return json.loads(p.read_text(encoding="utf-8"))
async def mutate(guild_id, callback):
    async with _lock(guild_id):
        p = _path(guild_id)
        data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"settings": {}, "suggestions": {}, "next_id": 1}
        result = callback(data)
        temp = p.with_suffix('.tmp')
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(p)
        return result
