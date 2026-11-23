"""Diagnóstico, backup e restauração dos dados JSON por servidor."""
import io
import json
from datetime import datetime, timezone
from modules.sugestoes.storage import read_data, mutate

MAX_BACKUP_BYTES = 8 * 1024 * 1024

def validate_data(data):
    issues = []
    if not isinstance(data, dict):
        return ["Raiz deve ser um objeto JSON."]
    if not isinstance(data.get("settings"), dict): issues.append("settings deve ser um objeto.")
    suggestions = data.get("suggestions")
    if not isinstance(suggestions, dict):
        issues.append("suggestions deve ser um objeto.")
        suggestions = {}
    next_id = data.get("next_id")
    if type(next_id) is not int or next_id < 1: issues.append("next_id inválido.")
    maximum = 0
    for key, entry in suggestions.items():
        if not isinstance(key, str) or not key.isdecimal() or int(key) < 1:
            issues.append(f"ID inválido: {str(key)[:30]}")
            continue
        maximum = max(maximum, int(key))
        if not isinstance(entry, dict): issues.append(f"Sugestão #{key} não é objeto."); continue
        if not isinstance(entry.get("text"), str): issues.append(f"Texto ausente em #{key}.")
        if not isinstance(entry.get("votes", {}), dict): issues.append(f"Votos inválidos em #{key}.")
    if type(next_id) is int and next_id <= maximum: issues.append("next_id não supera o maior ID.")
    if not isinstance(data.get("audit", []), list): issues.append("audit deve ser lista.")
    return issues[:30]

async def diagnostic(guild_id):
    data = await read_data(guild_id)
    issues = validate_data(data)
    return {"issues": issues, "suggestions": len(data.get("suggestions", {})) if isinstance(data.get("suggestions"), dict) else 0,
            "maintenance": bool(data.get("settings", {}).get("maintenance_enabled", False)) if isinstance(data.get("settings"), dict) else False}

async def make_backup(guild_id):
    data = await read_data(guild_id)
    payload = {"format": "king-plus-suggestions-backup", "version": 1, "guild_id": guild_id,
               "created_at": datetime.now(timezone.utc).isoformat(), "data": data}
    raw = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    if len(raw) > MAX_BACKUP_BYTES: raise ValueError("Backup maior que 8 MiB; faça backup manual da pasta data.")
    return io.BytesIO(raw)

def parse_backup(raw, guild_id):
    if len(raw) > MAX_BACKUP_BYTES: raise ValueError("Arquivo excede 8 MiB.")
    try: payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc: raise ValueError("JSON inválido.") from exc
    if not isinstance(payload, dict) or payload.get("format") != "king-plus-suggestions-backup" or payload.get("version") != 1:
        raise ValueError("Formato ou versão de backup incompatível.")
    if type(payload.get("guild_id")) is not int or payload["guild_id"] != guild_id:
        raise ValueError("Backup pertence a outro servidor.")
    data = payload.get("data")
    issues = validate_data(data)
    if issues: raise ValueError("Falha de integridade: " + "; ".join(issues[:4]))
    return data

async def restore(guild_id, restored):
    # Troca atômica sob o mesmo lock usado pelos demais comandos.
    def replace(data):
        data.clear()
        data.update(restored)
    await mutate(guild_id, replace)
