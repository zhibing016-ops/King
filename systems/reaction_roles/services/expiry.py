"""Varredura de expirações com lock por membro e rechecagem de prazo."""
import logging
from datetime import datetime, timezone
import discord
from .temporary import expired_grants, remove_if_unchanged
from .reactions import get_member_lock
from .audit import record_audit

log = logging.getLogger(__name__)

async def process_expirations(bot, store):
    for guild in list(bot.guilds):
        try:
            data = await store.get(guild.id)
            for key, grant in expired_grants(data):
                member_id, role_id = int(grant['member_id']), int(grant['role_id'])
                async with get_member_lock(guild.id, member_id):
                    latest = await store.get(guild.id)
                    current = latest.get('temporary_grants', {}).get(key)
                    if not current or current.get('expires_at') != grant['expires_at']:
                        continue
                    if datetime.fromisoformat(current['expires_at']) > datetime.now(timezone.utc):
                        continue
                    role = guild.get_role(role_id)
                    me = guild.me
                    if role is None:
                        await remove_if_unchanged(store, guild.id, key, grant['expires_at'])
                        continue
                    if not me or not me.guild_permissions.manage_roles or role >= me.top_role or role.managed:
                        log.warning('Expiração pendente por permissão: guild=%s role=%s', guild.id, role_id)
                        continue
                    try:
                        member = await guild.fetch_member(member_id)
                    except discord.NotFound:
                        await remove_if_unchanged(store, guild.id, key, grant['expires_at'])
                        continue
                    except (discord.Forbidden, discord.HTTPException):
                        log.exception('Erro ao buscar membro para expiração')
                        continue
                    try:
                        if role in member.roles:
                            await member.remove_roles(role, reason='KING PLUS: cargo temporário expirado')
                            await record_audit(bot, store, guild.id, 'expire', member_id=member_id, role_id=role_id, panel_id=grant.get('panel_id'), source='expiry')
                    except (discord.Forbidden, discord.HTTPException):
                        log.exception('Falha ao expirar cargo')
                        continue
                    await remove_if_unchanged(store, guild.id, key, grant['expires_at'])
        except Exception:
            log.exception('Falha ao processar expirações da guild %s', guild.id)
