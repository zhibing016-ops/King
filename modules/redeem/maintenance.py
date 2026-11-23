"""Guild-scoped offline backup, restore and diagnostics. Never backs up API secrets."""
import copy
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from modules.redeem.store import DATA, load, save

BACKUPS = DATA.parent / 'backups'
COLLECTIONS = ('games', 'codes', 'campaigns')
LISTS = ('claims', 'audit_events')
MAX_BYTES = 4_000_000

def _own(record, guild_id):
    return isinstance(record, dict) and str(record.get('guild_id')) == str(guild_id)

def snapshot(guild_id, data=None):
    data = data if data is not None else load()
    gid = str(guild_id)
    payload = {'format': 'kingplus-redeem-guild-v1', 'guild_id': gid,
               'created_at': datetime.now(timezone.utc).isoformat()}
    for key in COLLECTIONS:
        payload[key] = {k: copy.deepcopy(v) for k, v in data.get(key, {}).items() if _own(v, gid)}
    for key in LISTS:
        payload[key] = [copy.deepcopy(v) for v in data.get(key, []) if _own(v, gid)]
    payload['settings'] = copy.deepcopy(data.get('settings', {}).get(gid, {}))
    # Secret credentials live outside this JSON file and are never exported.
    return payload

def validate_backup(obj, guild_id):
    if not isinstance(obj, dict) or obj.get('format') != 'kingplus-redeem-guild-v1' or str(obj.get('guild_id')) != str(guild_id):
        raise ValueError('Backup incompatível com este servidor.')
    for key in COLLECTIONS:
        if not isinstance(obj.get(key), dict) or any(not _own(v, guild_id) for v in obj[key].values()):
            raise ValueError('Registros de jogo/código/campanha inválidos.')
    for key in LISTS:
        if not isinstance(obj.get(key), list) or any(not _own(v, guild_id) for v in obj[key]):
            raise ValueError('Registros de solicitações/auditoria inválidos.')
    if not isinstance(obj.get('settings'), dict):
        raise ValueError('Configurações inválidas.')
    games = obj['games']
    if any(c.get('game_key') not in games for c in obj['codes'].values()):
        raise ValueError('Código aponta para jogo ausente.')
    if any(c.get('game_key') not in games for c in obj['campaigns'].values()):
        raise ValueError('Campanha aponta para jogo ausente.')
    if any(c.get('game_key') not in games or c.get('code_id') not in obj['codes'] for c in obj['claims']):
        raise ValueError('Solicitação aponta para jogo ou código ausente.')

def create_backup(guild_id):
    obj = snapshot(guild_id)
    validate_backup(obj, guild_id)
    BACKUPS.mkdir(parents=True, exist_ok=True)
    name = f'{guild_id}_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}_{uuid4().hex[:8]}.json'
    raw = json.dumps(obj, ensure_ascii=False, indent=2).encode('utf-8')
    if len(raw) > MAX_BYTES: raise ValueError('Backup excede 4 MB.')
    path = BACKUPS / name
    with path.open('xb') as file: file.write(raw)
    return name

def backups_for(guild_id):
    if not BACKUPS.exists(): return []
    return sorted((x.name for x in BACKUPS.glob(f'{guild_id}_*.json') if x.is_file()), reverse=True)[:15]

def restore_backup(guild_id, name):
    if not re.fullmatch(r'[0-9]+_[0-9]{8}T[0-9]{6}Z_[0-9a-f]{8}\.json', name) or not name.startswith(f'{guild_id}_'):
        raise ValueError('Nome de backup inválido.')
    path = BACKUPS / name
    if not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ValueError('Backup não encontrado ou excede o limite.')
    obj = json.loads(path.read_text(encoding='utf-8'))
    validate_backup(obj, guild_id)
    data = load()
    gid = str(guild_id)
    for key in COLLECTIONS:
        data[key] = {k: v for k, v in data.get(key, {}).items() if not _own(v, gid)}
        data[key].update(copy.deepcopy(obj[key]))
    for key in LISTS:
        data[key] = [v for v in data.get(key, []) if not _own(v, gid)]
        restored = copy.deepcopy(obj[key])
        if key == 'claims':
            # Unknown outcomes are never automatically retried after rollback.
            for c in restored:
                if c.get('status') in ('pending', 'processing'):
                    c['status'] = 'review'
        data[key].extend(restored)
    data.setdefault('settings', {})[gid] = copy.deepcopy(obj['settings'])
    for game in data['games'].values():
        if _own(game, gid):
            game.setdefault('api', {})['enabled'] = False
    save(data)
    return 'Backup restaurado. Entregas desativadas e pendências enviadas para revisão. Confira o jogo antes de reativar.'

def diagnostics(guild_id):
    data = load()
    games = {k:v for k,v in data.get('games', {}).items() if _own(v, guild_id)}
    codes = {k:v for k,v in data.get('codes', {}).items() if _own(v, guild_id)}
    claims = [c for c in data.get('claims', []) if _own(c, guild_id)]
    issues = []
    for key, code in codes.items():
        if code.get('game_key') not in games: issues.append(f'Código {key[:12]} sem jogo.')
        if int(code.get('claims_count', 0)) < 0: issues.append(f'Contagem negativa em {key[:12]}.')
    for claim in claims:
        if claim.get('code_id') not in codes: issues.append('Claim sem código associado.')
        if claim.get('status') in ('review', 'processing'): issues.append('Há entregas que exigem conciliação manual.')
    for game in games.values():
        api = game.get('api', {})
        if api.get('enabled') and not api.get('base_url'): issues.append('Entrega habilitada sem URL da API.')
    return {'games':len(games), 'codes':len(codes), 'claims':len(claims),
            'issues':list(dict.fromkeys(issues))[:15]}
