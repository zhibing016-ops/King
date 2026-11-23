"""Campaign windows and structured reward descriptors (metadata, not guaranteed game items)."""
import re
from datetime import datetime, timezone
from uuid import uuid4

def utc_time(value):
    value = value.strip()
    if not value: return None
    try: dt = datetime.strptime(value, '%Y-%m-%d %H:%M').replace(tzinfo=timezone.utc)
    except ValueError: raise ValueError('Use AAAA-MM-DD HH:MM (UTC).')
    return dt.isoformat()

def create_campaign(data, guild_id, game_key, name, start, end):
    name = name.strip()
    if not 2 <= len(name) <= 80: raise ValueError('Nome deve ter 2–80 caracteres.')
    start, end = utc_time(start), utc_time(end)
    if start and end and start >= end: raise ValueError('Início deve ser anterior ao término.')
    key = uuid4().hex
    data.setdefault('campaigns', {})[key] = {'id': key, 'guild_id': guild_id, 'game_key': game_key,
        'name': name, 'starts_at': start, 'ends_at': end, 'enabled': True}
    return key

def active(data, code):
    campaign_id = code.get('campaign_id')
    if not campaign_id: return True
    campaign = data.get('campaigns', {}).get(campaign_id)
    if not campaign or not campaign.get('enabled', False): return False
    if str(campaign.get('guild_id')) != str(code.get('guild_id')) or campaign.get('game_key') != code.get('game_key'): return False
    now = datetime.now(timezone.utc)
    return not ((campaign.get('starts_at') and now < datetime.fromisoformat(campaign['starts_at'])) or
                (campaign.get('ends_at') and now >= datetime.fromisoformat(campaign['ends_at'])))

def parse_rewards(value):
    # Up to ten human-readable descriptors; the game API must interpret these itself.
    items = [x.strip() for x in value.splitlines() if x.strip()]
    if not 1 <= len(items) <= 10 or any(len(x) > 100 for x in items):
        raise ValueError('Informe 1–10 recompensas, uma por linha, até 100 caracteres cada.')
    return items
