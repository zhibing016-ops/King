import asyncio
import json
import re
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "data" / "ticket_categories.json"
LOCK = asyncio.Lock()
MAX_CATEGORIES = 20

async def list_categories(guild_id):
    async with LOCK:
        if not PATH.exists():
            return []
        return json.loads(PATH.read_text(encoding="utf-8")).get(str(guild_id), [])

async def add_category(guild_id, name, description, emoji):
    name = name.strip()
    if not 2 <= len(name) <= 60:
        raise ValueError("O nome deve ter entre 2 e 60 caracteres.")
    if not 1 <= len(description) <= 300:
        raise ValueError("A descrição deve ter entre 1 e 300 caracteres.")
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not slug:
        raise ValueError("Use letras ou números no nome.")
    async with LOCK:
        PATH.parent.mkdir(parents=True, exist_ok=True)
        data = json.loads(PATH.read_text(encoding="utf-8")) if PATH.exists() else {}
        items = data.setdefault(str(guild_id), [])
        if len(items) >= MAX_CATEGORIES:
            raise ValueError("Limite de 20 categorias atingido.")
        if any(item["key"] == slug for item in items):
            raise ValueError("Já existe uma categoria com esse identificador.")
        items.append({"key": slug, "name": name, "description": description, "emoji": emoji or "🎫", "enabled": True})
        tmp = PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(PATH)
        return items[-1]

async def update_category(guild_id, key, action):
    async with LOCK:
        if not PATH.exists():
            raise ValueError("Nenhuma categoria cadastrada.")
        data = json.loads(PATH.read_text(encoding="utf-8"))
        items = data.get(str(guild_id), [])
        item = next((c for c in items if c["key"] == key), None)
        if item is None:
            raise ValueError("Categoria não encontrada.")
        if action == "delete":
            items.remove(item)
        elif action == "toggle":
            item["enabled"] = not item.get("enabled", True)
        else:
            raise ValueError("Ação inválida.")
        tmp = PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(PATH)
