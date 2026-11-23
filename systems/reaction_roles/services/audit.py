"""Auditoria persistente limitada, com envio best-effort para canal do Discord."""
import logging
from datetime import datetime, timezone

log = logging.getLogger(__name__)
VALID_EVENTS = {'grant','revoke','denied','error','expire','config'}
MAX_HISTORY = 500

def sanitize_note(value):
    return str(value).replace('@', '@\u200b')[:350]

def audit_settings(data):
    cfg = data.get('audit', {})
    return {'enabled': bool(cfg.get('enabled', True)),
            'channel_id': str(cfg.get('channel_id') or ''),
            'history': list(cfg.get('history', []))}

async def set_audit_channel(store, guild_id, channel_id):
    channel = str(int(channel_id)) if channel_id else ''
    if channel and int(channel) <= 0:
        raise ValueError('Canal inválido')
    def update(data):
        audit = data.setdefault('audit', {})
        audit['channel_id'] = channel
        audit.setdefault('enabled', True)
        audit.setdefault('history', [])
    await store.mutate(guild_id, update)

async def record_audit(bot, store, guild_id, event, *, member_id=None, role_id=None,
                       panel_id=None, source='', note=''):
    if event not in VALID_EVENTS:
        raise ValueError('Evento de auditoria inválido')
    entry = {'at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
             'event': event, 'member_id': str(member_id or ''),
             'role_id': str(role_id or ''), 'panel_id': str(panel_id or ''),
             'source': sanitize_note(source), 'note': sanitize_note(note)}
    def update(data):
        audit = data.setdefault('audit', {})
        audit.setdefault('enabled', True)
        if audit['enabled']:
            audit['history'] = (audit.get('history', []) + [entry])[-MAX_HISTORY:]
    try:
        data = await store.mutate(guild_id, update)
    except Exception:
        log.exception('Falha ao persistir auditoria guild=%s', guild_id)
        return
    cfg = audit_settings(data)
    if not cfg['enabled'] or not cfg['channel_id'] or bot is None:
        return
    guild = bot.get_guild(guild_id)
    if guild is None:
        return
    channel = guild.get_channel(int(cfg['channel_id']))
    if channel is None:
        return
    message = (f'**KING PLUS • Auditoria** `{event}`\n'
               f'Membro: `{entry["member_id"] or "—"}` | Cargo: `{entry["role_id"] or "—"}`\n'
               f'Painel: `{entry["panel_id"] or "—"}` | Origem: {entry["source"] or "—"}\n'
               f'Detalhe: {entry["note"] or "—"}')
    try:
        await channel.send(message, allowed_mentions=__import__('discord').AllowedMentions.none())
    except Exception:
        log.warning('Falha ao enviar auditoria guild=%s channel=%s', guild_id, cfg['channel_id'], exc_info=True)
