"""Trilha de auditoria persistente, sem dados sensíveis."""
import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path

LOG_FILE = Path(__file__).resolve().parent.parent / 'data' / 'audit.jsonl'
_lock = asyncio.Lock()

async def record_event(action, actor_id, *, system=None, previous=None, current=None, detail=None):
    event = {'at': datetime.now(timezone.utc).isoformat(), 'action': action,
             'actor_id': str(actor_id), 'system': system, 'previous': previous,
             'current': current, 'detail': detail}
    async with _lock:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open('a', encoding='utf-8') as fp:
            fp.write(json.dumps(event, ensure_ascii=False) + '\n')
    return event

async def post_audit_notice(bot, event):
    from core.maintenance_notices import get_setting
    import discord
    channel_id = get_setting('audit_channel_id')
    if not channel_id:
        return False
    try:
        channel = bot.get_channel(int(channel_id)) or await bot.fetch_channel(int(channel_id))
        if not hasattr(channel, 'send'):
            return False
        embed = discord.Embed(title='🛡️ KING PLUS • Registro administrativo', color=discord.Color.dark_blue())
        embed.add_field(name='Ação', value=str(event['action']), inline=True)
        embed.add_field(name='Responsável (ID)', value=event['actor_id'], inline=True)
        if event['system']:
            embed.add_field(name='Sistema', value=event['system'], inline=True)
        if event['previous'] is not None:
            embed.add_field(name='Anterior → Atual', value=f"{event['previous']} → {event['current']}", inline=False)
        if event['detail']:
            embed.add_field(name='Detalhes', value=str(event['detail'])[:1024], inline=False)
        embed.timestamp = datetime.fromisoformat(event['at'])
        await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        return True
    except (discord.Forbidden, discord.NotFound, discord.HTTPException, ValueError, TypeError):
        return False

async def audit(bot, action, actor_id, **kwargs):
    event = await record_event(action, actor_id, **kwargs)
    await post_audit_notice(bot, event)
    return event
