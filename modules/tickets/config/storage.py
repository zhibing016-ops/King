import asyncio
import json
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data" / "tickets.json"
LOCK = asyncio.Lock()

async def get_config(guild_id: int):
    async with LOCK:
        DATA.parent.mkdir(parents=True, exist_ok=True)
        if not DATA.exists():
            DATA.write_text("{}", encoding="utf-8")
        payload = json.loads(DATA.read_text(encoding="utf-8"))
        return payload.get(str(guild_id), {"enabled": True})

async def update_config(guild_id: int, **changes):
    async with LOCK:
        DATA.parent.mkdir(parents=True, exist_ok=True)
        payload = json.loads(DATA.read_text(encoding="utf-8")) if DATA.exists() else {}
        cfg = payload.setdefault(str(guild_id), {"enabled": True})
        cfg.update(changes)
        tmp = DATA.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(DATA)
        return cfg
