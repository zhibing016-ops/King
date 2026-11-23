import re
import discord
from modules.sugestoes.storage import read_data, mutate
from modules.sugestoes.audit import record_event, send_audit_log

IMAGE_RE = re.compile(r"^https://[^\s<>]{1,480}\.(?:png|jpg|jpeg|gif|webp)(?:\?[^\s<>]{0,80})?$", re.I)

def valid_image_url(value: str) -> bool:
    return bool(IMAGE_RE.fullmatch(value))

async def create_discussion_thread(bot, guild_id: int, numero: int, message: discord.Message):
    data = await read_data(guild_id)
    if not data.get("settings", {}).get("threads_enabled", True):
        return
    try:
        thread = await message.create_thread(name=f"💬 Discussão da sugestão #{numero}", auto_archive_duration=1440)
    except (discord.Forbidden, discord.HTTPException, ValueError):
        return
    def store(d):
        entry = d["suggestions"].get(str(numero))
        if entry:
            entry["thread_id"] = thread.id
            record_event(d, "thread_created", bot.user.id, numero, {"thread_id": thread.id})
    await mutate(guild_id, store)
    try:
        from modules.sugestoes.cogs.suggestions import montar_embed, VotacaoView
        latest = (await read_data(guild_id))["suggestions"][str(numero)]
        await message.edit(embed=montar_embed(numero, latest), view=VotacaoView(guild_id, numero))
    except (discord.Forbidden, discord.HTTPException):
        pass

class CommentModal(discord.ui.Modal, title="Comentar sugestão"):
    comentario = discord.ui.TextInput(label="Comentário", style=discord.TextStyle.paragraph, min_length=2, max_length=1000)
    def __init__(self, guild_id: int, numero: int):
        super().__init__()
        self.guild_id, self.numero = guild_id, numero

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.guild_id != self.guild_id:
            return await interaction.response.send_message("Servidor inválido.", ephemeral=True)
        await interaction.response.defer(ephemeral=True, thinking=True)
        data = await read_data(self.guild_id)
        if not data.get("settings", {}).get("comments_enabled", True):
            return await interaction.followup.send("Comentários desativados.", ephemeral=True)
        entry = data.get("suggestions", {}).get(str(self.numero))
        if not entry or not entry.get("thread_id"):
            return await interaction.followup.send("Esta sugestão não possui tópico de discussão.", ephemeral=True)
        thread = interaction.guild.get_thread(entry["thread_id"])
        if thread is None:
            try:
                thread = await interaction.guild.fetch_channel(entry["thread_id"])
            except (discord.HTTPException, discord.Forbidden):
                return await interaction.followup.send("Tópico indisponível.", ephemeral=True)
        try:
            await thread.send(f"💬 **Comentário de {interaction.user.mention}:**\n{discord.utils.escape_mentions(self.comentario.value)}", allowed_mentions=discord.AllowedMentions.none())
        except (discord.Forbidden, discord.HTTPException):
            return await interaction.followup.send("Não consegui enviar o comentário. Verifique as permissões.", ephemeral=True)
        def save(d):
            item = d["suggestions"].get(str(self.numero))
            if item:
                item["comment_count"] = item.get("comment_count", 0) + 1
                record_event(d, "comment_added", interaction.user.id, self.numero, {"count": item["comment_count"]})
        await mutate(self.guild_id, save)
        await send_audit_log(interaction.client, self.guild_id, "comment_added", interaction.user.id, self.numero, {})
        await interaction.followup.send(f"Comentário publicado em {thread.mention}.", ephemeral=True)
