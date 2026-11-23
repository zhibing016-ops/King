"""Auditoria append-only lógica armazenada no JSON por servidor."""
from datetime import datetime, timezone
import discord
from modules.sugestoes.storage import read_data

MAX_EVENTS = 5000

def record_event(data, action, actor_id, suggestion_id=None, details=None):
    events = data.setdefault("audit_events", [])
    seq = int(data.get("audit_next_id", 1))
    data["audit_next_id"] = seq + 1
    events.append({"id": seq, "timestamp": datetime.now(timezone.utc).isoformat(),
                   "action": action, "actor_id": actor_id,
                   "suggestion_id": suggestion_id, "details": details or {}})
    # Retenção configurável: manter no máximo 5000 eventos por servidor.
    if len(events) > MAX_EVENTS:
        del events[:-MAX_EVENTS]
    return seq

async def send_audit_log(bot, guild_id, action, actor_id, suggestion_id=None, details=None):
    data = await read_data(guild_id)
    channel_id = data.get("settings", {}).get("audit_channel_id")
    if not channel_id:
        return False
    guild = bot.get_guild(guild_id)
    if not guild:
        return False
    channel = guild.get_channel(channel_id)
    if channel is None:
        try:
            channel = await guild.fetch_channel(channel_id)
        except (discord.HTTPException, discord.Forbidden):
            return False
    labels = {"suggestion_created": "Nova sugestão", "status_changed": "Status alterado",
              "audit_channel_changed": "Canal de auditoria configurado"}
    desc = f"**Ação:** {labels.get(action, action)}\n**Responsável:** <@{actor_id}>"
    if suggestion_id is not None:
        desc += f"\n**Sugestão:** #{suggestion_id}"
    if details:
        # Não divulgar autoria anônima nem texto de sugestões nos logs.
        if action == "status_changed":
            desc += f"\n**De:** {details.get('before')}\n**Para:** {details.get('after')}"
        elif action == "suggestion_created":
            desc = f"**Ação:** Nova sugestão\n**Sugestão:** #{suggestion_id}\n**Autoria:** " + ("Anônima" if details.get("anonymous") else f"<@{actor_id}>")
    embed = discord.Embed(title="📋 KING PLUS • Auditoria", description=desc,
                          color=discord.Color.blurple(), timestamp=datetime.now(timezone.utc))
    try:
        await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        return True
    except (discord.Forbidden, discord.HTTPException):
        return False
