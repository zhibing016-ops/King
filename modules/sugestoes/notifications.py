"""Notificações DM opcionais e com falhas tratadas."""
import discord
from modules.sugestoes.storage import read_data, mutate

STATUS_NOTIFICAVEIS = {"Aprovada", "Rejeitada", "Em análise"}

async def enviar_aviso_status(bot, guild_id: int, numero: int, registro: dict) -> str:
    status = registro.get("status")
    if status not in STATUS_NOTIFICAVEIS or registro.get("previous_status") == status:
        return "Nenhuma nova DM necessária."
    data = await read_data(guild_id)
    settings = data.get("settings", {})
    if not settings.get("dm_enabled", True):
        return "Notificações por DM desativadas."
    if not settings.get("dm_statuses", {}).get(status, True):
        return "DM desativada para esse status."
    author_id = registro.get("author_id")
    if not author_id or str(author_id) in settings.get("dm_opt_out", []):
        return "Autor sem DM habilitada."
    # A reserva impede envio duplicado quando revisões ocorrem simultaneamente.
    key = f"{numero}:{status}:{registro.get('reviewed_by')}:{registro.get('previous_status')}"
    def reservar(d):
        item = d.get("suggestions", {}).get(str(numero))
        if not item or item.get("status") != status or item.get("dm_last_key") == key:
            return False
        item["dm_last_key"] = key
        return True
    if not await mutate(guild_id, reservar):
        return "Aviso já processado ou status alterado."
    guild = bot.get_guild(guild_id)
    servidor = guild.name if guild else "seu servidor"
    try:
        usuario = bot.get_user(int(author_id)) or await bot.fetch_user(int(author_id))
        embed = discord.Embed(title=f"💡 Atualização da sugestão #{numero}",
            description=f"Sua sugestão em **{servidor}** está agora: **{status}**.",
            color=discord.Color.blurple())
        embed.set_footer(text="KING PLUS • Sugestões")
        await usuario.send(embed=embed)
        return "DM enviada ao autor."
    except (discord.Forbidden, discord.HTTPException, ValueError):
        return "Não foi possível entregar a DM (privacidade ou erro do Discord)."
