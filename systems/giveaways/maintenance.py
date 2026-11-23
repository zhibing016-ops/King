"""Backup, restore and structural validation for KING PLUS giveaways."""
import asyncio
import copy
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def validate_data(data):
    issues = []
    if not isinstance(data, dict):
        return ['Raiz JSON precisa ser um objeto.']
    if not isinstance(data.get('guilds'), dict):
        return ['Campo guilds precisa ser um objeto.']
    for gid, guild in data['guilds'].items():
        if not str(gid).isdigit() or not isinstance(guild, dict):
            issues.append(f'Servidor inválido: {gid}')
            continue
        giveaways = guild.get('giveaways', {})
        if not isinstance(giveaways, dict):
            issues.append(f'{gid}: giveaways não é objeto')
            continue
        for mid, record in giveaways.items():
            if not isinstance(record, dict):
                issues.append(f'{gid}/{mid}: sorteio não é objeto')
                continue
            if not str(mid).isdigit():
                issues.append(f'{gid}/{mid}: ID de mensagem inválido')
            participants = record.get('participants', [])
            if not isinstance(participants, list):
                issues.append(f'{gid}/{mid}: participantes não é lista')
            elif len(set(map(str, participants))) != len(participants):
                issues.append(f'{gid}/{mid}: participantes duplicados')
            if not isinstance(record.get('winners', []), list):
                issues.append(f'{gid}/{mid}: vencedores não é lista')
        for key in ('schedules', 'audit_log'):
            if key in guild and not isinstance(guild[key], list):
                issues.append(f'{gid}: {key} não é lista')
    return issues


def inspect_store(path):
    path = Path(path)
    if not path.exists():
        return {'ok': False, 'issues': ['Arquivo JSON não encontrado.'], 'guilds': 0, 'giveaways': 0}
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        return {'ok': False, 'issues': [f'Erro de leitura: {exc}'], 'guilds': 0, 'giveaways': 0}
    issues = validate_data(data)
    guilds = data.get('guilds', {}) if isinstance(data, dict) else {}
    if not isinstance(guilds, dict):
        guilds = {}
    return {'ok': not issues, 'issues': issues, 'guilds': len(guilds),
            'giveaways': sum(len(g.get('giveaways', {})) for g in guilds.values() if isinstance(g, dict) and isinstance(g.get('giveaways', {}), dict))}


async def export_guild(store, guild_id):
    async with store._lock:
        data = store._read()
        guild = copy.deepcopy(data.get('guilds', {}).get(str(guild_id), {'enabled': True, 'giveaways': {}}))
    return json.dumps({'schema_version': 1, 'guilds': {str(guild_id): guild}}, ensure_ascii=False, indent=2).encode('utf-8')


async def restore_guild(store, guild_id, content):
    if len(content) > 8 * 1024 * 1024:
        raise ValueError('Backup excede 8 MB.')
    try:
        incoming = json.loads(content.decode('utf-8'))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError('Arquivo não é JSON UTF-8 válido.') from exc
    issues = validate_data(incoming)
    if issues:
        raise ValueError('Backup inválido: ' + '; '.join(issues[:3]))
    gid = str(guild_id)
    if set(incoming['guilds']) != {gid}:
        raise ValueError('O backup deve conter apenas o servidor atual.')
    async with store._lock:
        data = store._read()
        current_issues = validate_data(data)
        if current_issues:
            raise ValueError('Dados atuais inválidos; restauração bloqueada para evitar perda.')
        # Save a rollback snapshot before changing anything.
        backup_dir = store.path.parent / 'backups'
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = backup_dir / f'{gid}_{datetime.now(timezone.utc):%Y%m%d_%H%M%S_%f}.json'
        backup_path.write_text(json.dumps({'schema_version': 1, 'guilds': {gid: data.get('guilds', {}).get(gid, {})}}, ensure_ascii=False, indent=2), encoding='utf-8')
        data.setdefault('guilds', {})[gid] = incoming['guilds'][gid]
        store._write(data)
    return backup_path
