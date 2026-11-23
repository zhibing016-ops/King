import asyncio
import json
import time
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "data" / "ticket_limits.json"
LOCK = asyncio.Lock()
DEFAULTS = {"cooldown_seconds": 300, "max_open_per_user": 1}
def read_all():
    return json.loads(PATH.read_text(encoding="utf-8")) if PATH.exists() else {}
def write_all(data):
    PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(PATH)
async def get_limits(guild_id):
    async with LOCK:
        return {**DEFAULTS, **read_all().get(str(guild_id), {}).get("settings", {})}
async def configure_limits(guild_id, cooldown_seconds):
    if not 0 <= cooldown_seconds <= 86400:
        raise ValueError("Cooldown deve estar entre 0 e 86400 segundos.")
    async with LOCK:
        data = read_all()
        data.setdefault(str(guild_id), {}).setdefault("settings", {})["cooldown_seconds"] = cooldown_seconds
        write_all(data)
async def remaining_cooldown(guild_id, user_id):
    async with LOCK:
        data = read_all().get(str(guild_id), {})
        seconds = data.get("settings", {}).get("cooldown_seconds", 300)
        last = data.get("last_open", {}).get(str(user_id), 0)
        return max(0, int(last + seconds - time.time() + .999))
async def record_open(guild_id, user_id):
    async with LOCK:
        data = read_all()
        data.setdefault(str(guild_id), {}).setdefault("last_open", {})[str(user_id)] = time.time()
        write_all(data)
