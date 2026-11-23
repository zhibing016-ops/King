"""Form definitions per guild and category; JSON persistence."""
import asyncio
import json
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "data" / "ticket_forms.json"
LOCK = asyncio.Lock()

async def get_questions(guild_id, category_key):
    async with LOCK:
        if not PATH.exists():
            return []
        return json.loads(PATH.read_text(encoding="utf-8")).get(str(guild_id), {}).get(category_key, [])

async def modify_questions(guild_id, category_key, operation, question=None, index=None):
    async with LOCK:
        PATH.parent.mkdir(parents=True, exist_ok=True)
        data = json.loads(PATH.read_text(encoding="utf-8")) if PATH.exists() else {}
        items = data.setdefault(str(guild_id), {}).setdefault(category_key, [])
        if operation == "add":
            if len(items) >= 5:
                raise ValueError("Máximo de 5 perguntas por formulário (limite do Discord).")
            if not question or not 1 <= len(question["label"]) <= 45:
                raise ValueError("Pergunta inválida (máximo 45 caracteres).")
            items.append(question)
        elif operation == "remove":
            if index is None or index < 0 or index >= len(items):
                raise ValueError("Número de pergunta inválido.")
            items.pop(index)
        elif operation == "clear":
            items.clear()
        else:
            raise ValueError("Operação inválida.")
        tmp = PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(PATH)
        return list(items)
