"""Per-ticket priority and internal support notes, persisted as JSON."""
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / 'data' / 'ticket_attention.json'
LOCK = asyncio.Lock()
PRIORITIES = ('baixa', 'normal', 'alta', 'urgente')

def _read():
    return json.loads(PATH.read_text(encoding='utf-8')) if PATH.exists() else {}

def _write(data):
    PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = PATH.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(PATH)

async def set_priority(guild_id, channel_id, priority, actor_id):
    if priority not in PRIORITIES:
        raise ValueError('Prioridade inválida')
    async with LOCK:
        data = _read()
        item = data.setdefault(str(guild_id), {}).setdefault(str(channel_id), {})
        item['priority'] = priority
        item['priority_by'] = actor_id
        _write(data)

async def add_note(guild_id, channel_id, author_id, content):
    content = content.strip()
    if not content or len(content) > 1000:
        raise ValueError('Nota deve ter entre 1 e 1000 caracteres')
    async with LOCK:
        data = _read()
        item = data.setdefault(str(guild_id), {}).setdefault(str(channel_id), {})
        notes = item.setdefault('notes', [])
        notes.append({'author_id': author_id, 'content': content,
                      'at': datetime.now(timezone.utc).isoformat()})
        item['notes'] = notes[-30:]
        _write(data)

async def get_attention(guild_id, channel_id):
    async with LOCK:
        return dict(_read().get(str(guild_id), {}).get(str(channel_id), {}))
