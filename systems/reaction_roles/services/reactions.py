"""Sincronização de reações e aplicação segura de cargos."""
import asyncio
import logging
import re
import discord
from .panels import panel_embed
from .unique import conflicting_role_ids
from .modes import role_action
from .temporary import register_grant, unregister_grant
from .access import can_change
from .audit import record_audit

log = logging.getLogger(__name__)
_member_locks = {}

def get_member_lock(guild_id, user_id):
    return _member_locks.setdefault((guild_id, user_id), asyncio.Lock())
CUSTOM = re.compile(r"^<a?:[A-Za-z0-9_]{2,32}:([0-9]{15,22})>$")

def emoji_key(emoji):
    """Normaliza emojis personalizados sem depender do nome alterável."""
    value = str(emoji)
    match = CUSTOM.fullmatch(value)
    if match:
        return f"custom:{match.group(1)}"
    if isinstance(emoji, (discord.Emoji, discord.PartialEmoji)) and emoji.id:
        return f"custom:{emoji.id}"
    return value

def mapped_role(panel, emoji):
    target = emoji_key(emoji)
    for key, role_id in panel.get('roles', {}).items():
        if emoji_key(key) == target:
            return int(role_id)
    return None

async def sync_message(message, panel):
    """Atualiza o embed e adiciona emojis cadastrados; erros são informados."""
    await message.edit(embed=panel_embed(discord, panel))
    errors = []
    for emoji in panel.get('roles', {}):
        try:
            await message.add_reaction(emoji)
        except (discord.HTTPException, discord.InvalidArgument, TypeError, ValueError) as exc:
            errors.append(f'{emoji}: {type(exc).__name__}')
    return errors

async def handle_raw_reaction(bot, store, payload, adding):
    if not payload.guild_id or not payload.user_id or payload.user_id == bot.user.id:
        return
    guild = bot.get_guild(payload.guild_id)
    if guild is None:
        return
    data = await store.get(guild.id)
    if not data.get('enabled', False):
        return
    panel = next((p for p in data.get('panels', {}).values()
                  if p.get('message_id') == str(payload.message_id)
                  and p.get('channel_id') == str(payload.channel_id)), None)
    if not panel or panel.get("interface", "reactions") != "reactions":
        return
    action = role_action(panel, adding)
    if action is None:
        return
    role_id = mapped_role(panel, payload.emoji)
    if role_id is None:
        return
    role = guild.get_role(role_id)
    me = guild.me
    if (role is None or role.is_default() or role.managed or me is None
            or not me.guild_permissions.manage_roles or role >= me.top_role):
        log.warning('Cargo indisponível/não gerenciável: guild=%s role=%s', guild.id, role_id)
        await record_audit(bot, store, guild.id, 'error', role_id=role_id, panel_id=panel['id'], source='reaction', note='Permissão ou hierarquia insuficiente')
        return
    member = payload.member if adding else None
    if member is None:
        member = guild.get_member(payload.user_id)
    if member is None:
        try:
            member = await guild.fetch_member(payload.user_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return
    if member.bot:
        return
    allowed, reason = can_change(panel, member, action)
    if not allowed:
        log.info("Reaction Roles: acesso negado guild=%s user=%s: %s", guild.id, member.id, reason)
        await record_audit(bot, store, guild.id, "denied", member_id=member.id, role_id=role_id, panel_id=panel["id"], source="reaction", note=reason)
        return
    try:
        if action == "grant":
            # Unique: remoção dos cargos conflitantes antes da atribuição.
            # A operação é serializada por membro para reduzir corridas entre reações.
            lock = get_member_lock(guild.id, member.id)
            async with lock:
                if panel.get('unique'):
                    # fetch_member traz os cargos atuais, evitando cache desatualizado.
                    try:
                        member = await guild.fetch_member(member.id)
                    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                        return
                    conflicts = conflicting_role_ids(panel, role_id)
                    removable = [r for r in member.roles if r.id in conflicts]
                    if removable:
                        if any(r >= me.top_role or r.managed for r in removable):
                            log.warning('Unique bloqueado por hierarquia: guild=%s user=%s', guild.id, member.id)
                            return
                        await member.remove_roles(*removable, reason='KING PLUS Reaction Roles: modo Unique')
                if role not in member.roles:
                    await member.add_roles(role, reason='KING PLUS Reaction Roles: reação adicionada')
                    await record_audit(bot, store, guild.id, 'grant', member_id=member.id, role_id=role.id, panel_id=panel['id'], source='reaction')
                    if panel.get('temporary_seconds'):
                        await register_grant(store, guild.id, member.id, role.id, panel['id'], panel['temporary_seconds'])
        elif action == "revoke" and role in member.roles:
            await member.remove_roles(role, reason='KING PLUS Reaction Roles: reação removida')
            await record_audit(bot, store, guild.id, 'revoke', member_id=member.id, role_id=role.id, panel_id=panel['id'], source='reaction')
            await unregister_grant(store, guild.id, member.id, role.id)
    except (discord.Forbidden, discord.HTTPException):
        log.exception('Não foi possível alterar cargo: guild=%s user=%s role=%s', guild.id, member.id, role.id)
        await record_audit(bot, store, guild.id, 'error', member_id=member.id, role_id=role.id, panel_id=panel['id'], source='reaction', note='Falha na API do Discord')
