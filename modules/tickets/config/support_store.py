"""Tracks role overwrites applied by support synchronization."""
import asyncio
import json
from pathlib import Path
PATH = Path(__file__).resolve().parents[1] / "data" / "ticket_support_sync.json"
LOCK = asyncio.Lock()

async def get_synced(guild_id, channel_id):
    async with LOCK:
        data = json.loads(PATH.read_text(encoding="utf-8")) if PATH.exists() else {}
        return set(data.get(str(guild_id), {}).get(str(channel_id), []))

async def set_synced(guild_id, channel_id, role_ids):
    async with LOCK:
        data = json.loads(PATH.read_text(encoding="utf-8")) if PATH.exists() else {}
        data.setdefault(str(guild_id), {})[str(channel_id)] = sorted(role_ids)
        PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(PATH)
