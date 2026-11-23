"""Ticket registry; JSON-backed with a per-process lock."""
import asyncio
import json
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "data" / "ticket_open.json"
LOCK = asyncio.Lock()

def _read():
    return json.loads(PATH.read_text(encoding="utf-8")) if PATH.exists() else {}

def _save(data):
    PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(PATH)

async def get_open(guild_id, user_id):
    async with LOCK:
        return _read().get(str(guild_id), {}).get(str(user_id))

async def save_open(guild_id, user_id, channel_id, category_key):
    async with LOCK:
        data = _read()
        data.setdefault(str(guild_id), {})[str(user_id)] = {
            "channel_id": channel_id, "category_key": category_key
        }
        _save(data)

async def remove_open(guild_id, user_id, channel_id=None):
    async with LOCK:
        data = _read()
        entry = data.get(str(guild_id), {}).get(str(user_id))
        if entry and (channel_id is None or entry["channel_id"] == channel_id):
            del data[str(guild_id)][str(user_id)]
            _save(data)

async def list_open_tickets(guild_id):
    async with LOCK:
        return list(_read().get(str(guild_id), {}).values())

async def find_ticket(guild_id, channel_id):
    async with LOCK:
        for owner_id, item in _read().get(str(guild_id), {}).items():
            if int(item["channel_id"]) == int(channel_id):
                return int(owner_id), item
    return None, None

async def set_assignee(guild_id, channel_id, staff_id):
    async with LOCK:
        data = _read()
        for item in data.get(str(guild_id), {}).values():
            if int(item["channel_id"]) == int(channel_id):
                item["assignee_id"] = staff_id
                _save(data)
                return True
    return False

async def set_ticket_status(guild_id, channel_id, status, actor_id, reason=""):
    if status not in ("open", "closed"):
        raise ValueError("Estado inválido.")
    async with LOCK:
        data = _read()
        for item in data.get(str(guild_id), {}).values():
            if int(item["channel_id"]) == int(channel_id):
                item["status"] = status
                item["last_action_by"] = actor_id
                item["close_reason"] = reason if status == "closed" else ""
                _save(data)
                return True
    return False
