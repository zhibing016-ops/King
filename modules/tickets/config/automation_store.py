"""JSON configuration and last-activity tracking for ticket reminders."""
import asyncio
import json
import time
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "data" / "ticket_automations.json"
LOCK = asyncio.Lock()
DEFAULTS = {
    "enabled": False,
    "inactivity_hours": 24,
    "reminder_hours": 24,
    "welcome_message": "Obrigado por abrir um ticket! Nossa equipe responderá em breve."
}

def _read():
    return json.loads(PATH.read_text(encoding="utf-8")) if PATH.exists() else {}

def _save(data):
    PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(PATH)

async def get_settings(guild_id):
    async with LOCK:
        return {**DEFAULTS, **_read().get(str(guild_id), {}).get("settings", {})}

async def update_settings(guild_id, **kwargs):
    allowed = set(DEFAULTS)
    if set(kwargs) - allowed:
        raise ValueError("Configuração inválida")
    if "inactivity_hours" in kwargs and not 1 <= kwargs["inactivity_hours"] <= 720:
        raise ValueError("Inatividade deve ser de 1 a 720 horas")
    if "reminder_hours" in kwargs and not 1 <= kwargs["reminder_hours"] <= 720:
        raise ValueError("Intervalo deve ser de 1 a 720 horas")
    if "welcome_message" in kwargs and len(kwargs["welcome_message"]) > 1000:
        raise ValueError("Mensagem muito longa")
    async with LOCK:
        data = _read()
        data.setdefault(str(guild_id), {}).setdefault("settings", {}).update(kwargs)
        _save(data)

async def mark_activity(guild_id, channel_id):
    async with LOCK:
        data = _read()
        entry = data.setdefault(str(guild_id), {}).setdefault("activity", {}).setdefault(str(channel_id), {})
        entry["last_activity"] = time.time()
        entry["last_reminder"] = 0
        _save(data)

async def due_reminders(guild_id, open_channel_ids):
    """Return candidate IDs; caller must mark reminder after sending."""
    now = time.time()
    async with LOCK:
        data = _read().get(str(guild_id), {})
        settings = {**DEFAULTS, **data.get("settings", {})}
        if not settings["enabled"]:
            return []
        result = []
        for channel_id in open_channel_ids:
            entry = data.get("activity", {}).get(str(channel_id))
            if not entry:
                continue
            last = entry.get("last_activity", now)
            reminded = entry.get("last_reminder", 0)
            if now - last >= settings["inactivity_hours"] * 3600 and (
                not reminded or now - reminded >= settings["reminder_hours"] * 3600
            ):
                result.append(channel_id)
        return result

async def mark_reminded(guild_id, channel_id):
    async with LOCK:
        data = _read()
        entry = data.setdefault(str(guild_id), {}).setdefault("activity", {}).setdefault(str(channel_id), {})
        entry["last_reminder"] = time.time()
        _save(data)
