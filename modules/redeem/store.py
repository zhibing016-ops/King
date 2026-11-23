import json
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / 'storage' / 'redeem.json'
DEFAULT = {'games': {}, 'codes': {}, 'claims': [], 'settings': {}}

def load():
    DATA.parent.mkdir(parents=True, exist_ok=True)
    if not DATA.exists():
        save(DEFAULT.copy())
    with DATA.open(encoding='utf-8') as f:
        data = json.load(f)
    for k, v in DEFAULT.items():
        data.setdefault(k, v.copy() if isinstance(v, dict) else [])
    return data

def save(data):
    DATA.parent.mkdir(parents=True, exist_ok=True)
    temp = DATA.with_suffix('.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(DATA)

def guild_games(data, guild_id):
    # Fase 01 stored game records without a guild id. Those remain available
    # to the first guild that edits them, but are not exposed across guilds.
    return {k:v for k,v in data['games'].items() if str(v.get('guild_id')) == str(guild_id)}
