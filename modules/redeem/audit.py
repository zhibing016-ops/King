"""Per-guild audit history. No credentials, tokens, or raw API bodies."""
from datetime import datetime, timezone
from uuid import uuid4
from modules.redeem.store import load, save

MAX_EVENTS = 1500
TYPES = {'claim_created', 'delivery_started', 'delivery_confirmed', 'delivery_review',
         'delivery_rejected', 'api_test', 'api_delivery_toggled', 'log_channel_changed'}

def append(data, guild_id, kind, *, claim_id='', actor_id=None, details=''):
    if kind not in TYPES:
        raise ValueError('Evento de auditoria desconhecido.')
    events = data.setdefault('audit_events', [])
    events.append({'id': uuid4().hex, 'guild_id': str(guild_id),
                   'kind': kind, 'claim_id': str(claim_id)[:64],
                   'actor_id': str(actor_id) if actor_id is not None else '',
                   'details': str(details)[:180],
                   'at': datetime.now(timezone.utc).isoformat(timespec='seconds')})
    # Retention bounded per guild; other guilds retain their own records.
    own = [e for e in events if e.get('guild_id') == str(guild_id)]
    if len(own) > MAX_EVENTS:
        old_ids = {e['id'] for e in own[:-MAX_EVENTS]}
        data['audit_events'] = [e for e in events if e['id'] not in old_ids]

def history(guild_id, limit=15):
    data = load()
    events = [e for e in data.get('audit_events', []) if e.get('guild_id') == str(guild_id)]
    return list(reversed(events[-max(1, min(limit, 50)):]))

def channel_id(guild_id):
    return load().get('settings', {}).get(str(guild_id), {}).get('audit_channel_id')

def set_channel(guild_id, new_channel_id, actor_id):
    data = load()
    data.setdefault('settings', {}).setdefault(str(guild_id), {})['audit_channel_id'] = str(new_channel_id) if new_channel_id else None
    append(data, guild_id, 'log_channel_changed', actor_id=actor_id,
           details='Canal de logs configurado' if new_channel_id else 'Canal de logs desativado')
    save(data)

async def notify(guild, kind, claim_id='', details=''):
    """Best-effort Discord notification; never changes delivery state."""
    import discord
    if guild is None: return
    configured = channel_id(guild.id)
    if not configured: return
    channel = guild.get_channel(int(configured))
    if channel is None or not hasattr(channel, 'send'): return
    embed = discord.Embed(title='📋 KING PLUS | Auditoria Redeem', color=discord.Color.blurple())
    embed.add_field(name='Evento', value=kind[:100], inline=False)
    if claim_id: embed.add_field(name='Solicitação', value=f'`{claim_id[:32]}`', inline=False)
    if details: embed.add_field(name='Detalhes', value=discord.utils.escape_mentions(details[:180]), inline=False)
    try:
        await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
    except (discord.Forbidden, discord.HTTPException):
        pass
